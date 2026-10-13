"""Small on-disk protocol between the local Discord agent and Windhawk."""
import os
from pathlib import Path
import time
from notification_avatar import cached_notification_avatar

BASE = Path(os.environ["LOCALAPPDATA"]) / "DynamicIslandDiscord"
STATUS = BASE / "status.tsv"
COMMAND = BASE / "command.txt"
NOTICE = BASE / "notification.tsv"
VOICE = BASE / "state.tsv"
TOKEN = BASE / "oauth.dpapi"


def field(value, max_length=512):
    text = str(value or "")[:max_length]
    return "".join(" " if c in "\r\n\t\x00" else c for c in text)


def atomic_lines(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".new")
    # Use an explicit LF wire format on every platform.
    temporary.write_bytes(("\n".join(map(str, lines)) + "\n").encode("utf-8"))
    temporary.replace(path)


def publish_status(mode, error=""):
    atomic_lines(STATUS, ["DISCORDSTATUS1", field(mode, 32), field(error)])


def pop_command():
    try:
        lines = COMMAND.read_text(encoding="utf-8").splitlines()
        COMMAND.unlink(missing_ok=True)
    except (OSError, UnicodeError):
        return None
    if len(lines) < 2 or lines[0] != "DISCORDCMD1":
        return None
    if lines[1] not in ("login", "logout"):
        return None
    return lines[1]


def publish_notification(payload, avatar_cache=None):
    if not isinstance(payload, dict):
        return
    message = payload.get("message") or {}
    identifier = str(message.get("id") or "")
    if not identifier.isdecimal():
        return
    title = field(payload.get("title") or "Discord", 256)
    body = field(payload.get("body") or message.get("content") or "", 700)
    if not title and not body:
        return
    sender_avatar = cached_notification_avatar(payload, avatar_cache) if avatar_cache else ""
    atomic_lines(NOTICE, ["DISCORDNOTIFY1", identifier, title, body,
                          str(int(time.time())), sender_avatar])
