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

calendar_bp = Blueprint("calendar", __name__, url_prefix="/api/calendar")

_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

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

        # Get user's Google email
        service = _gcal_build("oauth2", "v2", credentials=creds)
        user_info = service.userinfo().get().execute()
        email = user_info.get("email", "")

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
        return jsonify({"connected": False})
    return jsonify({
        "connected": True,
        "email": row.email or "",
        "configured": _is_configured(),
    })


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
