from datetime import datetime
from .models import db, Group, Member, AuditLog, Bot, User
from .group_defaults import get_group_default_settings
from .config import Config


def get_default_settings():
    """Return canonical group defaults. Delegates to group_defaults so both
    the official bot and legacy custom-bot groups stay in sync."""
    return get_group_default_settings()


class DatabaseManager:

    @staticmethod
    def get_or_create_group(bot_id, telegram_group_id, group_name=None,
                             member_count=None, chat_type="group", chat_username=None):
        # Never create a Group record for private chats — custom bots observe only.
        if chat_type == "private":
            return None

        group = Group.query.filter_by(
            bot_id=bot_id,
            telegram_group_id=str(telegram_group_id),
        ).first()

        if not group:
            # Enforce per-plan group limit for custom bots
            bot = Bot.query.get(bot_id)
            if bot:
                user = User.query.get(bot.user_id)
                tier = user.subscription_tier if user else "free"
                max_groups = Config.MAX_GROUPS_PER_CUSTOM_BOT.get(tier, 3)
                if max_groups != -1:
                    current_count = Group.query.filter_by(
                        bot_id=bot_id
                    ).filter(Group.chat_type != "private").count()
                    if current_count >= max_groups:
                        raise PermissionError(
                            f"Group limit reached. Your {tier.capitalize()} plan allows "
                            f"{max_groups} group(s) per custom bot. "
                            "Upgrade to Pro for unlimited groups."
                        )

            group = Group(
                bot_id=bot_id,
                telegram_group_id=str(telegram_group_id),
                group_name=group_name or str(telegram_group_id),
                settings=get_default_settings(),
                telegram_member_count=member_count or 0,
                chat_type=chat_type,
                chat_username=chat_username,
            )
            db.session.add(group)
            db.session.commit()
        else:
            changed = False
            if group_name and group.group_name != group_name:
                group.group_name = group_name
                changed = True
            if member_count and group.telegram_member_count != member_count:
                group.telegram_member_count = member_count
                changed = True
            if chat_username is not None and group.chat_username != chat_username:
                group.chat_username = chat_username
                changed = True
            if changed:
                db.session.commit()

        return group

    @staticmethod
    def get_or_create_member(group_id, telegram_user_id, username=None, first_name=None, last_name=None):
        member = Member.query.filter_by(
            group_id=group_id,
            telegram_user_id=str(telegram_user_id),
        ).first()

        if not member:
            member = Member(
                group_id=group_id,
                telegram_user_id=str(telegram_user_id),
                username=username,
                first_name=first_name or str(telegram_user_id),
                last_name=last_name,
            )
            db.session.add(member)
            db.session.commit()
        else:
            changed = False
            if username and member.username != username:
                member.username = username
                changed = True
            if first_name and member.first_name != first_name:
                member.first_name = first_name
                changed = True
            if last_name is not None and member.last_name != last_name:
                member.last_name = last_name
                changed = True
            if changed:
                db.session.commit()

        return member

    @staticmethod
    def add_xp(group_id, telegram_user_id, xp_amount, username=None, first_name=None):
        member = DatabaseManager.get_or_create_member(
            group_id, telegram_user_id, username, first_name
        )

        old_level = member.level
        member.xp += xp_amount
        member.last_xp_at = datetime.utcnow()

        new_level = DatabaseManager._calculate_level(member.xp)
        member.level = new_level

        group = Group.query.get(group_id)
        if group:
            roles = group.settings.get("levels", {}).get("roles", [])
            assigned_role = "member"
            for role_cfg in sorted(roles, key=lambda r: r["level"], reverse=True):
                if new_level >= role_cfg["level"]:
                    assigned_role = role_cfg["name"].lower().replace(" ", "_")
                    break
            member.role = assigned_role

        db.session.commit()
        leveled_up = new_level > old_level
        return member, leveled_up, new_level

    @staticmethod
    def _calculate_level(xp):
        level = 1
        xp_needed = 100
        while xp >= xp_needed:
            xp -= xp_needed
            level += 1
            xp_needed = int(xp_needed * 1.5)
        return level

    @staticmethod
    def add_warning(group_id, target_user_id, target_username, moderator_id, moderator_username, reason):
        member = DatabaseManager.get_or_create_member(group_id, target_user_id, target_username)
        member.warnings += 1
        db.session.commit()

        DatabaseManager.log_action(
            group_id=group_id,
            action_type="warn",
            target_user_id=str(target_user_id),
            target_username=target_username,
            moderator_id=str(moderator_id),
            moderator_username=moderator_username,
            reason=reason,
            extra_data={"total_warnings": member.warnings},
        )

        return member.warnings

    @staticmethod
    def apply_xp_penalty(group_id, telegram_user_id, penalty_xp):
        member = Member.query.filter_by(
            group_id=group_id,
            telegram_user_id=str(telegram_user_id),
        ).first()
        if member and penalty_xp < 0:
            member.xp = max(0, member.xp + penalty_xp)
            member.level = DatabaseManager._calculate_level(member.xp)
            db.session.commit()

    @staticmethod
    def count_warnings_in_window(group_id, target_user_id, hours):
        from datetime import timedelta
        since = datetime.utcnow() - timedelta(hours=hours)
        return AuditLog.query.filter(
            AuditLog.group_id == group_id,
            AuditLog.target_user_id == str(target_user_id),
            AuditLog.action_type == "warn",
            AuditLog.timestamp >= since,
        ).count()

    @staticmethod
    def log_action(group_id, action_type, target_user_id=None, target_username=None,
                   moderator_id=None, moderator_username=None, reason=None, extra_data=None):
        log = AuditLog(
            group_id=group_id,
            action_type=action_type,
            target_user_id=str(target_user_id) if target_user_id else None,
            target_username=target_username,
            moderator_id=str(moderator_id) if moderator_id else None,
            moderator_username=moderator_username,
            reason=reason,
            extra_data=extra_data,
        )
        db.session.add(log)
        db.session.commit()
        return log
