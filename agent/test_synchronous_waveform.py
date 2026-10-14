"""Regression: Discord columns must update synchronously without history-scroll offsets."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
bridge=(root/"windhawk/discord_bridge.h").read_text(encoding="utf-8")
mod=(root.parents[1]/"src/mod.wh.cpp").read_text(encoding="utf-8")
start=mod.index("// Synchronous bars: one current per-column PCM amplitude")
end=mod.index("accentBrush_->SetOpacity(1.0f);",start)
draw=mod[start:end]
assert "voice.waveform[static_cast<size_t>(i)]" in draw
assert "waveformWrite +" not in draw
assert "kSampleStep" not in draw
assert "std::sin(" not in draw
start=bridge.index("// Eight current PCM levels update")
end=bridge.index("g_layoutDirty = true;",start)
update=bridge[start:end]
assert "voice.waveform[i] = level > previous" in update
assert "voice.waveform[voice.waveformWrite %" not in update
assert "++voice.waveformWrite;" in update
assert "lastAudioPoll >= 16" in bridge
assert "WaitForSingleObject(g_stopEvent, 16)" in bridge
assert "previous * 0.60f + level * 0.40f" in update
print("SYNCHRONOUS_DISCORD_BARS_OK")
