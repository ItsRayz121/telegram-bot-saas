"""
Google Calendar integration routes.

GET  /api/calendar/auth-url          → OAuth authorization URL
GET  /api/calendar/callback          → Google OAuth redirect handler
GET  /api/calendar/status            → connection status + calendar email
GET  /api/calendar/events            → upcoming events from Google Calendar
POST /api/calendar/sync-reminder/<id> → push a reminder to Google Calendar
DELETE /api/calendar/disconnect      → revoke + delete stored tokens

Required env vars:
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  GOOGLE_REDIRECT_URI  (e.g. https://yourdomain.com/api/calendar/callback)
  FRONTEND_URL         (e.g. https://yourdomain.com — for post-OAuth redirect)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, redirect, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import db, User, GoogleCalendarToken
from ..middleware.rate_limit import rate_limit
from ..config import Config
from .. import secret_vault as _sv

_log = logging.getLogger(__name__)

# Google returns the granted scopes in a different order (and may add `openid`),
# which makes oauthlib raise "Scope has changed" and abort the token exchange.
# Relax that check so the callback can complete.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

calendar_bp = Blueprint("calendar", __name__, url_prefix="/api/calendar")

# calendar.events lets us create/read events; openid + userinfo.email let us
# read the connected account's address (shown in Settings). Without the email
# scope, the userinfo lookup in the callback fails and the whole connect breaks.
_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

# ── Helpers ───────────────────────────────────────────────────────────────────


def _current_user() -> User:
    return User.query.get(int(get_jwt_identity()))


def _is_configured() -> bool:
    return bool(
        getattr(Config, "GOOGLE_CLIENT_ID", None)
        and getattr(Config, "GOOGLE_CLIENT_SECRET", None)
    )


def _client_config() -> dict:
    return {
        "web": {
            "client_id": Config.GOOGLE_CLIENT_ID,
            "client_secret": _sv.get_secret("GOOGLE_CLIENT_SECRET"),
            "redirect_uris": [Config.GOOGLE_REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def _enc(val: str) -> str:
    from ..utils.encryption import encrypt_value
    return encrypt_value(val)


def _dec(val: str) -> str:
    try:
        from ..utils.encryption import decrypt_value
        return decrypt_value(val)
    except Exception:
        return val


def _build_credentials(token_row: GoogleCalendarToken):
    from google.oauth2.credentials import Credentials
    token_data = json.loads(_dec(token_row.token_json))
    return Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=Config.GOOGLE_CLIENT_ID,
        client_secret=_sv.get_secret("GOOGLE_CLIENT_SECRET"),
        scopes=_SCOPES,
        expiry=datetime.fromisoformat(token_data["expiry"]) if token_data.get("expiry") else None,
    )


def _save_credentials(user_id: int, creds, email: str | None = None) -> None:
    expiry_str = creds.expiry.isoformat() if creds.expiry else None
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "expiry": expiry_str,
    }
    token_json_enc = _enc(json.dumps(token_data))
    row = GoogleCalendarToken.query.filter_by(user_id=user_id).first()
    if row:
        row.token_json = token_json_enc
        row.updated_at = datetime.utcnow()
        if email:
            row.email = email
    else:
        row = GoogleCalendarToken(user_id=user_id, token_json=token_json_enc, email=email or "")
        db.session.add(row)
    db.session.commit()


def _iso_utc(dt) -> str:
    """RFC3339 UTC timestamp for the Google Calendar API. Treats a naive
    datetime as UTC (extraction stores naive-UTC scheduled_at)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat() + "Z"


def _calendar_service(user_id: int):
    """Build an authorized Calendar API client for a user, refreshing the token
    if needed. Returns None if the user hasn't connected Google Calendar."""
    row = GoogleCalendarToken.query.filter_by(user_id=user_id).first()
    if not row:
        return None
    from googleapiclient.discovery import build as _gcal_build
    from google.auth.transport.requests import Request

    creds = _build_credentials(row)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(user_id, creds, row.email)
    return _gcal_build("calendar", "v3", credentials=creds)


