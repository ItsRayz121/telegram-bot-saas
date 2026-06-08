"""
Bot-agnostic message forwarding (D3).

Called from BOTH the official bot and every custom bot's message handler, so
forwarding works identically across lineages (the engine takes a `bot`; only the
call sites differ). Supports:

  • many sources / many destinations per rule (D4 / O3, via ForwardSource / ForwardDestination)
  • forum topics: source-topic filter + per-destination topic target (D5)
  • keyword filter + match type, prefix/suffix templating
  • the approval queue (require_approval → pending_approval logs)
  • the anti-ban governor (D7) on every send, with per-destination auto-pause

Design note: DB reads (gather rules) and DB writes (logs / counters / pauses)
happen inside `flask_app.app_context()`, but the actual network sends run OUTSIDE
the app context so a slow Telegram call never holds a DB session open.
"""
import logging
import re
import time
from collections import deque

from .anti_ban import get_governor, is_fatal_destination_error

_log = logging.getLogger(__name__)

# ── Anti-ban backstops (D7 / Phase 5) ─────────────────────────────────────────
MAX_FORWARDS_PER_MIN_PER_RULE = 20   # per-rule throughput cap (on top of the governor)
FAIL_PAUSE_THRESHOLD = 5             # consecutive non-fatal failures → auto-pause

# Per-rule sliding-window send timestamps (in-memory, per process).
_rule_send_times: dict[int, deque] = {}


def _rule_rate_ok(rule_id) -> bool:
    """Token-free sliding-window check: True if this rule may send another forward
    in the last 60s, recording the send. A backstop above the per-chat governor so
    a single misconfigured rule can't fan out abusively."""
    now = time.monotonic()
    dq = _rule_send_times.setdefault(rule_id, deque())
    cutoff = now - 60.0
    while dq and dq[0] < cutoff:
        dq.popleft()
    if len(dq) >= MAX_FORWARDS_PER_MIN_PER_RULE:
        return False
    dq.append(now)
    return True


# ── Topic-link parsing (D5) ───────────────────────────────────────────────────
# Telegram's Bot API cannot enumerate a chat's topics, so users paste a link and
# we extract the message_thread_id. Handles:
#   https://t.me/c/2031234567/45          (private supergroup topic)
#   https://t.me/c/2031234567/45/678      (a message inside that topic)
#   https://t.me/mygroup/45               (public group topic)
#   45                                    (a bare thread id)
_TOPIC_RE = re.compile(r"t\.me/(?:c/\d+|[A-Za-z0-9_]+)/(\d+)")


