"""No network: verify author identities, caching, and notification wire format."""
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import notification_avatar
import controller

author = {"id": "123456789012345678", "username": "Moris",
          "avatar": "a_deadbeef1234567"}
payload = {"message": {"id": "123456789987654321", "author": author,
                       "content": "Hello from Discord"}, "title": "Captain Moris"}
expected = ("https://cdn.discordapp.com/avatars/123456789012345678/"
            "a_deadbeef1234567.png?size=64")
assert notification_avatar.avatar_url(payload) == expected
assert notification_avatar.avatar_url({"message": {"author": {"id": "invalid"}}}) == ""
assert notification_avatar.avatar_url({"message": {"author": {"id": author["id"],
       "avatar": "https://evil.example/a.png"}}}) == ""
assert notification_avatar.avatar_url(
    {"icon_url": "https://attacker.example/avatar.png"}) == ""
assert notification_avatar.avatar_url(
    {"icon_url": "https://cdn.discordapp.com/avatars/123456789/abc.png"}) != ""

with tempfile.TemporaryDirectory() as tmp:
    dest = Path(tmp) / "assets"
    calls = []
    original = notification_avatar.download_icon
    def fake_download(url, filename):
        calls.append(url)
        filename.parent.mkdir(parents=True, exist_ok=True)
        filename.write_bytes(b"\x89PNG\r\n\x1a\nnot-a-real-image")
        return True
    notification_avatar.download_icon = fake_download
    try:
        first = notification_avatar.cached_notification_avatar(payload, dest)
        second = notification_avatar.cached_notification_avatar(payload, dest)
    finally:
        notification_avatar.download_icon = original
    assert first == second and Path(first).is_file() and calls == [expected]

    old_notice = controller.NOTICE
    controller.NOTICE = Path(tmp) / "notification.tsv"
    original = notification_avatar.download_icon
    notification_avatar.download_icon = fake_download
    try:
        controller.publish_notification(payload, dest)
        lines = controller.NOTICE.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "DISCORDNOTIFY1"
        assert lines[1] == "123456789987654321"
        assert lines[3] == "Hello from Discord"
        assert lines[5] == first
        # Legacy notification calls still work and leave avatar path empty.
        controller.publish_notification({"message": {"id": "123456789987654322"},
                                        "title": "Legacy", "body": "Content"})
        lines = controller.NOTICE.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 6 and lines[5] == ""
    finally:
        notification_avatar.download_icon = original
        controller.NOTICE = old_notice

print("PASS Discord sender avatar extraction, host validation, cache, notification wire")
