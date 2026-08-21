#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File, QC and assemble the eight small works rendered in one combined pass.

The seven remaining Daśa Prakaraṇas plus the Saṅgraha Bhāṣya total 478 clips — far too
little to justify a render pass each, so they went out as one combined shard set into a
shared /tmp/prak_out and are separated here by id prefix.
"""
import json, os, subprocess, sys, time

B = "/home/ece/BigDisk/Prathosh/sarvamula_audio"
PY = "/home/ece/Prathosh/miniconda3/envs/indicf5/bin/python"
DROP = "/tmp/prak_out"

WORKS = [  # (slug, prefix, blocks file, shard stem)
    ("pramana_lakshana",             "pl_",  "blocks_pl.json",  "pl_all"),
    ("katha_lakshana",               "kl_",  "blocks_kl.json",  "kl_all"),
    ("upadhi_khandana",              "uk_",  "blocks_uk.json",  "uk_all"),
    ("mayavada_khandana",            "mk_",  "blocks_mk.json",  "mk_all"),
    ("prapancha_mithyatva_khandana", "pmk_", "blocks_pmk.json", "pmk_all"),
    ("tatva_sankhyana",              "tsk_", "blocks_tsk.json", "tsk_all"),
    ("tatva_viveka",                 "tvk_", "blocks_tvk.json", "tvk_all"),
    ("sangraha_bhashya",             "sgb_", "blocks_sgb.json", "sgb_all"),
]


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def sh(cmd, timeout=None):
    r = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


for slug, pre, blocks, stem in WORKS:
    want = {c for b in json.load(open(f"{B}/{blocks}", encoding="utf-8"))
            for u in b["units"] for c in u["clips"]}
    dest = f"{B}/works/{slug}/clips"
    os.makedirs(dest, exist_ok=True)
    n = 0
    for cid in want:
        s, d = f"{DROP}/{cid}.wav", f"{dest}/{cid}.wav"
        if os.path.exists(s) and not os.path.exists(d):
            sh(f"cp {s} {d}"); n += 1
    have = {f[:-4] for f in os.listdir(dest) if f.endswith(".wav")}
    miss = len(want - have)
    log(f"{slug}: filed {n}, {len(want & have)}/{len(want)} present"
        + (f", MISSING {miss}" if miss else ""))
    if miss:
        log(f"  skipping {slug} — assembling with gaps would ship silent holes")
        continue

    rc, out, err = sh(f"cd {B} && {PY} asr_qc_loop.py --shard {B}/{stem}.json "
                      f"--manifest {B}/{stem}_man.json --outdir {dest} "
                      f"--report {B}/works/{slug}/qc_{slug}.json --thresh 0.15 --no-edge --gpu 0",
                      timeout=10800)
    log(f"  QC rc={rc} " + (out.split("\n")[-1] if out else err[-140:]))
    rc, out, err = sh(f"cd {B} && {PY} assemble_bsb.py --blocks {blocks} --clipdir {dest} "
                      f"--outdir {B}/r2 --timings {B}/timings_{slug}.json", timeout=7200)
    log(f"  assembled rc={rc} " + (out.split("\n")[-1] if out else err[-140:]))
log("all eight done")
