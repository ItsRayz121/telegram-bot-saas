"""
Settings resolver for Assistant Hub.

NEVER read bot settings directly from HubBotSettings without going through
get_effective_settings(). This is the single access point per the spec.
"""
from .hub_models import HubBotIdentity, HubBotSettings

_SYSTEM_DEFAULTS = {
    "ai_personality_note": "",
    "response_language": "en",
    "extraction_sensitivity": "standard",
    "digest_enabled": False,
    "digest_time": "21:00:00",
    "digest_format": "compact",
    "notification_prefs": {},
}


def get_effective_settings(bot_id: str) -> dict:
    """
    Return the resolved settings dict for a bot.

    Official bot: NULLs resolved against system defaults.
    Custom bot: NULLs resolved against official bot's effective settings.
    """
    bot = HubBotIdentity.query.get(bot_id)
    if bot is None:
        return dict(_SYSTEM_DEFAULTS)

    settings = HubBotSettings.query.filter_by(bot_id=bot_id).first()

    if bot.bot_type == "official":
        return _resolve_official(settings)

    # Custom bot — inherit NULLs from official bot
    official = HubBotIdentity.query.filter_by(
        user_id=bot.user_id, bot_type="official"
    ).first()
    official_effective = _resolve_official(
        HubBotSettings.query.filter_by(bot_id=official.id).first() if official else None
    )
    return _resolve_custom(settings, official_effective)


def _resolve_official(settings) -> dict:
    s = settings
    return {
        "ai_personality_note": (s.ai_personality_note if s and s.ai_personality_note is not None else ""),
        "response_language": (s.response_language if s and s.response_language is not None else _SYSTEM_DEFAULTS["response_language"]),
        "extraction_sensitivity": (s.extraction_sensitivity if s and s.extraction_sensitivity is not None else _SYSTEM_DEFAULTS["extraction_sensitivity"]),
        "digest_enabled": (s.digest_enabled if s and s.digest_enabled is not None else _SYSTEM_DEFAULTS["digest_enabled"]),
        "digest_time": (_fmt_time(s.digest_time) if s and s.digest_time is not None else _SYSTEM_DEFAULTS["digest_time"]),
        "digest_format": (s.digest_format if s and s.digest_format is not None else _SYSTEM_DEFAULTS["digest_format"]),
        "notification_prefs": (s.notification_prefs if s and s.notification_prefs is not None else _SYSTEM_DEFAULTS["notification_prefs"]),
    }


def _resolve_custom(settings, official: dict) -> dict:
    s = settings
    return {
        # Never inherited
        "ai_personality_note": (s.ai_personality_note if s and s.ai_personality_note is not None else ""),
        "response_language": (s.response_language if s and s.response_language is not None else "en"),
        # Inheritable
        "extraction_sensitivity": (s.extraction_sensitivity if s and s.extraction_sensitivity is not None else official["extraction_sensitivity"]),
        "digest_enabled": (s.digest_enabled if s and s.digest_enabled is not None else official["digest_enabled"]),
        "digest_time": (_fmt_time(s.digest_time) if s and s.digest_time is not None else official["digest_time"]),
        "digest_format": (s.digest_format if s and s.digest_format is not None else official["digest_format"]),
        "notification_prefs": (s.notification_prefs if s and s.notification_prefs is not None else official["notification_prefs"]),
    }


def _fmt_time(t) -> str:
    if t is None:
        return _SYSTEM_DEFAULTS["digest_time"]
    return t.strftime("%H:%M:%S") if hasattr(t, "strftime") else str(t)
