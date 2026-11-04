"""Hold severe actions for staff approval (opt-in per server).

  warn_ladder.require_approval = ["kick", "ban", "timeout"]   which ladder actions wait
  leveling2.role_reward_approval = true                       level ranks wait

`gate_*` run in the bot (sync, via to_thread). They only QUEUE; nothing is executed until a
staff member approves in the dashboard (approvals_api.py). Default is off, so every
existing server keeps acting immediately.
"""
from __future__ import annotations

from models import ModApproval


def needs_approval(warn_ladder: dict | None, action: str) -> bool:
    return action in set((warn_ladder or {}).get("require_approval") or [])


def queue(db, guild_id: int, user_id: int, username, kind: str, *, role_id=None, minutes=None, reason=None):
    """Create a pending approval unless an identical one is already pending (a ladder
    retry or a re-run sweep must not stack duplicates). Returns (row, created)."""
    q = db.query(ModApproval).filter_by(guild_id=guild_id, user_id=user_id, kind=kind)
    if kind == "rank":
        # a rank is asked about once per member+role, whatever the earlier answer was
        dup = q.filter(ModApproval.role_id == role_id).first()
    else:
        dup = q.filter(ModApproval.status.in_(("pending", "reviewing"))).first()
    if dup is not None:
        return dup, False
    row = ModApproval(guild_id=guild_id, user_id=user_id, username=(username or "")[:120] or None,
                      kind=kind, role_id=role_id, minutes=minutes, reason=(reason or "")[:300] or None)
    db.add(row)
    db.flush()
    return row, True


def hold_escalation(guild_id: int, user_id: int, username, esc: dict, warn_ladder: dict | None) -> bool:
    """Sync (call via to_thread). If this escalation's action must wait for staff, queue it
    and return True - the caller then skips the Discord action (and any warning reset)."""
    action = (esc or {}).get("action")
    if not needs_approval(warn_ladder, action):
        return False
    from database import SessionLocal
    db = SessionLocal()
    try:
        queue(db, guild_id, user_id, username, action, minutes=esc.get("minutes"),
              reason=f"Reached warning {esc.get('at', '?')}")
        db.commit()
        return True
    except Exception:  # noqa: BLE001 - if we can't record it, do NOT silently skip the action
        db.rollback()
        return False
    finally:
        db.close()
        SessionLocal.remove()


def hold_rank(guild_id: int, user_id: int, username, role_id: int) -> None:
    """Sync. Queue a level rank for approval (once per member+role)."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        queue(db, guild_id, user_id, username, "rank", role_id=role_id, reason="Reached a level milestone")
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()
        SessionLocal.remove()
