"""Validate authoritative Discord voice-session timestamps without user tokens."""
from voice_state import normalize, parse_voice_start_time
from datetime import datetime, timezone

epoch=int(datetime(2026,10,14,12,0,tzinfo=timezone.utc).timestamp())
assert parse_voice_start_time("2026-10-14T12:00:00Z")==epoch
assert parse_voice_start_time(epoch*1000)==epoch
assert parse_voice_start_time(epoch)==epoch
assert parse_voice_start_time(None)==0
assert parse_voice_start_time("not-a-timestamp")==0
channel={"id":"123","guild_id":"222","name":"general-voice","voice_states":[],
         "voice_start_time":"2026-10-14T12:00:00Z"}
snapshot=normalize(channel,{}, {}, joined_at=epoch+3600)
assert snapshot["voice_started_unix"]==epoch
assert snapshot["joined_unix"]==epoch+3600
channel.pop("voice_start_time")
snapshot=normalize(channel,{}, {}, joined_at=epoch+3600)
assert snapshot["voice_started_unix"]==0
print("DISCORD_VOICE_SESSION_TIME_OK")
