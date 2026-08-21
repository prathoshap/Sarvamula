#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ASR-in-the-loop QC for rendered clips. Runs ENTIRELY on ece-box, which has both the
render env (indicf5) and the Su-shrota env (nemo_ai4b) — no cross-box transfer.

    render  ->  ASR transcribe  ->  CER vs source text
                                      |
                            CER > thresh?  -> try variants (other seeds, other voice)
                                      |            -> re-ASR -> keep the LOWEST CER
                                      v
                                  accept

Why ASR and not an acoustic test: an acoustic onset detector cannot tell a dropped
phoneme from a legitimate voiceless-stop burst — it called प्रसिद्धत्वात् truncated when
the प्र was actually present and the word was mangled mid-way instead. ASR reads what was
actually said, which is the thing we care about.

Baseline on BSB 1.1.1+1.1.2 (155 clips, v12-ep9): median CER 0.000, mean 0.028, 65%
perfect. So only a small tail needs rescuing.

Usage (on ece-box):
    python asr_qc_loop.py --shard s.json --manifest m.json --outdir clips \
        --report qc.json [--thresh 0.15] [--seeds 61,62,63] [--alt-voice anuṣṭubh]
"""
import argparse, json, os, subprocess, sys

REND_PY = "/home/ece/Prathosh/miniconda3/envs/indicf5/bin/python"
REND    = "/home/ece/Prathosh/production/render_batch.py"
ASR_PY  = "/home/ece/BigDisk/Prathosh/ASR/envs/nemo_ai4b/bin/python"
HERE    = os.path.dirname(os.path.abspath(__file__))


def render(shard, outdir, tag, gpu=0):
    """One render_batch invocation. Model load (~15s) is amortised over the whole shard,
    so batch as much as possible per call.

    outdir MUST be absolute: render_batch runs with cwd=production/, so a relative
    --outdir resolves there and every clip fails at write with 'System error'. It also
    does not create the directory itself."""
    outdir = os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)
    # skip anything already rendered — makes the loop resumable and avoids redoing the
    # base pass when the clips are already on disk
    todo = [c for c in shard if not os.path.exists(os.path.join(outdir, c["id"] + ".wav"))]
    if not todo:
        print(f"  [render {tag}] all {len(shard)} clips already present, skipping", flush=True)
        return len(shard)
    shard = [{**c, "out": os.path.join(outdir, c["id"] + ".wav")} for c in todo]
    sp = os.path.join(HERE, f"_shard_{tag}.json")
    json.dump(shard, open(sp, "w"), ensure_ascii=False)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu))
    r = subprocess.run([REND_PY, REND, "--shard", sp, "--results",
                        os.path.join(HERE, f"_res_{tag}.json"),
                        "--outdir", outdir, "--gap", "0.55"],
                       cwd="/home/ece/Prathosh/production", env=env,
                       capture_output=True, text=True)
    ok = sum(1 for l in r.stdout.splitlines() if l.startswith("OK"))
    print(f"  [render {tag}] {ok}/{len(shard)} clips", flush=True)
    if ok < len(shard):
        print("  " + "\n  ".join(l for l in r.stdout.splitlines() if l.startswith("FAIL")), flush=True)
    return ok


def asr(clipdir, manifest, tag):
    mp = os.path.join(HERE, f"_man_{tag}.json")
    op = os.path.join(HERE, f"_asr_{tag}.json")
    json.dump(manifest, open(mp, "w"), ensure_ascii=False)
    r = subprocess.run([ASR_PY, os.path.join(HERE, "asr_verify.py"),
                        "--clipdir", clipdir, "--manifest", mp, "--out", op],
                       capture_output=True, text=True)
    if not os.path.exists(op):
        print(r.stdout[-2000:], r.stderr[-2000:]); sys.exit("ASR failed")
    rows = json.load(open(op, encoding="utf-8"))
    print(f"  [asr {tag}] {len(rows)} clips, "
          f"{sum(1 for x in rows if x['cer']==0)} perfect", flush=True)
    return {x["clip"]: x for x in rows}


# Calibrated on 157 real clips (soft-onset n=115). Distribution:
#   p50 -35 | p75 -29 | p90 -23 | p95 -21
# The clip reported clipped by ear (bare "इति") sits at -22.9, so the threshold has to be
# at or above -23 to catch it: -30 flagged 31% of everything (useless), -22 flagged a tidy
# 9/157 but MISSED इति by 0.9 dB. -23 catches all 5 इति instances at 15/157 (~10 GPU-min
# of variants). Anchor any retune on that clip, not on the percentile.
ONSET_MAX_DB = -23.0

# CODA CHECK DELIBERATELY DISABLED. A clipped final म् is audible ("एष मोहम्") but I have
# no detector for it: ASR transcribes it correctly (CER 0.00, and the raw hypotheses show
# final म् rendered fine elsewhere — स्वयम्, नियामकम्, कर्मवान् — so canon() is not hiding
# it), and its tail of 10.4 ms is ABOVE the 4 ms median for halant-final clips. Any
# threshold that flags it flags most healthy clips too (tail<8ms fires on 62%). Shipping a
# check with no validated signal would just burn GPU on random re-rolls. Needs either a
# better measure (final-nasal murmur energy?) or an ear.
CODA_CHECK = False
CODA_MIN_TAIL_MS = 3.0


def penalty(r, edge=True):
    """Acoustic penalty on top of CER — ASR confirms a phoneme is PRESENT, not INTACT.
    'इति' loses its इ while still transcribing perfectly, so CER alone cannot see it.
    Gated on the text (see edge_metrics) so it cannot fire on a voiceless-stop burst,
    which legitimately starts loud and which an ungated version flagged 44% of the time."""
    p = 0.0
    if not r.get("head_ok", True):
        p += 1.0
    if edge and r.get("chk_onset") and r.get("onset_db", -120) > ONSET_MAX_DB:
        p += 0.5
    if edge and CODA_CHECK and r.get("chk_coda") and r.get("tail_ms", 99) < CODA_MIN_TAIL_MS:
        p += 0.5
    return p


_EDGE = True          # set from --no-edge in main()

def score(r):
    return r["cer"] + penalty(r, _EDGE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--report", default="qc_report.json")
    ap.add_argument("--thresh", type=float, default=0.15)
    ap.add_argument("--seeds", default="61,62,63")
    ap.add_argument("--sps", default="0.35,0.45", help="fix_duration widening to try")
    ap.add_argument("--alt-voice", default="anuṣṭubh")
    ap.add_argument("--gpu", type=int, default=0)
    ap.add_argument("--no-edge", action="store_true",
                    help="score on CER + head only; skip the acoustic onset/coda penalty")
    a = ap.parse_args()
    global _EDGE
    _EDGE = not a.no_edge

    shard = json.load(open(a.shard, encoding="utf-8"))
    man = json.load(open(a.manifest, encoding="utf-8"))
    byid = {c["id"]: c for c in shard}

    # pass 0 — render everything once, score everything once
    render(shard, a.outdir, "base", a.gpu)
    scored = asr(a.outdir, man, "base")

    # Flag on CER **or** a head mismatch. CER alone misses the failure that matters most:
    # a dropped FIRST WORD in a longer pada barely moves it — "अतो ब्रह्मजिज्ञासा कर्तव्या"
    # rendered as "ब्रह्मजिज्ञासा कर्तव्या" scores only 0.120 and sails through, yet the
    # word is simply gone. head_ok compares the first akṣaras specifically, so onset drops
    # surface regardless of pada length.
    flagged = sorted([c for c, r in scored.items() if score(r) > a.thresh],
                     key=lambda c: -score(scored[c]))
    n_cer  = sum(1 for c in flagged if scored[c]["cer"] > a.thresh)
    n_edge = sum(1 for c in flagged if scored[c]["cer"] <= a.thresh and penalty(scored[c]) > 0)
    print(f"\nflagged {len(flagged)}/{len(scored)} "
          f"(CER>{a.thresh}: {n_cer}, edge/head only: {n_edge})", flush=True)

    # ROUND-BASED RESCUE with early exit. Rendering every variant up front cost 5,958
    # renders for 993 flagged clips (~13 GPU-h). Most rescues succeed on the FIRST
    # alternate seed, so instead: try one candidate for all still-failing clips, ASR that
    # batch, drop whoever passed, and only then move to the next candidate. Batching by
    # ROUND keeps the ~15s model load amortised while skipping variants nobody needs.
    cands = [("seed", int(x)) for x in a.seeds.split(",") if x.strip()]
    if a.alt_voice:
        cands.append(("voice", a.alt_voice))

    winners, remaining = {}, list(flagged)
    for kind, val in cands:
        if not remaining:
            break
        batch = []
        for cid in remaining:
            base = byid[cid]
            if kind == "seed":
                vid = f"{cid}__s{val}"
                batch.append({**base, "id": vid, "seed": val,
                              "out": os.path.join(os.path.abspath(a.outdir), vid + ".wav")})
            else:
                alt = val
                if base.get("meter") == alt:
                    alt = "gadya_mbtn" if alt == "anuṣṭubh" else "anuṣṭubh"
                if base.get("meter") == alt:
                    continue
                vid = f"{cid}__v"
                batch.append({**base, "id": vid, "meter": alt,
                              "out": os.path.join(os.path.abspath(a.outdir), vid + ".wav")})
        if not batch:
            continue
        tag = f"{kind}{val}".replace(".", "")
        print(f"\nround {kind}:{val} — {len(batch)} clips still failing", flush=True)
        render(batch, a.outdir, tag, a.gpu)
        vman = {v["id"]: man[v["id"].split("__")[0]] for v in batch}
        vs = asr(a.outdir, vman, tag)

        still = []
        for v in batch:
            cid = v["id"].split("__")[0]
            r = vs.get(v["id"])
            if r and score(r) <= a.thresh and score(r) < score(scored[cid]):
                winners[cid] = {"cer_before": scored[cid]["cer"], "cer_after": r["cer"],
                                "won_by": f"{kind}:{val}", "file": v["id"],
                                "ref": scored[cid]["ref"], "hyp_before": scored[cid]["hyp"]}
                os.replace(os.path.join(a.outdir, v["id"] + ".wav"),
                           os.path.join(a.outdir, cid + ".wav"))
            else:
                still.append(cid)
        print(f"  rescued {len(batch)-len(still)}, {len(still)} still failing", flush=True)
        remaining = still

    for cid in remaining:                       # never rescued — keep the original
        winners[cid] = {"cer_before": scored[cid]["cer"], "cer_after": scored[cid]["cer"],
                        "won_by": "original", "file": cid,
                        "ref": scored[cid]["ref"], "hyp_before": scored[cid]["hyp"]}

    rep = {"n": len(scored), "flagged": len(flagged),
           "thresh": a.thresh, "winners": winners,
           "cer_all": {c: r["cer"] for c, r in scored.items()}}
    json.dump(rep, open(a.report, "w"), ensure_ascii=False, indent=1)

    imp = [w for w in winners.values() if w["cer_after"] < w["cer_before"]]
    print(f"\nrescued {len(imp)}/{len(flagged)} flagged clips")
    for c, w in sorted(winners.items(), key=lambda x: -x[1]["cer_before"])[:12]:
        arrow = "->" if w["cer_after"] < w["cer_before"] else "  (no better)"
        print(f"  {w['cer_before']:.2f} {arrow} {w['cer_after']:.2f}  via {w['won_by']:18s} {w['ref'][:34]}")
    print(f"\nreport -> {a.report}")


if __name__ == "__main__":
    main()
