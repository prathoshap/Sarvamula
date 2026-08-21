#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recover each block's true edges by forced-aligning its own text with Su-shrota. Runs ON box1.

    ASR_PY align_ts_asr.py --wav X.wav --ts TS_X.json --src X_by_shloka.json \
                           --onset 5.236 --out TS_X.aligned.json

The recorder's marks are the TAP, and the tap is late at both edges: a start lands after the
reciter has resumed, so the opening word is missing; an end lands after the NEXT mantra has
begun, so its opening rides along at the tail. Both failures were confirmed by ear on
rv_0020 — "यदङ्ग" clipped off the front, the next mantra audible at the back.

Nothing acoustic can fix this. Where recitation runs on there is no pause to snap to, and a
throat-clear is bounded by pauses exactly as speech is (one measured 0.151 RMS, the level of
quiet recitation). Only the text knows where a mantra stops.

GUARD TOKENS are what makes it work. Aligning a block's tokens alone and taking the first and
last occupied frames fails: Viterbi must consume every token somewhere, so with bleeding audio
still in the window the final token drifts late into the next mantra (rv_0047's end moved
+1131 ms the wrong way when tried that way). So each window is aligned against

    [tail of the previous mantra] + [this mantra] + [head of the next mantra]

and the edges are read from the span of THIS mantra's first and last tokens. The neighbouring
audio now has its own tokens to occupy, and stops competing for ours. It is self-correcting in
the other direction too: when the tail really is silence, the guard tokens squeeze into it at
low likelihood and our last token still ends where the voice does.

