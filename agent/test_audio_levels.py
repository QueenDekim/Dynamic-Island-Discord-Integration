"""Regression checks: Discord uses the exact Media PCM RMS mapping."""
from pathlib import Path
src=(Path(__file__).resolve().parents[1]/"windhawk"/"discord_process_loopback.h").read_text(encoding="utf-8")
assert "i * sums.size() / frames" in src
assert "std::sqrt(sums[i] / counts[i])" in src
assert "rms * 4.0" in src
assert "kHalfScaleRms" not in src
assert "kVoiceGain" not in src
assert "kFramesPerWindow" not in src
for frames in (8, 64, 128, 256, 960, 4800):
    bins=[0]*8
    for i in range(frames):
        bins[min(7,i*8//frames)] += 1
    assert min(bins)>0, (frames,bins)
assert [min(1.0,rms*4) for rms in (0,.01,.1,.25)]==[0,.04,.4,1.0]
print("DISCORD_MEDIA_RMS_MAPPING_OK")
