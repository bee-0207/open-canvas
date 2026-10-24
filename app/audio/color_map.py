"""
color_map.py: Layer 2 of the sound design (CLAUDE.md section 6). Turns the color under
the finger into instrument weights and a register (low/high) mix.

    blue           -> harp
    warm (R/O/Y)   -> strings
    green          -> woodwind   (NOT in the team's 4-instrument spec; see note below)
    pale / white   -> choir
    dark           -> cello
    brighter       -> higher register (crossmodal correspondence: light = high pitch)

Everything is a *soft* membership function (smoothstep / Gaussian on hue), not a hard
if/else. A hard threshold is a comparator with no hysteresis: when the finger sits on a
color boundary or the camera jitters by a pixel, the sound flips back and forth. Soft
weights crossfade instead.

Weights always sum to 1.0. The engine turns weight w into gain with
    gain = BED + (1 - BED) * w        (BED = 0.14, team spec)
so every instrument plays at least a quiet bed and the mix never goes silent.

"Dark" uses HSL lightness, not luma (team spec). Luma weights blue at only 11%, so
navy (0, 0, 128) has luma 0.06 and would read as black. HSL lightness is
(max + min) / 2 for every hue: navy is L = 0.25, which plays as harp in the low
register, not as cello.

GREEN NOTE (open question for the team): the spec has no slot for green, but landscapes
are full of it. EyeMusic, the research the design cites, gives green a reed timbre, so
woodwind is added here. To go back to 4 instruments, delete "woodwind" from HUE_CENTERS
and INSTRUMENTS; green then splits between harp and strings automatically.
"""

import colorsys
import math

# Chromatic instruments: hue center in degrees (0 = red, 120 = green, 240 = blue).
HUE_CENTERS = {
    "strings": 25.0,    # orange-ish: covers red, orange, yellow
    "woodwind": 115.0,  # green
    "harp": 220.0,      # blue
}
HUE_WIDTH_DEG = 45.0   # Gaussian width of each hue lobe. Larger = more blending.

INSTRUMENTS = ["harp", "strings", "woodwind", "choir", "cello"]

# Lightness / saturation thresholds (HSL, 0..1). Each pair is a smoothstep ramp.
DARK_RAMP = (0.10, 0.25)   # L below 0.10 is fully "dark", above 0.25 not dark at all
PALE_RAMP = (0.75, 0.92)   # L above 0.92 is fully "pale/white"
GRAY_RAMP = (0.08, 0.22)   # S below 0.08 has no usable hue (gray)

BED = 0.14                 # quiet floor for every instrument (team spec)


def smoothstep(e0, e1, x):
    """0 below e0, 1 above e1, smooth S-curve between (zero slope at both ends)."""
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def _hue_dist(a, b):
    """Shortest distance between two hues on the color wheel, in degrees."""
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def color_weights_hsl(h, s, l):
    """
    h: hue in degrees 0..360, s: saturation 0..1, l: lightness 0..1.
    This is the proposed `hsl` format for audio.update(); confirm it with the CE.
    Returns dict instrument -> weight 0..1, summing to 1.
    """
    w = {k: 0.0 for k in INSTRUMENTS}

    dark = 1.0 - smoothstep(*DARK_RAMP, l)
    pale = smoothstep(*PALE_RAMP, l)
    gray = 1.0 - smoothstep(*GRAY_RAMP, s)

    w["cello"] += dark
    w["choir"] += (1.0 - dark) * pale
    rest = (1.0 - dark) * (1.0 - pale)          # the mid-lightness share

    # Mid-lightness grays have no hue: lean cello when darker, choir when lighter.
    w["cello"] += rest * gray * (1.0 - l)
    w["choir"] += rest * gray * l

    # Colored share: split by circular Gaussian distance to each hue center.
    chroma = rest * (1.0 - gray)
    if chroma > 0:
        lobes = {k: math.exp(-(_hue_dist(h, c) / HUE_WIDTH_DEG) ** 2)
                 for k, c in HUE_CENTERS.items()}
        total = sum(lobes.values()) or 1.0
        for k, v in lobes.items():
            w[k] += chroma * v / total

    return w


def rgb_to_hsl(rgb):
    """(r, g, b) as 0..255 ints or 0..1 floats -> (h degrees, s, l)."""
    r, g, b = rgb
    if max(r, g, b) > 1.0:
        r, g, b = r / 255.0, g / 255.0, b / 255.0
    h, l, s = colorsys.rgb_to_hls(r, g, b)      # note: Python returns H, L, S order
    return h * 360.0, s, l


def register_mix(l):
    """
    Team spec: out = low * (1 - 0.7L) + high * (0.15 + 0.85L).
    At L=0 -> low 1.00, high 0.15.  At L=1 -> low 0.30, high 1.00.
    Both registers always sound a little, so a lightness change is a timbre glide,
    not an on/off switch.
    """
    return 1.0 - 0.7 * l, 0.15 + 0.85 * l


def instrument_gain(weight):
    return BED + (1.0 - BED) * weight


if __name__ == "__main__":
    # Sanity table. Run from the repo root:  .venv/bin/python -m app.audio.color_map
    tests = {
        "navy (0,0,128)": (0, 0, 128),
        "sky blue": (90, 150, 230),
        "orange sunset": (245, 150, 70),
        "pale sun": (255, 238, 190),
        "white": (250, 250, 250),
        "grass green": (60, 130, 60),
        "black": (15, 15, 15),
        "mid gray": (128, 128, 128),
        "purple": (130, 60, 170),
    }
    print(f"{'color':18s} " + " ".join(f"{k:>8s}" for k in INSTRUMENTS) + "      L  lo/hi")
    for name, c in tests.items():
        h, s, l = rgb_to_hsl(c)
        w = color_weights_hsl(h, s, l)
        lo, hi = register_mix(l)
        print(f"{name:18s} " + " ".join(f"{w[k]:8.2f}" for k in INSTRUMENTS)
              + f"   {l:4.2f}  {lo:.2f}/{hi:.2f}")
