#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pārāyaṇa tracks for the two root texts.

The Brahmasūtras and the Gītā are recited straight through, not consulted a sūtra at a time
— but the audio we have was cut for a commentary's purposes: 564 five-second sūtra tiles and
365 verse-runs. Reciting a pāda that way means forty separate plays.

This assembles the same clips into CONTINUOUS tracks:

    Brahmasūtra   one per PĀDA      (16 tracks, ~3 min each)
    Bhagavad-Gītā one per ADHYĀYA   (18 tracks, 2–13 min)

Karaoke stays per sūtra / per verse, so the reader still follows line by line inside a track.

Recitation practice, as followed in the sampradāya:

  * EVERY sūtra is framed ॐ … ॐ. That is how the Brahmasūtras are recited — the pranava is
    not an artefact of being quoted in a bhāṣya, it belongs to the recitation itself. (I had
    dropped it, reasoning that forty pranavas in a pāda was repetition; that was wrong.)
    The opening sūtra of the work keeps its two leading pranavas.
  * Gītā verses are NOT individually framed — the adhyāya flows.
  * the pause between sūtras is longer than between verse pādas — a sūtra is a complete
    aphorism, a pāda is a metrical line.
"""
import argparse, json, os, subprocess, sys
import numpy as np, soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from assemble_block import rd, sil, trim_lead, SR, EXEMPLAR, PRANAVA_GAP, PRANAVA_TIGHT

SUTRA_GAP = 0.85     # between aphorisms
VERSE_GAP = 0.55     # between verses
PADA_GAP  = 0.45     # between the pādas of one verse
FRAME_GAP = 0.35     # around the opening/closing pranava


def encode(wav, out, bitrate="128k"):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-c:a", "aac",
                    "-b:a", bitrate, "-movflags", "+faststart", out], check=True)


def build(units, clipdir, frame_each, unit_gap, first_double=False):
    """units -> (audio, segs), ONE seg per unit; a unit may hold several pāda clips.

    frame_each puts a pranava on both sides of every unit — the Brahmasūtra recitation. The
    seg spans the framing too, so the highlight covers the ॐ that belongs to that sūtra."""
    parts, segs, pos = [], [], 0
    def emit(a):
        nonlocal pos
        parts.append(a); pos += len(a)
    ex = rd(EXEMPLAR) if frame_each else None
    for i, u in enumerate(units):
        if i:
            emit(sil(unit_gap))
        start = pos
        if ex is not None:
            emit(ex); emit(sil(PRANAVA_GAP))
            if i == 0 and first_double:          # the opening sūtra of the work
                emit(ex); emit(sil(PRANAVA_TIGHT))
        for k, cid in enumerate(u["clips"]):
            if k:
                emit(sil(PADA_GAP))
            p = os.path.join(clipdir, cid + ".wav")
            if not os.path.exists(p):
                return None, None, cid
            emit(trim_lead(rd(p)))
        if ex is not None:
            emit(sil(PRANAVA_GAP)); emit(ex)
        segs.append({"s": round(start / SR, 3), "e": round(pos / SR, 3),
                     "u": i, "ref": u.get("ref") or u.get("verse")})
    return np.concatenate(parts), segs, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks-bsb", default="blocks_bsb.json")
    ap.add_argument("--blocks-gita", default="blocks_gt.json")
    ap.add_argument("--clips-bsb", required=True)
    ap.add_argument("--clips-gita", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--timings", default="timings_parayana.json")
    a = ap.parse_args()

    out, missing = [], []

    # ── Brahmasūtra: one track per pāda ───────────────────────────────────────
    groups = {}
    for b in json.load(open(a.blocks_bsb, encoding="utf-8")):
        if not b.get("ref"):
            continue
        adh, pada, s = b["ref"].split("/")
        for u in b["units"]:
            if u["type"] == "sutra":
                groups.setdefault((int(adh), int(pada)), []).append(dict(u, ref=b["ref"]))
    for (adh, pada), units in sorted(groups.items()):
        audio, segs, miss = build(units, a.clips_bsb, frame_each=True, unit_gap=SUTRA_GAP,
                                  first_double=(adh == 1 and pada == 1))
        if miss:
            missing.append(f"BS {adh}.{pada}: {miss}"); continue
        rel = f"parayana/brahmasutra/BS_{adh}.{pada}.m4a"
        wav = os.path.join(a.outdir, rel).replace(".m4a", ".wav")
        os.makedirs(os.path.dirname(wav), exist_ok=True)
        sf.write(wav, audio, SR, subtype="PCM_16")
        encode(wav, os.path.join(a.outdir, rel)); os.unlink(wav)
        out.append({"work": "brahmasutra", "block": f"bs_{adh}_{pada}", "part": 0,
                    "path": rel, "dur": round(len(audio) / SR, 3),
                    "n": len(units), "segs": segs})
        print(f"  BS {adh}.{pada}: {len(units)} sūtras, {len(audio)/SR/60:.1f} min")

    # ── Gītā: one track per adhyāya ───────────────────────────────────────────
    gg = {}
    for b in json.load(open(a.blocks_gita, encoding="utf-8")):
        for u in b["units"]:
            if u.get("is_mula") and u.get("verse"):
                gg.setdefault(int(u["verse"].split("/")[0]), []).append(u)
    for adh, units in sorted(gg.items()):
        audio, segs, miss = build(units, a.clips_gita, frame_each=False, unit_gap=VERSE_GAP)
        if miss:
            missing.append(f"BG {adh}: {miss}"); continue
        rel = f"parayana/bhagavadgita/BG_{adh}.m4a"
        wav = os.path.join(a.outdir, rel).replace(".m4a", ".wav")
        os.makedirs(os.path.dirname(wav), exist_ok=True)
        sf.write(wav, audio, SR, subtype="PCM_16")
        encode(wav, os.path.join(a.outdir, rel)); os.unlink(wav)
        out.append({"work": "bhagavadgita", "block": f"bg_{adh}", "part": 0,
                    "path": rel, "dur": round(len(audio) / SR, 3),
                    "n": len(units), "segs": segs})
        print(f"  BG {adh}: {len(units)} verses, {len(audio)/SR/60:.1f} min")

    json.dump(out, open(a.timings, "w"), ensure_ascii=False)
    tot = sum(x["dur"] for x in out)
    print(f"\n{len(out)} pārāyaṇa tracks, {tot/3600:.2f} h -> {a.outdir}")
    print(f"timings -> {a.timings}")
    if missing:
        print(f"\nSKIPPED {len(missing)} track(s) with absent clips:")
        for m in missing[:8]:
            print("  ", m)


if __name__ == "__main__":
    main()
