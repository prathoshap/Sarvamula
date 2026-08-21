#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic sweep for the tiny connective units (u04 "इति स्कान्दे", u10 "इत्यादि च").

These are ~4 aksharas rendered against an ~8s prose reference — roughly an 8:1
ref:target ratio, which is where F5 tends to degrade. render_batch.py exposes the
levers we need per clip:

    sps       duration override; fix_duration = ref_len + nsyll*sps.
              sps = 0 disables fix_duration entirely (pure speed-based).
    speed     pace (lower = slower/more elongated)
    ref_wav   use a different reference audio than the meter's

So the sweep separates three candidate causes:
  A. unlucky seed            -> vary seed, everything else fixed
  B. target too short/rushed -> raise sps, or drop fix_duration (sps=0), or slow down
  C. reference too long      -> swap in a SHORT reference (anuṣṭubh 3.9s, pramāṇikā 4.0s)

Usage: sweep_u04.py [--unit 4] > shard_sweep_u04.json
"""
import argparse, json

ECE  = "/home/ece/Prathosh/sarvamula_try"
BANK = "/home/ece/Prathosh/production/reference_bank"
UNITS = "/Users/prathosh/Sarvamula/audio/units_bsb_1_1_2.json"

ap = argparse.ArgumentParser()
ap.add_argument("--unit", type=int, default=4)
ap.add_argument("--out", default="/Users/prathosh/Sarvamula/audio/shard_sweep_u04.json")
a = ap.parse_args()

u = json.load(open(UNITS, encoding="utf-8"))[a.unit - 1]
text = u["padas"][0]
tag = f"u{a.unit:02d}"

def c(suffix, meter="gadya", seed=60, **kw):
    d = {"id": f"sweep_{tag}_{suffix}", "meter": meter, "padas": [text],
         "seed": seed, "no_sandhi": True, "out": f"{ECE}/clips/sweep_{tag}_{suffix}.wav"}
    d.update(kw)
    return d

shard = []
# A. seed sweep, everything else at the block's settings
for s in (60, 61, 62, 63, 64, 65):
    shard.append(c(f"seed{s}", seed=s))
# B. give the utterance more room / drop the duration constraint / slow it down
shard.append(c("sps035", sps=0.35))
shard.append(c("sps045", sps=0.45))
shard.append(c("spsFREE", sps=0.0))          # no fix_duration at all
shard.append(c("speed080", speed=0.80))
# C. short reference instead of the 8s prose one
shard.append(c("refanu",   meter="anuṣṭubh"))
shard.append(c("refpram",  meter="pramāṇikā"))
# and the other prose reference, for completeness
shard.append(c("mbtn", meter="gadya_mbtn"))
shard.append(c("mbtn_sps035", meter="gadya_mbtn", sps=0.35))

json.dump(shard, open(a.out, "w"), ensure_ascii=False, indent=1)
print(f"{len(shard)} clips for {tag} {text!r} -> {a.out}")
for x in shard:
    extra = " ".join(f"{k}={v}" for k, v in x.items()
                     if k in ("sps", "speed") )
    print(f"  {x['id']:26s} meter={x['meter']:12s} seed={x['seed']} {extra}")
