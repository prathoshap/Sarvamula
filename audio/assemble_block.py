#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Assemble a whole BSB block (sutra + bhāṣya units) into one track.

Per-unit clips come from render_batch.py (--outdir). This adds the editorial layer
that the renderer does not know about:

  * the SUTRA unit is framed by the human-recorded exemplar pranava (assemble.py's
    approved rule: EX + 0.25 + body + 0.25 + EX; the first sutra of a work also gets
    the integral opening ॐ — see assemble.py FIRST_SUTRA_IDS),
  * units are separated by a unit gap, longer than the intra-unit pada gap that
    render_batch already applied (--gap, default 0.55) so the unit boundary reads as
    a bigger break than a pada boundary,
  * a quote (padya) that follows prose gets a slightly longer lead-in, since in
    recitation the citation is set off from the bhāṣya around it.

Usage:
  assemble_block.py --clipdir out16 --canon shard_bsb_1_1_2_canon.json \
                    --out bsb_1_1_2_block.wav
"""
import argparse, json, os, subprocess, tempfile
import numpy as np, soundfile as sf

AUDIO = os.path.dirname(os.path.abspath(__file__))
EXEMPLAR = os.path.join(AUDIO, "assets", "pranava_exemplar.wav")
SR = 24000

PRANAVA_GAP = 0.25   # exemplar ॐ <-> sutra body (assemble.py approved)
PRANAVA_TIGHT = 0.08 # first sutra: the integral ॐ flows tight into "atha…"
UNIT_GAP    = 0.75   # between units (> render_batch --gap 0.55 pada gap)
QUOTE_LEAD  = 0.30   # extra before a padya that follows prose

# The opening sutra of a work carries its OWN ॐ in the text (BSB 1/1/1 reads
# '॥ [ॐ] ॐ अथातो ब्रह्मजिज्ञासा [ॐ]॥'), so it gets two leading pranavas: the maṅgala ॐ,
# then the integral one running tight into the aphorism. Mirrors assemble.py.
FIRST_SUTRA_BLOCKS = {"bsb_1_1_1"}

_TYPES = ("sutra", "gadya", "padya")

def clip_type(cid):
    """Unit type out of a clip id. Ids are <block>_u<NN>_<type> and, since clip ids
    became content-addressed, <block>_u<NN>_<type>_<hash6> — so take the last component
    that IS a type rather than the last component."""
    for part in reversed(cid.split("_")):
        if part in _TYPES:
            return part
    return ""


def sil(dur):
    return np.zeros(int(dur*SR), dtype=np.float32)


def rd(path):
    a, sr = sf.read(path, dtype="float32")
    if a.ndim > 1: a = a.mean(1)
    assert sr == SR, f"{path}: expected {SR}, got {sr}"
    return a


def trim_lead(a, thr_db=-65.0, win=0.02):
    """Drop leading frames below thr_db — F5's zero-padding only, never speech.

    Threshold matters. At the old -45 dB, this removed audio ABOVE -45 dB on 14 of 67
    clips (worst peak -33.5 dBFS): the ramp-in of a sonorant onset (न, य, अ), i.e. the
    very same "first syllable clipped" failure as gate(), just relocated to assembly.
    F5's padding measures ~-80 dB while onsets sit at -33..-38 dB, so -65 dB lands in
    the empty band between them: it still removes ~222 ms of padding on average, and
    across all 67 clips the loudest thing it removes is -52.7 dB. Do not raise it."""
    w = int(win*SR)
    i = 0
    while i + w <= len(a) and 20*np.log10(max(float(np.sqrt((a[i:i+w]**2).mean())), 1e-9)) < thr_db:
        i += w
    return a[i:]


# Pauses inside a unit depend on WHY the pada boundary is there:
#   hard (daṇḍa / comma / lacuna) — a sentence break, must be heard
#   soft (visarga split)          — sub-clause, only there for the visarga echo; a full
#                                   pause here chops a sentence mid-flow
PADA_GAP      = 0.55   # hard boundary
PADA_GAP_SOFT = 0.12   # soft boundary

# A LACUNA is lost text (Anuvyākhyāna marks it "--- --- ---"). It is rendered as SILENCE,
# never bridged: joining the surviving halves would make the recitation assert a line the
# manuscript does not have, and the join would be inaudible. Longer than a pada gap so the
# hole is unmistakably a hole rather than phrasing.
LACUNA_SIL = 0.9


def assemble_from_units(units, clipdir, unit_gap=UNIT_GAP, quote_lead=QUOTE_LEAD,
                        pada_gap=PADA_GAP, pranava=True, prebuilt=None):
    """Assemble from PER-PADA clips (the Bhāgavatam arrangement: one pada per render).

    units = [{n, type, clips:[per-pada clip ids]}] in reading order.
    Every gap is now ours: pada_gap inside a unit, unit_gap between units, plus
    quote_lead before a citation that follows prose. Set pada_gap=0 for the variant
    where the model's own padding is the only pause.
    Returns (audio, segs) with one seg per UNIT (the karaoke granularity)."""
    ex = rd(EXEMPLAR) if pranava else None
    prebuilt = prebuilt or {}
    parts, segs, prev_type, pos = [], [], None, 0

    def emit(c):
        nonlocal pos
        parts.append(c); pos += len(c)

    for n, u in enumerate(units):
        utype = u["type"]
        if n:
            emit(sil(unit_gap + (quote_lead if (utype == "padya" and prev_type == "gadya") else 0.0)))
        start = pos
        bounds = u.get("bounds") or ["hard"]*len(u["clips"])
        gapafter = u.get("gapafter") or [False]*len(u["clips"])
        body, spans = [], []          # spans: (offset_in_body, length) per PADA
        if u.get("lead_gap"):
            body.append(sil(LACUNA_SIL))          # text lost BEFORE the first surviving pada
        for k, cid in enumerate(u["clips"]):
            if k:
                # the gap BEFORE pada k is set by the boundary that follows pada k-1
                soft = k-1 < len(bounds) and bounds[k-1] == "soft"
                body.append(sil(pada_gap * (PADA_GAP_SOFT/PADA_GAP) if soft else pada_gap))
            clip = (rd(prebuilt[cid]) if cid in prebuilt
                    else trim_lead(rd(os.path.join(clipdir, cid + ".wav"))))
            spans.append((sum(len(c) for c in body), len(clip)))
            body.append(clip)
            if k < len(gapafter) and gapafter[k]:
                body.append(sil(LACUNA_SIL))      # text lost AFTER this pada
        body_at = pos                 # where body starts in the assembled stream
        oms = []                      # (label, offset, length) for each spliced pranava
        # PREBUILT now supplies the sūtra BODY only — it used to supply the whole framed
        # file, which meant the one hand-approved sūtra (1.1.1) skipped framing entirely and
        # would have kept the old 0.557 s ॐ while all 563 others changed, and shown no ॐ
        # lines. The approved recitation is preserved; only the frame around it is ours.
        if utype == "sutra" and ex is not None:
            first = u["clips"][0].rsplit("_u", 1)[0] in FIRST_SUTRA_BLOCKS
            frame = ([ex, sil(PRANAVA_GAP), ex, sil(PRANAVA_TIGHT)] if first
                     else [ex, sil(PRANAVA_GAP)])
            # The pranava is RECITED, so it needs a seg — otherwise the karaoke has nothing
            # to light for the first ~0.6 s of every sūtra and the reader shows no ॐ at all
            # though one is plainly audible. Labels rather than indices, so adding a
            # pranava can never collide with a pāda's position.
            nlead = 0
            for c in frame:
                if c is ex:
                    oms.append((f"om{nlead}", pos, len(c))); nlead += 1
                emit(c)
            body_at = pos
            for c in body: emit(c)
            emit(sil(PRANAVA_GAP))
            oms.append(("omT", pos, len(ex))); emit(ex)
        else:
            for c in body: emit(c)
        # ONE SEG PER PADA, not per unit. A padya unit can be 24 padas — lighting the whole
        # unit at once is unreadable, and verse wants pāda-wise karaoke anyway. Since every
        # pada is its own clip, the boundaries are exact rather than estimated.
        for k, (off, ln) in enumerate(spans):
            segs.append({"s": round((body_at + off)/SR, 3),
                         "e": round((body_at + off + ln)/SR, 3),
                         "u": n, "p": k, "type": utype})
        for label, at, ln in oms:     # absolute already — not relative to body_at
            segs.append({"s": round(at/SR, 3), "e": round((at + ln)/SR, 3),
                         "u": n, "p": label, "type": "pranava"})
        prev_type = utype
    return np.concatenate(parts), segs


def assemble_units(ids, clipdir, unit_gap=UNIT_GAP, quote_lead=QUOTE_LEAD, pranava=True,
                   opens=None, prebuilt=None):
    """Core used by both this CLI and the corpus pass (assemble_bsb.py).

    opens[i]    unit i began with a ॐ in the source that was NOT rendered (the model
                cannot voice a lone pranava) -> splice the exemplar in front of it.
    prebuilt    {clip_id: wav_path} to use verbatim instead of clipdir + framing —
                for hand-approved assemblies such as sutra_1_1_1_final.wav.

    Returns (audio float32, segs) where segs = [{s,e,u,type}] in seconds."""
    ex = rd(EXEMPLAR) if pranava else None
    opens = opens or [False]*len(ids)
    prebuilt = prebuilt or {}
    parts, segs, prev_type, pos = [], [], None, 0

    def emit(chunk):
        nonlocal pos
        parts.append(chunk); pos += len(chunk)

    for n, cid in enumerate(ids):
        utype = clip_type(cid)
        if n:
            emit(sil(unit_gap + (quote_lead if (utype == "padya" and prev_type == "gadya") else 0.0)))
        start = pos
        # seg spans the WHOLE unit as heard, pranava framing included, so tapping a
        # unit in the reader seeks to the start of its recitation.
        if cid in prebuilt:                       # hand-approved, use verbatim
            emit(rd(prebuilt[cid]))
        else:
            clip = trim_lead(rd(os.path.join(clipdir, cid + ".wav")))
            if utype == "sutra" and ex is not None:
                first = cid.rsplit("_u", 1)[0] in FIRST_SUTRA_BLOCKS
                frame = ([ex, sil(PRANAVA_GAP), ex, sil(PRANAVA_TIGHT), clip,
                          sil(PRANAVA_GAP), ex] if first else
                         [ex, sil(PRANAVA_GAP), clip, sil(PRANAVA_GAP), ex])
                for c in frame:
                    emit(c)
            else:
                # a unit that opened with ॐ in the source: the pranava was removed
                # before TTS (the model collapses it), so splice the exemplar here.
                if opens[n] and ex is not None:
                    emit(ex); emit(sil(PRANAVA_GAP))
                emit(clip)
        segs.append({"s": round(start/SR, 3), "e": round(pos/SR, 3), "u": n, "type": utype})
        prev_type = utype

    return np.concatenate(parts), segs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clipdir", required=True)
    ap.add_argument("--canon", required=True, help="json list of clip ids, in reading order")
    ap.add_argument("--out", required=True)
    ap.add_argument("--unit_gap", type=float, default=UNIT_GAP)
    ap.add_argument("--quote_lead", type=float, default=QUOTE_LEAD)
    ap.add_argument("--no_pranava", action="store_true", help="skip the exemplar ॐ around the sutra")
    ap.add_argument("--timings", default="", help="write per-unit karaoke segs JSON "
                    "([{s,e,u,type}], same shape as Bhāgavatam's timings.segs) for the DB")
    a = ap.parse_args()

    ids = json.load(open(a.canon))
    final, segs = assemble_units(ids, a.clipdir, a.unit_gap, a.quote_lead,
                                 pranava=not a.no_pranava)
    sf.write(a.out, final, SR, subtype="PCM_16")
    for g in segs:
        print(f"  {ids[g['u']]:34s} {g['s']:7.3f} -> {g['e']:7.3f}")
    print(f"\n{len(ids)} units -> {a.out}  {len(final)/SR:.3f}s")

    if a.timings:
        json.dump(segs, open(a.timings, "w"), ensure_ascii=False)
        print(f"timings ({len(segs)} segs) -> {a.timings}")


if __name__ == "__main__":
    main()
