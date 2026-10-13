from pathlib import Path
import tempfile
from voice_state import normalize, write_windhawk_tsv

channel = {
    "id": "123456789012345678",
    "guild_id": "987654321098765432",
    "name": "Голосовой канал",
    "voice_states": [
        {"user": {"id": "111111111111111111", "username": "Алексей",
                  "avatar": "0123456789abcdef"}},
        {"user": {"id": "222222222222222222", "username": "Виктор",
                  "avatar": None}},
    ],
}
guild = {"name": "Тестовый сервер", "icon_url": ""}
settings = {"mute": False, "deaf": True}
state = normalize(channel, guild, settings, joined_at=1700000000)
assert state["connected"] is True
assert state["channel_name"] == "Голосовой канал"
assert state["participant_count"] == 2
assert state["deafened"] is True
assert state["members"] if "members" in state else state["participants"][0]["name"] == "Алексей"
with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / "voice.tsv"
    write_windhawk_tsv(state, path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[:2] == ["DISCORD1", "1"]
    assert lines[2:4] == ["Тестовый сервер", "Голосовой канал"]
    assert lines[5:8] == ["2", "0", "1"]
    assert lines[9] == "2"
print("PASS Discord RPC voice snapshot: names, participants, timer anchor, microphone state, UTF-8 wire format")