def push_hub_meeting_to_calendar(user_id: int, meeting):
    """Insert an Echo Hub meeting (HubMeeting) as a Google Calendar event.

    Returns the created event dict, or None if the meeting has no date or the
    user hasn't connected Calendar. Raises on a genuine API failure so callers
    can decide whether to retry. Does NOT flip calendar_pushed — the caller owns
    that, after a successful commit."""
    if not getattr(meeting, "scheduled_at", None):
        return None
    service = _calendar_service(user_id)
    if service is None:
        return None

    from ..assistant.hub_crypto import _dec as _dec_hub
    start_dt = meeting.scheduled_at
    end_dt = start_dt + timedelta(hours=1)
    title = (_dec_hub(meeting.title) or "Meeting")[:200]
    participants = meeting.participants or []
    desc = ["Synced from Telegizer Echo."]
    if participants:
        desc.append(f"With: {', '.join(str(p) for p in participants)}")
    if meeting.meeting_url:
        desc.append(f"Link: {meeting.meeting_url}")

    event = {
        "summary": title,
        "description": "\n".join(desc),
        "start": {"dateTime": _iso_utc(start_dt), "timeZone": "UTC"},
        "end":   {"dateTime": _iso_utc(end_dt),   "timeZone": "UTC"},
        # One tidy event, but with native Google reminders mirroring the Telegram
        # ladder (1 day / 3 hr / 1 hr / 10 min) so Calendar also nudges the user —
        # without creating multiple events. Google caps overrides at 5.
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 1440},
                {"method": "popup", "minutes": 180},
                {"method": "popup", "minutes": 60},
                {"method": "popup", "minutes": 10},
            ],
        },
    }
    if meeting.meeting_url:
        event["location"] = meeting.meeting_url
    return service.events().insert(calendarId="primary", body=event).execute()


# ── Routes ────────────────────────────────────────────────────────────────────


@calendar_bp.route("/auth-url", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def get_auth_url():
    """Return the Google OAuth authorization URL."""
    if not _is_configured():
        return jsonify({"error": "Google Calendar not configured on this server"}), 501

    user = _current_user()
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(_client_config(), scopes=_SCOPES)
    flow.redirect_uri = Config.GOOGLE_REDIRECT_URI

    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=str(user.id),
    )
    return jsonify({"auth_url": auth_url})


@calendar_bp.route("/callback", methods=["GET"])
def oauth_callback():
    """Google redirects here after user consent. Stores tokens and redirects to dashboard."""
    if not _is_configured():
        frontend_url = getattr(Config, "FRONTEND_URL", "")
        return redirect(f"{frontend_url}/settings?calendar=error&reason=not_configured")

    state = request.args.get("state", "")
    code = request.args.get("code")
    error = request.args.get("error")
    frontend_url = getattr(Config, "FRONTEND_URL", "")

    if error or not code or not state.isdigit():
        return redirect(f"{frontend_url}/settings?calendar=error&reason={error or 'missing_code'}")

    user_id = int(state)
    try:
        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build as _gcal_build

        flow = Flow.from_client_config(_client_config(), scopes=_SCOPES, state=state)
        flow.redirect_uri = Config.GOOGLE_REDIRECT_URI
        flow.fetch_token(code=code)
        creds = flow.credentials

        # Get user's Google email — best-effort. Never let a userinfo hiccup
        # break an otherwise-successful Calendar connection.
        email = ""
        try:
            service = _gcal_build("oauth2", "v2", credentials=creds)
            user_info = service.userinfo().get().execute()
            email = user_info.get("email", "")
        except Exception as einfo:
            _log.warning("could not fetch Google email for user %s: %s", user_id, einfo)

        _save_credentials(user_id, creds, email)
        return redirect(f"{frontend_url}/settings?calendar=connected")
    except Exception as exc:
        _log.error("Google Calendar OAuth callback failed for user %s: %s", user_id, exc)
        return redirect(f"{frontend_url}/settings?calendar=error&reason=oauth_failed")