The CTC head is peaky — blank through most of a syllable with a spike at its centre — so its
non-blank frames are token centres, not speech boundaries. Hence a real forced alignment
rather than a blank-probability threshold, which was tried first and returned +0 ms ends.
"""
import argparse, json, os, re, sys
import numpy as np

ROOT = "/home/ece/BigDisk/Prathosh/ASR"
MODEL = f"{ROOT}/exp/ft_ctc_v12/ft_ctc_ep9.nemo"
OFF, V, BL = 4096, 256, 5632          # Sanskrit slice of the aggregate vocab
SR = 16000
NEG = -1e30


def load_model():
    import torch
    import nemo.collections.asr as na
    m = na.models.EncDecHybridRNNTCTCBPEModel.restore_from(MODEL, map_location="cuda").eval()
    return m, torch


def posteriors(m, torch, wav):
    """(frames, 1+V) log-probs over [blank] + the Sanskrit token slice."""
    sig = torch.tensor(wav).unsqueeze(0).cuda()
    sl = torch.tensor([len(wav)]).cuda()
    with torch.no_grad():
        enc, _ = m.forward(input_signal=sig, input_signal_length=sl)
        lp = m.ctc_decoder(encoder_output=enc)[0].cpu().numpy()
    P = lp[:, [BL] + list(range(OFF, OFF + V))]
    mx = P.max(1, keepdims=True)
    return P - (mx + np.log(np.exp(P - mx).sum(1, keepdims=True)))


def ctc_path(P, ids):
    """Viterbi-align token ids to frames; return the per-frame extended-state path and score.

    Standard CTC over the blank-extended label sequence: from state s you may stay, advance
    one, or — only between two DIFFERENT labels — skip the blank between them."""
    T = P.shape[0]
    ext = [0]
    for t in ids:
        ext += [t + 1, 0]                      # column 0 is blank; token id t is column t+1
    S = len(ext)
    if T < S // 2 or S == 1:
        return None, None
    ext_a = np.array(ext)
    dp = np.full((T, S), NEG)
    bk = np.zeros((T, S), dtype=np.int8)
    dp[0, 0] = P[0, ext[0]]
    if S > 1:
        dp[0, 1] = P[0, ext[1]]
    # a label may be reached from s-2 only when it differs from the label two back
    skip_ok = np.zeros(S, dtype=bool)
    skip_ok[2:] = (ext_a[2:] != 0) & (ext_a[2:] != ext_a[:-2])
    for t in range(1, T):
        prev = dp[t-1]
        c0 = prev
        c1 = np.concatenate(([NEG], prev[:-1]))
        c2 = np.where(skip_ok, np.concatenate(([NEG, NEG], prev[:-2])), NEG)
        stack = np.vstack([c0, c1, c2])
        arg = stack.argmax(0)
        dp[t] = stack[arg, np.arange(S)] + P[t, ext_a]
        bk[t] = arg
    s = S - 1 if dp[T-1, S-1] >= dp[T-1, S-2] else S - 2
    score = dp[T-1, s] / T
    path = np.empty(T, dtype=np.int32)
    for t in range(T-1, -1, -1):
        path[t] = s
        s -= bk[t, s]
    return path, float(score)


def toks(m, txt):
    txt = re.sub(r"[०-९\d/।॥\|]+", " ", txt or "").strip()
    if not txt:
        return []
    try:
        return m.tokenizer.text_to_ids(txt, "sa")
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--ts", required=True)
    ap.add_argument("--src", required=True, help="the by_shloka file the recording was made from")
    ap.add_argument("--onset", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pre", type=float, default=2.0,
                    help="look back this far when the previous block abuts this one")
    ap.add_argument("--pre-gap", type=float, default=1.0,
                    help="look back only this far when a discarded take precedes the mark")
    ap.add_argument("--post", type=float, default=3.0)
    ap.add_argument("--guard", type=int, default=6, help="neighbour tokens to align alongside")
    ap.add_argument("--chunk", type=int, default=1,
                    help="align this many consecutive blocks as ONE token sequence and read "
                         "every internal boundary from the single path. Needed wherever verses "
                         "share a refrain: aligned one at a time, the guard tokens cannot tell "
                         "one repetition from the next and a block swallows its neighbour's "
                         "audio (Dvādaśa #147 took #148's, leaving it 150 ms long). Aligned "
                         "together, both repetitions must be accounted for at once.")
    ap.add_argument("--max-shift", type=float, default=3.0)
    ap.add_argument("--max-late", type=float, default=1.2,
                    help="reject an edge that moves LATER by more than this. The tap is late at "
                         "both edges — every recording measured says so — so a boundary running "
                         "forward by seconds is the path having slid, not a discovery. Catches "
                         "what repeated text does to alignment: Dvādaśa's 12th stotra ends every "
                         "verse with the same refrain, and the path slid a whole verse for +5.4s.")
    ap.add_argument("--min-keep", type=float, default=0.35,
                    help="reject a result shorter than this fraction of the tap duration")
    ap.add_argument("--pad", type=float, default=0.05)
    ap.add_argument("--only", default="", help="comma-separated block indices, for a trial run")
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
    src = json.load(open(a.src, encoding="utf-8"))["content"]
    only = {int(i) for i in a.only.split(",") if i.strip()} if a.only else None

    def text_of(i):
        if not (0 <= i < len(blocks)):
            return ""
        k = blocks[i]["id"]
        return " ".join(src[k][0]["text"]) if k in src else ""

    m, torch = load_model()
    moved = rejected = 0
    step = max(1, a.chunk)
    for g0 in range(0, len(blocks), step):
        grp = [i for i in range(g0, min(g0 + step, len(blocks)))
               if (only is None or i in only) and toks(m, text_of(i))]
        if not grp:
            continue
        first, last = grp[0], grp[-1]
        s = blocks[first]["start_ms"] / 1000.0 + a.onset
        e = blocks[last]["end_ms"] / 1000.0 + a.onset
        prev_e = (blocks[first-1]["end_ms"] / 1000.0 + a.onset) if first else 0.0

        # A gap before the mark means a DISCARDED TAKE of this same mantra sits there. Reaching
        # into it is how the aligner would latch onto the wrong recitation, so look back less.
        pre = a.pre if (first and abs(prev_e - s) < 0.05) else a.pre_gap
        w0, w1 = max(0.0, s - pre), min(dur, e + a.post)
        seg = x[int(w0 * SR):int(w1 * SR)]
        if len(seg) < SR // 2:
            continue

        # one token sequence for the whole chunk, remembering where each block sits in it
        left = toks(m, text_of(first-1))[-a.guard:] if first else []
        ids = list(left)
        at = {}
        for i in grp:
            t = toks(m, text_of(i))
            at[i] = (len(ids), len(ids) + len(t) - 1)
            ids += t
        ids += toks(m, text_of(last+1))[:a.guard]

        P = posteriors(m, torch, seg)
        hop = (len(seg) / SR) / len(P)
        path, score = ctc_path(P, ids)
        if path is None:
            continue
        for i in grp:
            k = blocks[i]
            j0, j1 = at[i]
            f_first = np.where(path == 2 * j0 + 1)[0]
            f_last = np.where(path == 2 * j1 + 1)[0]
            if not len(f_first) or not len(f_last):
                continue
            bs = k["start_ms"] / 1000.0 + a.onset
            be = k["end_ms"] / 1000.0 + a.onset
            ns = w0 + f_first[0] * hop - a.pad
            ne = w0 + (f_last[-1] + 1) * hop + a.pad
            why = ""
            if abs(ns - bs) > a.max_shift or abs(ne - be) > a.max_shift:
                why = "beyond max-shift"
            elif ns - bs > a.max_late or ne - be > a.max_late:
                why = "moved later"
            elif ne - ns < a.min_keep * (be - bs):
                why = "collapsed"
            elif ne <= ns:
                why = "inverted"
            if why:
                rejected += 1
                print(f"  #{i:4d} REJECT {ns-bs:+.2f} {ne-be:+.2f}  ({why}, score {score:.2f})",
                      flush=True)
                continue
            k["start_ms"] = int(round((ns - a.onset) * 1000))
            k["end_ms"] = int(round((ne - a.onset) * 1000))
            k["duration_ms"] = k["end_ms"] - k["start_ms"]
            k["align_score"] = round(score, 3)
            moved += 1
            print(f"  #{i:4d} start {bs:8.3f}->{ns:8.3f} ({(ns-bs)*1000:+6.0f}ms)  "
                  f"end {be:8.3f}->{ne:8.3f} ({(ne-be)*1000:+6.0f}ms)  sc {score:5.2f}", flush=True)

    # order must survive: a later block may not begin before an earlier one ends
    fixed = 0
    for i in range(len(blocks) - 1):
        if blocks[i]["end_ms"] > blocks[i+1]["start_ms"]:
            blocks[i]["end_ms"] = blocks[i+1]["start_ms"]
            blocks[i]["duration_ms"] = blocks[i]["end_ms"] - blocks[i]["start_ms"]
            fixed += 1
    json.dump(ts, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\naligned {moved}/{len(blocks)} | rejected {rejected} | {fixed} overlaps trimmed"
          f" -> {a.out}")


if __name__ == "__main__":
    main()
