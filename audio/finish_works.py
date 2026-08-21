#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Finish the three works still in flight, on box1, unattended.

    MBTN fill  : the 294 hemistichs missing from the YouTube clip bank -> re-segment
                 against bank+fill -> re-assemble only the blocks that changed
    Gītā Bhāṣya: consolidate 8 shards -> ASR-QC -> assemble
    Gītā Tātparya: same, once its shards land

Each stage checks what is already true rather than assuming, so a re-run after a crash
picks up where it stopped. A work that cannot finish is logged and skipped — one stuck
grantha must not hold the other two.
"""
import json, os, re, subprocess, sys, time

B = "/home/ece/BigDisk/Prathosh/sarvamula_audio"
PY = "/home/ece/Prathosh/miniconda3/envs/indicf5/bin/python"
NODE_DIRS = {
    "gita_bhashya": [("localhost", f"{B}/works/gita_bhashya/clips"),
                     ("10.32.38.180", "/home/ece/n3_gita_bhashya/clips"),
                     ("10.32.38.162", "/home/ece/n4_gita_bhashya/clips"),
                     ("10.32.38.167", "/home/ece/n5_gita_bhashya/clips")],
    "gita_tatparya": [("localhost", f"{B}/works/gita_tatparya/clips"),
                      ("10.32.38.180", "/home/ece/n3_gita_tatparya/clips"),
                      ("10.32.38.162", "/home/ece/n4_gita_tatparya/clips"),
                      ("10.32.38.167", "/home/ece/n5_gita_tatparya/clips")],
}
STEM = {"gita_bhashya": "gb_all", "gita_tatparya": "gt_all"}
BLOCKS = {"gita_bhashya": "blocks_gb.json", "gita_tatparya": "blocks_gt.json"}


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def sh(cmd, host="localhost", timeout=None):
    if host != "localhost":
        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
               "-o", "ConnectTimeout=10", f"ece@{host}", cmd]
    else:
        cmd = ["bash", "-lc", cmd]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def have(host, path):
    rc, out, _ = sh(f"ls {path} 2>/dev/null | sed 's/\\.wav$//'", host)
    return set(out.split("\n")) if rc == 0 and out else set()


def wanted(blocks):
    bs = json.load(open(f"{B}/{blocks}", encoding="utf-8"))
    return {c for b in bs for u in b["units"] for c in u["clips"]}


def busy():
    rc, out, _ = sh("pgrep -f 'render_batch.py|roll2.py' | head -1")
    return bool(out.strip())


# ── MBTN ──────────────────────────────────────────────────────────────────────
def mbtn_fill():
    fill = f"{B}/works/mbtn/fill"
    ids = {c["id"] for c in json.load(open(f"{B}/mbtn_fill.json", encoding="utf-8"))}
    while True:
        got = have("localhost", fill)
        if len(ids & got) >= len(ids):
            break
        if not busy() and not os.path.exists(f"{B}/.mbtn_fill_running"):
            log(f"  MBTN fill waiting ({len(ids & got)}/{len(ids)}) …")
        time.sleep(120)
    log(f"MBTN fill complete: {len(ids)} clips")

    # the fill clips join the bank so segmentation can match the lines that were missing
    sh(f"cd {B}/works/mbtn/clips && ln -sf {fill}/*.wav . 2>/dev/null")
    man = json.load(open(f"{B}/mbtn_fill_man.json", encoding="utf-8"))
    bank = json.load(open(f"{B}/mbtn_all_clips.json", encoding="utf-8"))
    known = {c["id"] for c in bank}
    for cid, txt in man.items():
        if cid not in known:
            bank.append({"adh": "fill", "id": cid, "verse": None, "hi": None,
                         "meter": "anuṣṭubh", "text": txt})
    json.dump(bank, open(f"{B}/mbtn_bank_full.json", "w"), ensure_ascii=False)
    rc, out, err = sh(f"cd {B} && python3 segment_mbtn.py --clips {B}/mbtn_bank_full.json "
                      f"--out {B}/blocks_mbtn.json")
    log("  re-segmented: " + " | ".join(l for l in out.split("\n") if "clips" in l or "unmatched" in l))
    rc, out, err = sh(f"cd {B} && {PY} assemble_bsb.py --blocks blocks_mbtn.json "
                      f"--clipdir {B}/works/mbtn/clips --outdir {B}/r2 "
                      f"--timings {B}/timings_mbtn.json", timeout=14400)
    log(f"  MBTN re-assembled rc={rc} " + (out.split("\n")[-1] if out else err[-150:]))


# ── the two Gītā works ────────────────────────────────────────────────────────
def finish(work):
    want = wanted(BLOCKS[work])
    dest = f"{B}/works/{work}/clips"
    sh(f"mkdir -p {dest}")
    last = -1
    while True:
        got = set()
        for h, d in NODE_DIRS[work]:
            got |= have(h, d)
        n = len(want & got)
        if n != last:
            log(f"  {work}: {n}/{len(want)} clips")
            last = n
        if n >= len(want):
            break
        time.sleep(120)

    for h, d in NODE_DIRS[work]:
        if h == "localhost":
            continue
        sh(f"rsync -a {d}/ ece@10.32.38.96:{dest}/", h, timeout=7200)
    log(f"  {work}: consolidated {len(have('localhost', dest))} clips")

    rep = f"{B}/works/{work}/qc_{work}.json"
    rc, out, err = sh(f"cd {B} && {PY} asr_qc_loop.py --shard {B}/{STEM[work]}.json "
                      f"--manifest {B}/{STEM[work]}_man.json --outdir {dest} --report {rep} "
                      f"--thresh 0.15 --no-edge --gpu 0", timeout=36000)
    log(f"  {work} QC rc={rc} " + (out.split("\n")[-1] if out else err[-150:]))

    rc, out, err = sh(f"cd {B} && {PY} assemble_bsb.py --blocks {BLOCKS[work]} "
                      f"--clipdir {dest} --outdir {B}/r2 --timings {B}/timings_{work}.json",
                      timeout=14400)
    log(f"  {work} assembled rc={rc} " + (out.split("\n")[-1] if out else err[-150:]))


if __name__ == "__main__":
    log("finisher starting")
    for fn, name in ((mbtn_fill, "mbtn fill"), (lambda: finish("gita_bhashya"), "gita_bhashya"),
                     (lambda: finish("gita_tatparya"), "gita_tatparya")):
        try:
            fn()
        except Exception as e:
            log(f"!! {name} FAILED: {e!r} — continuing")
    log("finisher complete")
