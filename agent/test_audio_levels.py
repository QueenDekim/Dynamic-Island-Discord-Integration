"""Regression: Discord RMS bars must not saturate during ordinary speech."""
from pathlib import Path
import math

src = (Path(__file__).resolve().parents[1] / "windhawk" /
       "discord_process_loopback.h").read_text(encoding="utf-8")
assert "kHalfScaleRms = 0.085" in src
assert "kFramesPerWindow = 240" in src
assert "(raw[i] - mean) * 2.2" not in src
assert "signal / (signal + kHalfScaleRms)" in src
assert "kVoiceGain = 120.0" not in src

def level(rms):
    signal = max(0.0, rms - 0.001)
    return signal / (signal + 0.085)

assert level(0) == 0
assert level(0.0008) == 0
values = [level(x) for x in (0.002, 0.008, 0.02, 0.06, 0.12, 0.3)]
assert all(0 < a < b < 1 for a,b in zip(values, values[1:]))
assert level(0.02) < 0.3
assert level(0.06) < 0.6
assert level(0.12) < 0.7
print("DISCORD_RMS_SOFT_KNEE_OK", [round(v,3) for v in values])
