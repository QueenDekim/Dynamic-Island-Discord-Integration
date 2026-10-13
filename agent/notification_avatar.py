"""Extract/cache the sender's avatar from a Discord RPC notification.

The RPC notification may contain message.author or top-level author/user.
Never fetch arbitrary endpoints: only Discord's CDN with avatar paths.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

from voice_state import download_icon


def avatar_url(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    message = payload.get("message")
    if not isinstance(message, dict):
        message = {}
    author = message.get("author") or payload.get("author") or payload.get("user")
    if not isinstance(author, dict):
        author = {}
    uid = str(author.get("id") or "")
    avatar = author.get("avatar")
    if uid.isdecimal():
        if isinstance(avatar, str) and avatar and all(
            c in "0123456789abcdefABCDEF_" for c in avatar
        ):
            return f"https://cdn.discordapp.com/avatars/{uid}/{avatar}.png?size=64"
    # Prefer Discord's supplied sender icon before falling back to the
    # user's deterministic default avatar (some RPC events omit author.avatar).
    for candidate in (
        payload.get("icon_url"), payload.get("avatar_url"),
        message.get("icon_url"), author.get("avatar_url"),
    ):
        if not isinstance(candidate, str):
            continue
        url = urlparse(candidate)
        if (url.scheme == "https" and url.hostname in
                {"cdn.discordapp.com", "media.discordapp.net"} and
                url.path.startswith(("/avatars/", "/embed/avatars/")) and
                not url.username and not url.password):
            return candidate
    if uid.isdecimal() and not avatar:
        default_index = (int(uid) >> 22) % 6
        return f"https://cdn.discordapp.com/embed/avatars/{default_index}.png"
    return ""


def cached_notification_avatar(payload: dict, directory: Path) -> str:
    url = avatar_url(payload)
    if not url:
        return ""
    cached = directory / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".img")
    if cached.is_file():
        return str(cached)
    return str(cached) if download_icon(url, cached) else ""
