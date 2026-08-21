#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Can Su-shrota hear this recording at all? Runs ON box1.

    ASR_PY asr_hear_test.py --wav X.wav --ts TS_X.json --src X_by_shloka.json --onset 7.796 -n 12

Before tuning an aligner, establish whether the model recognises the material. Forced
alignment can only place text the acoustic model has some belief in; if the posteriors are
flat, every knob in the aligner is decoration.

Decodes each block greedily between its own tap marks and reports character error against the
text that was recited. Compare against a recording known to align well — Ṛgveda scored a
median -0.69 path likelihood, Dvādaśa -0.55, Swara -1.67, and this says whether that gap is
the model failing to recognise the chant or the aligner misplacing text it did recognise.
"""
import argparse, json, re, sys, unicodedata
import numpy as np

ROOT = "/home/ece/BigDisk/Prathosh/ASR"
MODEL = f"{ROOT}/exp/ft_ctc_v12/ft_ctc_ep9.nemo"
OFF, V, BL = 4096, 256, 5632
SR = 16000
SV = re.compile(r"[॒॑॓॔᳐-᳿꣠-ꣿ]")


def norm(s, keep_svara=False):
    s = unicodedata.normalize("NFC", s or "")
    if not keep_svara:
        s = SV.sub("", s)
    return re.sub(r"\s+", " ", re.sub(r"[०-९\d/।॥\|]+", " ", s)).strip()


def cer(ref, hyp):
    r, h = list(ref.replace(" ", "")), list(hyp.replace(" ", ""))
    if not r:
        return 1.0
    d = np.arange(len(h) + 1)
    for i, rc in enumerate(r, 1):
        prev, d[0] = d[0], i
        for j, hc in enumerate(h, 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j-1] + 1, prev + (rc != hc))
            prev = cur
    return d[len(h)] / len(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", required=True)
    ap.add_argument("--ts", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--onset", type=float, required=True)
    ap.add_argument("-n", type=int, default=12)
    ap.add_argument("--only", default="")
    a = ap.parse_args()

    import torch, soundfile as sf
    import nemo.collections.asr as na
    m = na.models.EncDecHybridRNNTCTCBPEModel.restore_from(MODEL, map_location="cuda").eval()

    x, sr = sf.read(a.wav, dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    if sr != SR:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(int(sr), SR)
        x = resample_poly(x, SR // g, int(sr) // g).astype("float32")

    blocks = json.load(open(a.ts, encoding="utf-8"))["blocks"]
    src = json.load(open(a.src, encoding="utf-8"))["content"]
    idxs = ([int(i) for i in a.only.split(",") if i.strip()] if a.only
            else list(np.linspace(0, len(blocks) - 1, a.n, dtype=int)))

    scores = []
    for i in idxs:
        k = blocks[i]
        s = k["start_ms"] / 1000.0 + a.onset
        e = k["end_ms"] / 1000.0 + a.onset
        seg = x[int(s * SR):int(e * SR)]
        if len(seg) < SR // 2:
            continue
        sig = torch.tensor(seg).unsqueeze(0).cuda()
        sl = torch.tensor([len(seg)]).cuda()
        with torch.no_grad():
            enc, _ = m.forward(input_signal=sig, input_signal_length=sl)
            lp = m.ctc_decoder(encoder_output=enc)[0].cpu().numpy()
        P = lp[:, [BL] + list(range(OFF, OFF + V))]
        best = P.argmax(1)
        out, prev = [], -1
        for b in best:
            if b != prev and b != 0:
                out.append(int(b) - 1)      # sentencepiece rejects numpy ints
            prev = b
        hyp = m.tokenizer.ids_to_text(out, "sa") if out else ""
        ref = norm(" ".join(src[k["id"]][0]["text"]))
        c = cer(ref, norm(hyp))
        scores.append(c)
        blank = float(np.exp(P[:, 0] - P.max(1)).mean())
        print(f"#{i:4d} CER {c:5.1%}  blank-dominance {blank:.2f}  {e-s:5.1f}s")
        print(f"   ref: {ref[:78]}")
        print(f"   hyp: {norm(hyp)[:78]}")
    if scores:
        print(f"\nmedian CER {np.median(scores):.1%} over {len(scores)} blocks"
              f"  (a model that hears the material lands well under 30%)")


if __name__ == "__main__":
    main()
