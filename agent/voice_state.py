"""Normalize Discord RPC voice metadata for the Windhawk Discord card."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def normalize(channel: dict | None, guild: dict | None, settings: dict | None,
              *, joined_at: float = 0) -> dict:
    now = time.time()
    if not isinstance(channel, dict) or not channel.get("id"):
        return {"connected": False, "updated_unix": now}

    guild = guild if isinstance(guild, dict) else {}
    settings = settings if isinstance(settings, dict) else {}
    members = []
    for row in channel.get("voice_states", [])[:100]:
        if not isinstance(row, dict):
            continue
        user = row.get("user") or {}
        uid = str(user.get("id") or "")
        if not uid.isdecimal():
            continue
        avatar = user.get("avatar")
        url = ("https://cdn.discordapp.com/avatars/" + uid + "/" +
               avatar + ".png?size=64") if isinstance(avatar, str) and avatar else ""
        members.append({
            "id": uid,
            "name": str(row.get("nick") or user.get("global_name") or
                        user.get("username") or "User")[:80],
            "avatar_url": url,
            "speaking": False,
        })

    return {
        "connected": True,
        "updated_unix": now,
        "joined_unix": joined_at or now,
        "guild_id": str(channel.get("guild_id") or ""),
        "guild_name": str(guild.get("name") or "Discord")[:128],
        "guild_icon_url": str(guild.get("icon_url") or "").replace(".webp", ".png")[:1024],
        "channel_id": str(channel["id"]),
        "channel_name": str(channel.get("name") or "Voice channel")[:128],
        "participant_count": len(channel.get("voice_states", [])),
        "participants": members[:12],
        "mic_muted": bool(settings.get("mute", False)),
        "deafened": bool(settings.get("deaf", False)),
    }


def download_icon(url: str, output: Path) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in (
        "cdn.discordapp.com", "media.discordapp.net"
    ):
        return False
    if not parsed.path.startswith(("/avatars/", "/icons/")):
        return False
    try:
        req = Request(url, headers={"User-Agent": "DynamicIslandDiscord/1.0"})
        with urlopen(req, timeout=4) as resp:
            mime = resp.headers.get("Content-Type", "")
            data = resp.read(200000)
        if len(data) >= 200000 or not mime.startswith("image/"):
            return False
        if not (data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff")):
            return False
        output.parent.mkdir(parents=True, exist_ok=True)
        tmp = output.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(output)
        return True
    except (OSError, ValueError):
        return False


def cache_images(state: dict, directory: Path) -> dict:
    for element in ([{"avatar_url": state.get("guild_icon_url", ""), "_server": True}]
                    + state.get("participants", [])):
        key = "guild_icon" if element.get("_server") else "avatar"
        url = element.get("avatar_url", "")
        if not url:
            continue
        filename = hashlib.sha256(url.encode("utf-8")).hexdigest() + ".img"
        file = directory / filename
        if (file.exists() or download_icon(url, file)):
            if element.get("_server"):
                state["guild_icon_file"] = str(file)
            else:
                element["avatar_file"] = str(file)
    return state


def atomic_state(state: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".new")
    temp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def write_windhawk_tsv(state: dict, destination: Path) -> None:
    """Stable UTF-8 wire format, with file paths limited to local avatar cache."""
    def field(value) -> str:
        return str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")[:512]

    participants = state.get("participants", [])[:12]
    lines = [
        "DISCORD1",
        "1" if state.get("connected") else "0",
        field(state.get("guild_name", "")),
        field(state.get("channel_name", "")),
        str(int(state.get("joined_unix") or 0)),
        str(int(state.get("participant_count") or 0)),
        "1" if state.get("mic_muted") else "0",
        "1" if state.get("deafened") else "0",
        field(state.get("guild_icon_file", "")),
        str(len(participants)),
    ]
    for person in participants:
        lines.extend([field(person.get("name", "")),
                      field(person.get("avatar_file", ""))])
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_suffix(".new")
    staging.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    staging.replace(destination)