def parse_topic_link(value) -> int | None:
    """Return the message_thread_id from a Telegram topic link, or None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    m = _TOPIC_RE.search(s)
    if m:
        return int(m.group(1))
    return None


# ── Matching helpers ──────────────────────────────────────────────────────────

def _matches_keyword(rule, text: str) -> bool:
    if not rule.keyword_filter:
        return True
    keywords = [k.strip().lower() for k in rule.keyword_filter.split(",") if k.strip()]
    if not keywords:
        return True
    t = (text or "").lower()
    if rule.match_type == "starts_with":
        return any(t.startswith(k) for k in keywords)
    return any(k in t for k in keywords)


def _source_matches(rule, group_id, thread_id) -> bool:
    """True if this rule should fire for a message in `group_id` / `thread_id`."""
    for src in rule.effective_sources():
        if str(src["chat_id"]) != str(group_id):
            continue
        topic = src.get("topic_id")
        if topic is None:
            return True  # no topic filter → any topic in this chat
        if thread_id is not None and int(topic) == int(thread_id):
            return True
        # rule wants a specific topic but the message is elsewhere/none → keep looking
    return False


def _build_text(prefix, body, suffix) -> str:
    return "\n".join(p for p in (prefix, body, suffix) if p)


# ── Single delivery (shared by live + approval paths) ─────────────────────────

async def _deliver(bot, governor, *, destination_id, topic_id, prefix, suffix,
                   from_chat_id, message_id, body_text):
    """Send one message to one destination through the governor. Raises on failure."""
    if prefix or suffix:
        text = _build_text(prefix, body_text, suffix)

        async def _coro():
            return await bot.send_message(
                chat_id=destination_id, text=text, message_thread_id=topic_id,
            )
    else:
        async def _coro():
            return await bot.copy_message(
                chat_id=destination_id, from_chat_id=from_chat_id,
                message_id=message_id, message_thread_id=topic_id,
            )

    return await governor.send(destination_id, _coro)


# ── Live path: called from message handlers ───────────────────────────────────

async def run_forwarding(flask_app, bot, group_id, message, *, bot_type="official",
                         owner_bot_id=None):
    """Evaluate + execute every active forward rule whose source matches this
    message's chat (and topic). Safe to call from any bot's handler.

    Mirrors the original official-bot inline logic, plus many→many, topics, and
    the governor. Unfiltered rules now also relay media (no text); keyword-filtered
    rules still require matching text, exactly as before.
    """
    if not flask_app:
        return

    text = message.text or message.caption or ""
    thread_id = getattr(message, "message_thread_id", None)
    governor = get_governor(bot)

    snippet = text[:500] if text else None
    jobs = []          # immediate deliveries to perform outside app context
    pending_logs = 0   # count for logging

    # ── Pass 1: read rules, decide what to do (inside app context) ──
    try:
        with flask_app.app_context():
            from ..models import db, ForwardRule, ForwardSource, ForwardLog

            # Candidate rules: those with a ForwardSource row for this chat, plus
            # legacy rules whose single source column points here.
            rule_ids = {
                s.rule_id for s in
                ForwardSource.query.filter_by(source_chat_id=str(group_id)).all()
            }
            candidates = {}
            if rule_ids:
                for r in ForwardRule.query.filter(
                    ForwardRule.id.in_(rule_ids), ForwardRule.is_active.is_(True)
                ).all():
                    candidates[r.id] = r
            for r in ForwardRule.query.filter_by(
                source_group_id=str(group_id), is_active=True
            ).all():
                candidates.setdefault(r.id, r)

            for rule in candidates.values():
                if not _source_matches(rule, group_id, thread_id):
                    continue
                if not _matches_keyword(rule, text):
                    continue

                for dest in rule.effective_destinations():
                    if dest.get("is_paused"):
                        continue
                    if rule.require_approval:
                        db.session.add(ForwardLog(
                            rule_id=rule.id,
                            source_chat_id=str(group_id),
                            source_message_id=message.message_id,
                            source_text=snippet,
                            destination_id=dest["destination_id"],
                            destination_topic_id=dest.get("topic_id"),
                            bot_id=owner_bot_id,
                            status="pending_approval",
                        ))
                        pending_logs += 1
                    else:
                        jobs.append({
                            "rule_id": rule.id,
                            "dest_row_id": dest.get("id"),
                            "destination_id": dest["destination_id"],
                            "topic_id": dest.get("topic_id"),
                            "prefix": rule.prefix_text,
                            "suffix": rule.suffix_text,
                        })
            if pending_logs:
                db.session.commit()
    except Exception as exc:
        _log.debug("run_forwarding pass-1 failed for group %s: %s", group_id, exc)
        return

    if not jobs:
        return

    # ── Pass 2: send (outside app context) ──
    results = []
    for job in jobs:
        # Per-rule throughput backstop — skip (don't fail) if the rule is hot.
        if not _rule_rate_ok(job["rule_id"]):
            _log.warning(
                "Anti-ban: rule %s hit %d forwards/min cap — skipping further sends this minute",
                job["rule_id"], MAX_FORWARDS_PER_MIN_PER_RULE,
            )
            continue
        ok, err, fatal = True, None, False
        try:
            await _deliver(
                bot, governor,
                destination_id=job["destination_id"],
                topic_id=job["topic_id"],
                prefix=job["prefix"],
                suffix=job["suffix"],
                from_chat_id=group_id,
                message_id=message.message_id,
                body_text=text,
            )
        except Exception as exc:  # noqa: BLE001
            ok = False
            err = str(exc)[:500]
            fatal = is_fatal_destination_error(exc)
            _log.debug("Forward failed rule=%s dest=%s: %s",
                       job["rule_id"], job["destination_id"], exc)
        results.append({**job, "ok": ok, "err": err, "fatal": fatal})

    if not results:
        return

    # ── Pass 3: persist logs / counters / pauses (inside app context) ──
    paused_notes = []  # (rule_id, destination_id, reason) for user-facing notice
    try:
        with flask_app.app_context():
            from ..models import db, ForwardRule, ForwardLog, ForwardDestination
            for res in results:
                db.session.add(ForwardLog(
                    rule_id=res["rule_id"],
                    source_chat_id=str(group_id),
                    source_message_id=message.message_id,
                    source_text=snippet,
                    destination_id=res["destination_id"],
                    destination_topic_id=res["topic_id"],
                    bot_id=owner_bot_id,
                    status="forwarded" if res["ok"] else "failed",
                    error_msg=res["err"],
                ))
                rule = ForwardRule.query.get(res["rule_id"])
                if rule and res["ok"]:
                    rule.forward_count = (rule.forward_count or 0) + 1
                if res["dest_row_id"]:
                    drow = ForwardDestination.query.get(res["dest_row_id"])
                    if drow:
                        if res["ok"]:
                            drow.forward_count = (drow.forward_count or 0) + 1
                            drow.last_error = None
                            drow.fail_count = 0
                        else:
                            drow.last_error = res["err"]
                            drow.fail_count = (drow.fail_count or 0) + 1
                            # Fatal (bot removed / no rights) pauses at once;
                            # repeated transient failures pause after a threshold.
                            if (res["fatal"] or drow.fail_count >= FAIL_PAUSE_THRESHOLD) \
                                    and not drow.is_paused:
                                drow.is_paused = True
                                drow.pause_reason = (
                                    "auto-paused: destination unreachable"
                                    if res["fatal"] else
                                    f"auto-paused after {drow.fail_count} consecutive failures"
                                )
                                paused_notes.append(
                                    (res["rule_id"], res["destination_id"], drow.pause_reason)
                                )
            db.session.commit()
    except Exception as exc:
        _log.debug("run_forwarding pass-3 failed for group %s: %s", group_id, exc)
        return

    # ── User-facing notice for auto-paused destinations (dashboard AI Activity) ──
    for rule_id, dest_id, reason in paused_notes:
        _log.info("Anti-ban: paused forwarding rule=%s dest=%s (%s)", rule_id, dest_id, reason)
        try:
            from ..ai_activity import log_ai_activity
            log_ai_activity(
                bot_type, str(group_id), "automation",
                f"⚠️ Forwarding paused to {dest_id}",
                detail=reason, status="failed", source="forwarding",
            )
        except Exception:
            pass


# ── Approval path: deliver a previously-queued pending log ────────────────────

async def deliver_pending_log(bot, rule, log_entry):
    """Forward an approved pending log through the governor. Returns (ok, error).

    Used by the forwarding approval API once it has resolved the owning bot.
    Pure send — the caller persists status changes.
    """
    governor = get_governor(bot)
    try:
        if rule.prefix_text or rule.suffix_text:
            text = _build_text(rule.prefix_text, log_entry.source_text, rule.suffix_text)

            async def _coro():
                return await bot.send_message(
                    chat_id=log_entry.destination_id, text=text,
                    message_thread_id=log_entry.destination_topic_id,
                )
        else:
            async def _coro():
                return await bot.copy_message(
                    chat_id=log_entry.destination_id,
                    from_chat_id=log_entry.source_chat_id,
                    message_id=log_entry.source_message_id,
                    message_thread_id=log_entry.destination_topic_id,
                )
        await governor.send(log_entry.destination_id, _coro)
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:500]
