#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a Vagdhenu render_batch shard from the segmented units (this block only).
Meter is assigned per unit; gadya prose uses the 'gadya' reference template.
Shard schema (render_batch.py): {id, meter, padas:[deva], seed, no_sandhi, out}."""
import json

ECE_DIR = "/home/ece/Prathosh/sarvamula_try"
UNITS   = "/Users/prathosh/Sarvamula/audio/units_bsb_1_1_2.json"
OUT     = "/Users/prathosh/Sarvamula/audio/shard_bsb_1_1_2.json"

# per-unit meter (1-indexed to match the printed segmentation)
#  01 sutra→gadya  02 prose→gadya  03 Skanda śloka→anuṣṭubh  04 prose→gadya
#  05 Taittirīya (PROSE mantra)→gadya_mbtn  06-09 Ṛgveda triṣṭubh-family→upajāti  10 prose→gadya
# u05 and u04 use the gadya_mbtn reference (approved by ear 2026-08-02). u04
# "इति स्कान्दे" was GARBLED on plain gadya at seed 60; both gadya_mbtn/seed 60 and
# gadya/seed 62 fixed it, and the reference swap was preferred over a magic seed.
# u02/u10 still on plain gadya — ALT clips below render them both ways to compare.
METERS = ["gadya", "gadya", "anuṣṭubh", "gadya_mbtn", "gadya_mbtn",
          "upajāti", "upajāti", "upajāti", "upajāti", "gadya"]

# NO PRIMER (2026-08-02). The "model eats the first syllable" behaviour was never the
# model — it was gate() in render_batch.py trimming with thresholds meant for stop
# bursts, so any SONORANT onset (vowel, semivowel य/व/र/ल, nasal) got its attack shaved
# and then faded up from zero. Fixed there via soft_onset(); measured on u05 यतो it was
# discarding 120 ms peaking at -13.9 dBFS. The sacrificial ॐ was a workaround for that
# bug and is no longer needed — verified by ear on u05, 2026-08-02.
PRIMER = ""

# per-unit seed overrides (1-indexed) — re-roll units whose default-60 render is off.
# (u04 "इति स्कान्दे" seed 62 was compensating for the same gate bug; back to default,
#  with an ALT clip below to confirm 60 is now fine.)
SEED = {}

# Pada regrouping (1-indexed unit -> groups of source-pada indices, 0-indexed).
# segment.py splits prose at every visarga/daṇḍa, which is right for the visarga echo
# but can over-fragment: each pada becomes its own render segment with a --gap pause
# after it. u05 (Taittirīya) reads better with the last three clauses run together —
# that is the 3-pada grouping approved by ear on 2026-08-02 (was shard_u05f).
PADA_GROUPS = {5: [[0], [1], [2, 3, 4]]}

# extra comparison clips: (unit_index, meter, seed, suffix). Rendered alongside the
# canonical 10 but excluded from the full stitch.
ALTS = [(2, "gadya_mbtn", 60, "ALTMBTN"),
        (10, "gadya_mbtn", 60, "ALTMBTN"),
        (4, "gadya",      62, "ALTSEED62")]   # the other accepted u04; kept for the record

units = json.load(open(UNITS, encoding="utf-8"))
assert len(units) == len(METERS), f"{len(units)} units vs {len(METERS)} meters"

def clip(i, u, meter, seed, suffix=""):
    cid = f"bsb_1_1_2_u{i:02d}_{u['type']}" + (f"_{suffix}" if suffix else "")
    src = list(u["padas"])
    padas = ([" ".join(src[k] for k in grp) for grp in PADA_GROUPS[i]]
             if i in PADA_GROUPS else src)
    if PRIMER: padas[0] = PRIMER + padas[0]
    return {"id": cid, "meter": meter, "padas": padas, "seed": seed,
            "no_sandhi": True, "out": f"{ECE_DIR}/clips/{cid}.wav"}

shard = [clip(i, u, meter, SEED.get(i, 60))
         for i, (u, meter) in enumerate(zip(units, METERS), 1)]
CANON = [c["id"] for c in shard]
shard += [clip(i, units[i-1], meter, seed, suffix) for i, meter, seed, suffix in ALTS]

json.dump(shard, open(OUT, "w"), ensure_ascii=False, indent=1)
json.dump(CANON, open(OUT.replace(".json", "_canon.json"), "w"), indent=1)
print(f"{len(shard)} clips ({len(CANON)} canonical + {len(ALTS)} alt) -> {OUT}")
for c in shard:
    tag = "" if c["id"] in CANON else "   [alt]"
    print(f"  {c['id']:34s} meter={c['meter']:12s} seed={c['seed']} padas={len(c['padas'])}{tag}")
