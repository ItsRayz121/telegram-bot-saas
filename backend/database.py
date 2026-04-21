from datetime import datetime
from .models import db, Group, Member, AuditLog


def get_default_settings():
    return {
        "verification": {
            "enabled": False,
            "method": "button",
            "timeout_seconds": 60,
            "kick_on_fail": True,
            "custom_question": "",
            "custom_answer": "",
        },
        "welcome": {
            "enabled": True,
            "message": "Welcome {first_name} to {group_name}! 👋\nYou are member #{member_count}.",
            "media_url": "",
            "delete_after_seconds": 0,
            "show_rules": False,
            "rules_text": "",
        },
        "levels": {
            "enabled": True,
            "xp_per_message": 10,
            "xp_cooldown_seconds": 60,
            "level_up_message": "🎉 {first_name} leveled up to level {level}!",
            "announce_level_up": True,
            "roles": [
                {"level": 1, "name": "Newcomer"},
                {"level": 5, "name": "Member"},
                {"level": 10, "name": "Regular"},
                {"level": 25, "name": "Veteran"},
                {"level": 50, "name": "Elite"},
                {"level": 100, "name": "Legend"},
            ],
        },
        "automod": {
            "enabled": True,
            "bad_words": {
                "enabled": False,
                "words": [],
                "action": "delete",
                "warn_user": True,
            },
            "spam": {
                "enabled": True,
                "max_messages": 5,
                "time_window_seconds": 10,
                "action": "mute",
                "mute_duration_minutes": 10,
            },
            "external_links": {
                "enabled": False,
                "whitelist": [],
                "action": "delete",
            },
            "telegram_links": {
                "enabled": False,
                "action": "delete",
                "warn_user": True,
            },
            "excessive_emojis": {
                "enabled": False,
                "max_emojis": 10,
                "action": "delete",
            },
            "caps_lock": {
                "enabled": False,
                "threshold_percent": 70,
                "min_length": 10,
                "action": "delete",
            },
            "forwarded_messages": {
                "enabled": False,
                "action": "delete",
            },
        },
        "moderation": {
            "max_warnings": 3,
            "warning_action": "ban",
            "mute_duration_minutes": 60,
            "ban_delete_days": 1,
            "notify_on_action": True,
            "log_to_channel": False,
            "log_channel_id": "",
        },
        "raids": {
            "enabled": True,
            "default_duration_hours": 24,
            "default_xp_reward": 100,
        },
    }


class DatabaseManager:

    @staticmethod
    def get_or_create_group(bot_id, telegram_group_id, group_name=None):
        group = Group.query.filter_by(
            bot_id=bot_id,
            telegram_group_id=str(telegram_group_id),
        ).first()

        if not group:
            group = Group(
                bot_id=bot_id,
                telegram_group_id=str(telegram_group_id),
                group_name=group_name or str(telegram_group_id),
                settings=get_default_settings(),
            )
            db.session.add(group)
            db.session.commit()
        elif group_name and group.group_name != group_name:
            group.group_name = group_name
            db.session.commit()

        return group

    @staticmethod
    def get_or_create_member(group_id, telegram_user_id, username=None, first_name=None):
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
