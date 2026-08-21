#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verify rendered clips against their source text with Su-shrota (v12-ep9).

Runs ON ece-box, where the model and its NeMo env live:
    model /home/ece/BigDisk/Prathosh/ASR/exp/ft_ctc_v12/ft_ctc_ep9.nemo   (PINNED, not
          the ft_ctc_current.nemo symlink — that repoints on deploy and would silently
          change results)
    env   /home/ece/BigDisk/Prathosh/ASR/envs/nemo_ai4b/bin/python

Aggregate multilingual IndicConformer: decode the CTC head on the Sanskrit token slice.

Why this and not just the acoustic onset test: the acoustic test cannot tell a dropped
first phoneme from a legitimate voiceless-stop burst. ASR can — if the transcript is
missing the first akṣara, the audio really is missing it.

A 0.3 s silence pre/post-roll is added to every clip because the ASR itself clips onsets
and tails; without it the measurement would blame the TTS for the ASR's own truncation.

Usage (on the box):
    python asr_verify.py --clipdir <dir of 24k wavs> --manifest manifest.json --out asr.json
manifest.json = {clip_id: expected_devanagari_text}
"""
import argparse, json, os, re, sys
import numpy as np

ROOT = "/home/ece/BigDisk/Prathosh/ASR"
MODEL = f"{ROOT}/exp/ft_ctc_v12/ft_ctc_ep9.nemo"
LABELS = f"{ROOT}/data/eval_logits/labels.json"
OFF, V, BL = 4096, 256, 5632          # Sanskrit slice of the aggregate vocab
PREROLL = 0.3                          # seconds of silence pre/post


def _lse(x, ax):
    m = x.max(ax, keepdims=True)
    return m + np.log(np.exp(x - m).sum(ax, keepdims=True))


def load_model():
    import torch
    import nemo.collections.asr as na
    m = na.models.EncDecHybridRNNTCTCBPEModel.restore_from(MODEL, map_location="cuda").eval()
    lab = json.load(open(LABELS))
    return m, lab, torch


def transcribe(m, lab, torch, wav16):
    sig = torch.tensor(wav16).unsqueeze(0).cuda()
    sl = torch.tensor([len(wav16)]).cuda()
    with torch.no_grad():
        enc, _ = m.forward(input_signal=sig, input_signal_length=sl)
        lp = m.ctc_decoder(encoder_output=enc)[0].cpu().numpy()
    cols = [BL] + list(range(OFF, OFF + V))
    P = lp[:, cols]
    P = P - _lse(P, 1)
    ids = P.argmax(1)
    out, prev = [], -1
    for i in ids:
        i = int(i)
        if i != prev and i != 0:
            out.append(lab[i - 1])
        prev = i
    return "".join(out).replace("▁", " ").strip()


def read16k(path, sr_target=16000):
    """24k -> 16k by 2:3 decimation via polyphase if scipy is present, else ffmpeg."""
    import soundfile as sf
    a, sr = sf.read(path, dtype="float32")
    if a.ndim > 1:
        a = a.mean(1)
    if sr != sr_target:
        try:
            from scipy.signal import resample_poly
            a = resample_poly(a, sr_target, sr).astype("float32")
        except Exception:
            import subprocess, tempfile
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                tmp = f.name
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", path,
                            "-ar", str(sr_target), "-ac", "1", tmp], check=True)
            a, _ = sf.read(tmp, dtype="float32")
            os.unlink(tmp)
    pad = np.zeros(int(PREROLL * sr_target), dtype="float32")
    return np.concatenate([pad, a, pad])


# ── text comparison ───────────────────────────────────────────────────────────
_AK = re.compile(r"[अ-हऽ]")

# ── acoustic edge quality ─────────────────────────────────────────────────────
# ASR verifies that a phoneme is PRESENT, not that it is intact: "एष मोहम्" scored CER
# 0.00 while its final म् was audibly clipped. These two measures give the QC loop ears.
#
# Applied SELECTIVELY, because the naive versions produce false positives:
#   onset — only for a clip beginning with a vowel or sonorant. Those ramp in, so a loud
#           first frame means the attack is missing. A voiceless stop legitimately starts
#           at its burst, and judging those flagged 44% of perfectly good clips.
#   coda  — only for a halant-final clip (त्/म्/क्). A final consonant should decay; the
#           audio ending flush at speaking level means it was cut off.
_STOPS_SLP = set("kKgGcCjJwWqQtTdDpPbB")
_VIRAMA = "्"

def edge_metrics(wav, sr, ref):
    """(onset_db, coda_db, tail_ms) plus which checks apply to this text."""
    w = int(0.02 * sr)
    amp = 3e-3
    m = np.abs(wav) > amp
    if not m.any():
        return {"onset_db": -120.0, "coda_db": -120.0, "tail_ms": 0.0,
                "chk_onset": False, "chk_coda": False}
    i = int(np.argmax(m))
    j = len(wav) - 1 - int(np.argmax(m[::-1]))
    d = lambda s: 20*np.log10(max(float(np.sqrt((s**2).mean())), 1e-9)) if len(s) else -120.0
    try:
        from indic_transliteration import sanscript
        slp = sanscript.transliterate(ref, sanscript.DEVANAGARI, sanscript.SLP1).strip()
    except Exception:
        slp = ""
    soft_onset = bool(slp) and slp[0] not in _STOPS_SLP
    t = (ref or "").rstrip(" ।॥|.,;:!?")
    return {"onset_db": round(d(wav[i:i+w]), 1),
            "coda_db": round(d(wav[max(0, j-w):j+1]), 1),
            "tail_ms": round((len(wav)-1-j)/sr*1000, 1),
            "chk_onset": soft_onset,
            "chk_coda": bool(t) and t[-1] == _VIRAMA}

def canon(s):
    """Light canonicalization: drop punctuation/whitespace and word-final anusvāra-vs-म्
    variation, which the ASR renders inconsistently and which we do not care about."""
    s = re.sub(r"[।॥\s,;\-'\"“”]", "", s or "")
    s = s.replace("म्", "ं")
    return s


def cer(a, b):
    a, b = canon(a), canon(b)
    if not b:
        return 0.0 if not a else 1.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / len(b)


def head_ok(hyp, ref, n=3):
    """Does the transcript BEGIN with the reference's first n akṣaras? This is the
    onset test — a dropped first phoneme shows up here even when overall CER is fine."""
    h, r = canon(hyp), canon(ref)
    if len(r) < n:
        n = len(r)
    if not n:
        return True
    # compare EQUAL-LENGTH heads — comparing hyp[:n+2] to ref[:n] charged the two extra
    # characters as insertions, so a perfect transcript always failed.
    # One substitution in n akṣaras is tolerated (ASR runs ~7% CER on prose).
    return cer(h[:n], r[:n]) <= 0.34


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clipdir", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    man = json.load(open(a.manifest, encoding="utf-8"))
    items = [(k, v) for k, v in man.items()
             if os.path.exists(os.path.join(a.clipdir, k + ".wav"))]
    if a.limit:
        items = items[:a.limit]
    print(f"{len(items)} clips to verify", flush=True)

    m, lab, torch = load_model()
    print("model loaded", flush=True)

    rows = []
    for i, (cid, ref) in enumerate(items, 1):
        wav = read16k(os.path.join(a.clipdir, cid + ".wav"))
        hyp = transcribe(m, lab, torch, wav)
        # measure the clip WITHOUT the pre/post-roll padding read16k added
        pad = int(PREROLL * 16000)
        em = edge_metrics(wav[pad:len(wav)-pad], 16000, ref)
        rows.append({"clip": cid, "ref": ref, "hyp": hyp,
                     "cer": round(cer(hyp, ref), 4), "head_ok": head_ok(hyp, ref), **em})
        if i % 20 == 0:
            print(f"  {i}/{len(items)}", flush=True)

    json.dump(rows, open(a.out, "w"), ensure_ascii=False, indent=1)
    bad_head = [r for r in rows if not r["head_ok"]]
    print(f"\nwritten {a.out}")
    print(f"  median CER {np.median([r['cer'] for r in rows]):.3f}")
    print(f"  HEAD MISMATCH (onset likely dropped): {len(bad_head)}/{len(rows)}")


if __name__ == "__main__":
    main()