@calendar_bp.route("/status", methods=["GET"])
@jwt_required()
def calendar_status():
    """Return whether Google Calendar is connected for this user."""
    user = _current_user()
    row = GoogleCalendarToken.query.filter_by(user_id=user.id).first()
    if not row:
        return jsonify({"connected": False, "configured": _is_configured()})
    return jsonify({
        "connected": True,
        "email": row.email or "",
        "configured": _is_configured(),
        "auto_sync_meetings": bool(getattr(row, "auto_sync_meetings", False)),
    })


@calendar_bp.route("/settings", methods=["PATCH"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def update_calendar_settings():
    """Toggle calendar preferences (currently: auto-sync new Echo meetings)."""
    user = _current_user()
    row = GoogleCalendarToken.query.filter_by(user_id=user.id).first()
    if not row:
        return jsonify({"error": "Google Calendar not connected"}), 400
    body = request.get_json(silent=True) or {}
    if "auto_sync_meetings" in body:
        row.auto_sync_meetings = bool(body["auto_sync_meetings"])
    db.session.commit()
    return jsonify({"auto_sync_meetings": bool(row.auto_sync_meetings)})


@calendar_bp.route("/events", methods=["GET"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def list_calendar_events():
    """Return upcoming events from user's Google Calendar."""
    user = _current_user()
    row = GoogleCalendarToken.query.filter_by(user_id=user.id).first()
    if not row:
        return jsonify({"error": "Google Calendar not connected"}), 400

    try:
        from googleapiclient.discovery import build as _gcal_build
        from google.auth.transport.requests import Request

        creds = _build_credentials(row)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_credentials(user.id, creds, row.email)

        service = _gcal_build("calendar", "v3", credentials=creds)
        now_iso = datetime.now(timezone.utc).isoformat()
        result = service.events().list(
            calendarId="primary",
            timeMin=now_iso,
            maxResults=20,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = []
        for e in result.get("items", []):
            start = e.get("start", {})
            events.append({
                "id": e.get("id"),
                "summary": e.get("summary", "(no title)"),
                "start": start.get("dateTime") or start.get("date"),
                "end": (e.get("end") or {}).get("dateTime") or (e.get("end") or {}).get("date"),
                "html_link": e.get("htmlLink"),
                "location": e.get("location"),
            })
        return jsonify({"events": events})
    except Exception as exc:
        _log.warning("calendar events fetch failed for user %s: %s", user.id, exc)
        return jsonify({"error": "Failed to fetch calendar events"}), 502


@calendar_bp.route("/sync-reminder/<int:reminder_id>", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def sync_reminder_to_calendar(reminder_id):
    """Push a workspace reminder as a Google Calendar event."""
    from ..models import WorkspaceReminder
    user = _current_user()
    row = GoogleCalendarToken.query.filter_by(user_id=user.id).first()
    if not row:
        return jsonify({"error": "Google Calendar not connected"}), 400

    reminder = WorkspaceReminder.query.filter_by(id=reminder_id, owner_user_id=user.id).first_or_404()

    try:
        from googleapiclient.discovery import build as _gcal_build
        from google.auth.transport.requests import Request

        creds = _build_credentials(row)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_credentials(user.id, creds, row.email)

        service = _gcal_build("calendar", "v3", credentials=creds)
        start_dt = reminder.remind_at
        end_dt = start_dt + timedelta(minutes=30)

        event = {
            "summary": reminder.reminder_text[:200],
            "description": "Synced from Telegizer",
            "start": {"dateTime": start_dt.isoformat() + "Z", "timeZone": "UTC"},
            "end":   {"dateTime": end_dt.isoformat() + "Z",   "timeZone": "UTC"},
        }
        created = service.events().insert(calendarId="primary", body=event).execute()
        return jsonify({"event_id": created.get("id"), "html_link": created.get("htmlLink")})
    except Exception as exc:
        _log.warning("calendar sync failed for user %s reminder %s: %s", user.id, reminder_id, exc)
        return jsonify({"error": "Failed to sync to Google Calendar"}), 502


@calendar_bp.route("/sync-meeting-link/<int:link_id>", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=10)
def sync_meeting_link_to_calendar(link_id):
    """Create a Google Calendar event from a captured meeting link."""
    from ..assistant.hub_models import HubMeeting
    user = _current_user()
    row = GoogleCalendarToken.query.filter_by(user_id=user.id).first()
    if not row:
        return jsonify({"error": "Google Calendar not connected"}), 400

    link = HubMeeting.query.filter_by(id=link_id, user_id=user.id).first_or_404()

    try:
        from googleapiclient.discovery import build as _gcal_build
        from google.auth.transport.requests import Request

        creds = _build_credentials(row)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_credentials(user.id, creds, row.email)

        service = _gcal_build("calendar", "v3", credentials=creds)
        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=1)
        title = f"Meeting: {link.group_title or 'Group'}" if link.group_title else "Meeting"
        context = link.context_text or link.url

        event = {
            "summary": title,
            "description": f"Captured from Telegram group.\n\nLink: {link.url}\n\nContext: {context}\n\nSynced via Telegizer",
            "start": {"dateTime": now.isoformat(), "timeZone": "UTC"},
            "end":   {"dateTime": end.isoformat(), "timeZone": "UTC"},
        }
        created = service.events().insert(calendarId="primary", body=event).execute()
        return jsonify({"event_id": created.get("id"), "html_link": created.get("htmlLink")})
    except Exception as exc:
        _log.warning("calendar sync-meeting-link failed for user %s link %s: %s", user.id, link_id, exc)
        return jsonify({"error": "Failed to sync to Google Calendar"}), 502


@calendar_bp.route("/sync-hub-meeting/<meeting_id>", methods=["POST"])
@jwt_required()
@rate_limit(requests_per_minute=20)
def sync_hub_meeting(meeting_id):
    """Create a Google Calendar event from an Echo Hub meeting (HubMeeting)."""
    from ..assistant.hub_models import HubMeeting
    user = _current_user()
    if not GoogleCalendarToken.query.filter_by(user_id=user.id).first():
        return jsonify({"error": "Google Calendar not connected"}), 400

    meeting = HubMeeting.query.filter_by(id=meeting_id, user_id=user.id).first_or_404()
    if not meeting.scheduled_at:
        return jsonify({"error": "This meeting has no date yet — set a date before syncing."}), 400

    try:
        created = push_hub_meeting_to_calendar(user.id, meeting)
        if not created:
            return jsonify({"error": "Google Calendar not connected"}), 400
        meeting.calendar_pushed = True
        db.session.commit()
        return jsonify({
            "event_id": created.get("id"),
            "html_link": created.get("htmlLink"),
            "calendar_pushed": True,
        })
    except Exception as exc:
        db.session.rollback()
        _log.warning("calendar sync-hub-meeting failed user=%s meeting=%s: %s", user.id, meeting_id, exc)
        return jsonify({"error": "Failed to sync to Google Calendar"}), 502


@calendar_bp.route("/disconnect", methods=["DELETE"])
@jwt_required()
def disconnect_calendar():
    """Revoke Google OAuth tokens and delete from DB."""
    user = _current_user()
    row = GoogleCalendarToken.query.filter_by(user_id=user.id).first()
    if not row:
        return jsonify({"ok": True})

    try:
        from google.oauth2.credentials import Credentials
        import requests as _req
        creds = _build_credentials(row)
        if creds.token:
            _req.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": creds.token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=5,
            )
    except Exception:
        pass

    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True})
