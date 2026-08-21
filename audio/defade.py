#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Undo gate()'s 15 ms linear fade-in on an already-rendered clip.

WHY: vagdhenu/src/render_core.py:140 gate() ends with

    fi = (0 if fric else int(fin*SR))          # fin=0.015 -> 360 samples @24k
    if fi and len(out) > fi: out[:fi] *= np.linspace(0, 1, fi)

That fade is harmless when the gate's start lands in silence (the usual case).
But when the clip begins with a SONORANT onset — a semivowel य/व/र/ल, a nasal, or
a vowel — the voiced-onset detector (voice=0.08) starts inside the glide, and the
ramp then attenuates live speech by up to ~32 dB. Heard as a clipped first syllable
("yato" -> "ato"/"'to").

This is a REPAIR for clips already rendered. The real fix is in gate() itself
(treat sonorant onsets like the existing fricative case: low floor, no fade-in) —
see patch_note in this directory. Samples the gate TRIMMED are gone; only the
attenuation is recoverable.

Usage:  defade.py in.wav out.wav [--lead 0.12]
"""
import argparse, numpy as np, soundfile as sf

SR = 24000
FIN = 0.015          # gate()'s fin
FLOOR = 0.08         # don't divide by a ramp value below this (noise blow-up guard)

def defade(au, fin=FIN, sr=SR, floor=FLOOR):
    fi = int(fin * sr)
    if len(au) <= fi:
        return au, 0.0
    ramp = np.linspace(0, 1, fi)
    # Below `floor` the ramp is so small that dividing amplifies dither/noise, and
    # those samples are perceptually negligible anyway — hold the gain constant there.
    gain = 1.0 / np.maximum(ramp, floor)
    out = au.copy()
    out[:fi] = out[:fi] * gain
    peak = float(np.abs(out).max())
    if peak > 0.99:                      # keep headroom; the onset can now exceed the old peak
        out = out / peak * 0.97
    return out, float(gain.max())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--lead", type=float, default=0.12,
                    help="seconds of silence to prepend so the clip does not start flush at t=0")
    a = ap.parse_args()

    au, sr = sf.read(a.src, dtype="float32")
    if au.ndim > 1: au = au.mean(1)
    assert sr == SR, f"expected {SR}, got {sr}"

    out, gmax = defade(au)
    if a.lead > 0:
        out = np.concatenate([np.zeros(int(a.lead * sr), dtype=np.float32), out])

    sf.write(a.dst, out, sr, subtype="PCM_16")
    print(f"{a.src} -> {a.dst}")
    print(f"  max onset gain applied : {gmax:.1f}x  ({20*np.log10(gmax):.1f} dB)")
    print(f"  lead silence prepended : {a.lead*1000:.0f} ms")
    print(f"  duration               : {len(out)/sr:.3f}s")

if __name__ == "__main__":
    main()
