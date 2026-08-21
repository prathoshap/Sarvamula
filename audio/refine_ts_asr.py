#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fine-tune recording timestamps with Su-shrota. Runs ON box1 (needs the GPU + NeMo env).

    ASR_PY refine_ts_asr.py --wav X.wav --ts TS_X.json --onset 10.321 --out TS_X.refined.json

THE TIMESTAMPS REMAIN THE ANCHOR. Which block is which, and in what order, comes from the
recorder and is never questioned here. All this does is move each block's two edges to where
the recitation actually starts and stops, within a bounded window around the mark.

Why ASR rather than an energy test, which is what I tried first and got wrong repeatedly:

  * a mark lands up to ~1 s after the reciter resumes on a retake, so the opening word sits
    outside the block. Energy can find that only when a pause precedes it — where the
    recitation runs on from the previous verse there is nothing to detect.
  * a mark can sit 1–2.7 s past the end, and the gap may hold a throat-clear. That burp
    measured 0.151 RMS, indistinguishable in level from quiet recitation, so no threshold
    separates them.

The CTC head settles both. It emits BLANK for anything that is not Sanskrit speech, so the
first and last non-blank frames bracket the recitation and exclude the burp by construction.

Edges only move within --max-shift, and never past a neighbour, so a mistaken frame can
never re-order the recording or swallow an adjacent block.
"""
import argparse, json, os, sys
import numpy as np

ROOT = "/home/ece/BigDisk/Prathosh/ASR"
MODEL = f"{ROOT}/exp/ft_ctc_v12/ft_ctc_ep9.nemo"
LABELS = f"{ROOT}/data/eval_logits/labels.json"
OFF, V, BL = 4096, 256, 5632          # Sanskrit slice of the aggregate vocab
SR = 16000


def load_model():
    import torch
    import nemo.collections.asr as na
    m = na.models.EncDecHybridRNNTCTCBPEModel.restore_from(MODEL, map_location="cuda").eval()
    return m, torch


def posteriors(m, torch, wav):
    """Frame log-probs over [blank + Sanskrit tokens] for one window."""
    sig = torch.tensor(wav).unsqueeze(0).cuda()
    sl = torch.tensor([len(wav)]).cuda()
    with torch.no_grad():
        enc, _ = m.forward(input_signal=sig, input_signal_length=sl)
        lp = m.ctc_decoder(encoder_output=enc)[0].cpu().numpy()
    P = lp[:, [BL] + list(range(OFF, OFF + V))]
    P = P - (P.max(1, keepdims=True) + np.log(np.exp(P - P.max(1, keepdims=True)).sum(1, keepdims=True)))
    return P                                     # (frames, 1+V), column 0 = blank


def speech_span(P, hop, thr=0.5, minrun=2):
    """(first, last) seconds of non-blank frames — where the model hears Sanskrit."""
    nonblank = np.exp(P[:, 0]) < thr             # blank probability below thr => speech
    idx = np.where(nonblank)[0]
    if len(idx) == 0:
        return None, None
    # ignore isolated frames: a run must be at least `minrun` long
    runs, s = [], idx[0]
    for a, b in zip(idx, idx[1:]):
        if b != a + 1:
            runs.append((s, a)); s = b
    runs.append((s, idx[-1]))
    runs = [r for r in runs if r[1] - r[0] + 1 >= minrun] or runs
    return runs[0][0] * hop, (runs[-1][1] + 1) * hop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--ts", required=True)
    ap.add_argument("--onset", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pre", type=float, default=1.6, help="look this far before a start mark")
    ap.add_argument("--post", type=float, default=0.6, help="look this far after an end mark")
    ap.add_argument("--max-shift", type=float, default=2.8)
    ap.add_argument("--pad", type=float, default=0.06, help="breathing room kept around speech")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    import soundfile as sf
    x, sr = sf.read(a.wav, dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    if sr != SR:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(int(sr), SR)
        x = resample_poly(x, SR // g, int(sr) // g).astype("float32")
    dur = len(x) / SR
    ts = json.load(open(a.ts, encoding="utf-8"))
    blocks = ts["blocks"]
    m, torch = load_model()

    out, moved = [], 0
    for i, k in enumerate(blocks):
        if a.limit and i >= a.limit:
            out.append(dict(k)); continue
        s = k["start_ms"] / 1000.0 + a.onset
        e = k["end_ms"] / 1000.0 + a.onset
        prev_e = (blocks[i-1]["end_ms"] / 1000.0 + a.onset) if i else 0.0
        next_s = (blocks[i+1]["start_ms"] / 1000.0 + a.onset) if i + 1 < len(blocks) else dur
        w0 = max(0.0, min(s - a.pre, s))
        w1 = min(dur, e + a.post)
        seg = x[int(w0 * SR):int(w1 * SR)]
        if len(seg) < SR // 4:
            out.append(dict(k)); continue
        P = posteriors(m, torch, seg)
        hop = (len(seg) / SR) / len(P)
        t0, t1 = speech_span(P, hop)
        ns, ne = s, e
        if t0 is not None:
            cand = w0 + t0 - a.pad
            if abs(cand - s) <= a.max_shift:
                ns = max(prev_e, cand) if i else max(0.0, cand)
        if t1 is not None:
            cand = w0 + t1 + a.pad
            if abs(cand - e) <= a.max_shift:
                ne = min(next_s, cand)
        if ne <= ns:
            ns, ne = s, e
        if abs(ns - s) > 0.02 or abs(ne - e) > 0.02:
            moved += 1
        n = dict(k)
        n["start_ms"] = int(round((ns - a.onset) * 1000))
        n["end_ms"] = int(round((ne - a.onset) * 1000))
        n["duration_ms"] = n["end_ms"] - n["start_ms"]
        n["asr_start_shift_ms"] = int(round((ns - s) * 1000))
        n["asr_end_shift_ms"] = int(round((ne - e) * 1000))
        out.append(n)
        print(f"  #{i:4d} start {s:8.3f}->{ns:8.3f} ({(ns-s)*1000:+6.0f}ms)  "
              f"end {e:8.3f}->{ne:8.3f} ({(ne-e)*1000:+6.0f}ms)", flush=True)

    ts["blocks"] = out
    bad = sum(1 for i in range(len(out) - 1) if out[i]["end_ms"] > out[i+1]["start_ms"])
    json.dump(ts, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n{moved}/{len(out)} blocks adjusted | overlaps {bad} | -> {a.out}")


if __name__ == "__main__":
    main()
