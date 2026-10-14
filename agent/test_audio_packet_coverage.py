"""Every bar must receive PCM samples from an ordinary WASAPI packet."""
from pathlib import Path
src=(Path(__file__).resolve().parents[1]/"windhawk"/"discord_process_loopback.h").read_text(encoding="utf-8")
assert "i * sums.size() / frames" in src
assert "kFramesPerWindow" not in src
for frames in [8,16,80,240,480,960,1920,4800]:
    counts=[0]*8
    for i in range(frames):
        counts[min(7,i*8//frames)] += 1
    assert all(n > 0 for n in counts),(frames,counts)
print("DISCORD_ALL_8_BARS_RECEIVE_PCM_OK")
