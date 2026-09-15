"""Shared ChatPermissions constant for "fully restore a member's permissions"
(verification success, /unmute, admin unmute action).

Telegram's Bot API replaced the single `can_send_media_messages` flag with six
granular ones (`can_send_audios`/`documents`/`photos`/`videos`/`video_notes`/
`voice_notes`) back in Bot API 6.4 / python-telegram-bot 20.5 — this repo pins
21.3, which never had `can_send_media_messages` in the first place. Before this
module existed, the six-flag expansion (plus `can_send_polls`) was copy-pasted
at four call sites, three of which were missing `can_send_polls` — meaning a
"fully unmuted" member still couldn't send polls. One shared definition so the
next time Telegram changes this API, it only needs to be fixed once.
"""
from telegram import ChatPermissions


def full_member_permissions() -> ChatPermissions:
    """A fresh ChatPermissions granting every normal-member action. Returns a
    new instance per call rather than one shared object, in case any caller
    ever expects to safely hold/mutate its own copy."""
    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
    )
