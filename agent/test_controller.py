"""Protocol regression tests; no Discord authorization or network."""
from pathlib import Path
import tempfile
import time
from unittest.mock import patch

import controller

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    with patch.object(controller, "BASE", root), \
         patch.object(controller, "STATUS", root / "status.tsv"), \
         patch.object(controller, "COMMAND", root / "command.txt"), \
         patch.object(controller, "NOTICE", root / "notification.tsv"):
        controller.publish_status("authorized")
        assert (root / "status.tsv").read_text(encoding="utf-8").splitlines()[:2] == [
            "DISCORDSTATUS1", "authorized"
        ]
        (root / "command.txt").write_text("DISCORDCMD1\nlogin\n", encoding="utf-8")
        assert controller.pop_command() == "login"
        assert controller.pop_command() is None
        (root / "command.txt").write_text("DISCORDCMD1\nlogout\n", encoding="utf-8")
        assert controller.pop_command() == "logout"

        controller.publish_notification({
            "title": "Alice (#general)",
            "body": "Hello\nDiscord!",
            "message": {"id": "123456789012345678", "content": "Hello\nDiscord!"}
        })
        values = (root / "notification.tsv").read_text(encoding="utf-8").splitlines()
        assert values[0] == "DISCORDNOTIFY1"
        assert values[1] == "123456789012345678"
        assert values[2] == "Alice (#general)"
        assert values[3] == "Hello Discord!"
        assert int(values[4]) >= time.time() - 5
print("PASS: login, logout, notification transport and multiline sanitization")
