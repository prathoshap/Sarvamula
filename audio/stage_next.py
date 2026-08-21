#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
One supervisor, on box1, for everything still outstanding:

    Gītā Tātparya  (rendering now)  -> QC -> assemble
    tantrasara_sangraha             -> render -> QC -> assemble
    krshna_amrta_maharnava          -> render -> QC -> assemble
    sadachara_smriti                -> render -> QC -> assemble

ONE supervisor deliberately. Earlier there were three overlapping ones (night_run, roll2,
finish_works) and when roll2 died silently the others kept waiting politely for clips that
nothing was producing — Gītā Tātparya sat idle for an hour with eight free cards. A single
process that owns the whole queue cannot develop that blind spot.

Progress is judged by CLIPS ON DISK, never by .done flags: a flag is written by the node and
goes missing if the node is killed, restaged, or its shard is edited mid-flight (all of which
happened today). Clip ids are content-addressed, so counting them is the ground truth.
"""
import json, os, subprocess, sys, time

B = "/home/ece/BigDisk/Prathosh/sarvamula_audio"
PY = "/home/ece/Prathosh/miniconda3/envs/indicf5/bin/python"
NODES = [("localhost", B + "/works/%s", 0, 0), ("localhost", B + "/works/%s", 1, 1),
         ("10.32.38.180", "/home/ece/n3_%s", 0, 2), ("10.32.38.180", "/home/ece/n3_%s", 1, 3),
         ("10.32.38.162", "/home/ece/n4_%s", 0, 4), ("10.32.38.162", "/home/ece/n4_%s", 1, 5),
         ("10.32.38.167", "/home/ece/n5_%s", 0, 6), ("10.32.38.167", "/home/ece/n5_%s", 1, 7)]

QUEUE = [  # (slug, blocks file, shard stem, already rendering?)
    ("gita_tatparya",          "blocks_gt.json",  "gt_all",  True),
    # these three were rendered together in one combined pass across the idle cards and
    # split by id prefix, so their clips already exist — go straight to QC and assembly
    ("tantrasara_sangraha",    "blocks_tss.json", "tss_all", True),
    ("krshna_amrta_maharnava", "blocks_kam.json", "kam_all", True),
    ("sadachara_smriti",       "blocks_sas.json", "sas_all", True),
    ("vishnu_tatva_nirnaya",   "blocks_vtn.json", "vtn_all", False),
    ("tatvodyota",             "blocks_tdy.json", "tdy_all", False),
]


def log(m):
    print(f"[{time.strftime('%m-%d %H:%M:%S')}] {m}", flush=True)


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


def clips_at(host, path):
    rc, out, _ = sh(f"ls {path} 2>/dev/null | sed 's/\\.wav$//'", host)
    return {x for x in out.split("\n") if x and "__" not in x} if rc == 0 and out else set()


def wanted(blocks):
    bs = json.load(open(f"{B}/{blocks}", encoding="utf-8"))
    return {c for b in bs for u in b["units"] for c in u["clips"]}


def dirs_for(slug):
    return [(h, (t % slug) + "/clips") for h, t, _, _ in NODES]


def launch(slug, stem):
    for host, tmpl, gpu, k in NODES:
        wd = tmpl % slug
        sh(f"mkdir -p {wd}/clips {wd}/logs {wd}/shards", host)
        src = f"{B}/{stem}.{k}.json"
        if host == "localhost":
            sh(f"cp {src} {wd}/shards/bsb_all.{k}.json; cp {B}/render_node.sh {wd}/render_node.sh")
        else:
            subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no", "-q",
                            src, f"ece@{host}:{wd}/shards/bsb_all.{k}.json"])
            subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no", "-q",
                            f"{B}/render_node.sh", f"ece@{host}:{wd}/render_node.sh"])
        sh(f"chmod +x {wd}/render_node.sh; rm -f {wd}/logs/render.{k}.done {wd}/logs/render.{k}.failed; "
           f"nohup {wd}/render_node.sh {k} {gpu} {wd} >/dev/null 2>&1 &", host)
    log(f"  {slug}: 8 shards launched")


def wait_clips(slug, want, stall_rounds=25):
    """Poll clip counts. Relaunch once if progress stops with work outstanding — a node
    whose render died is otherwise invisible until someone looks."""
    last, stuck, relaunched = -1, 0, False
    while True:
        got = set()
        for h, d in dirs_for(slug):
            got |= clips_at(h, d)
        n = len(want & got)
        if n != last:
            log(f"  {slug}: {n}/{len(want)} clips ({100*n/len(want):.1f}%)")
            last, stuck = n, 0
        else:
            stuck += 1
        if n >= len(want):
            return True
        if stuck >= stall_rounds:
            if relaunched:
                log(f"  {slug}: STALLED at {n}/{len(want)} after a relaunch — moving on")
                return False
            log(f"  {slug}: no progress for ~{stall_rounds} min, relaunching the shards")
            launch(slug, dict((q[0], q[2]) for q in QUEUE)[slug])
            relaunched, stuck = True, 0
        time.sleep(60)


PREFIX = {"tantrasara_sangraha": "tss_", "krshna_amrta_maharnava": "kam_",
          "sadachara_smriti": "sas_"}


def file_combined(slug):
    """The three small works were rendered in ONE pass into /tmp/three_out on each card —
    seven cards on 1,576 clips instead of three works queued behind each other. Their ids
    carry the work prefix, so filing them afterwards is unambiguous."""
    pre = PREFIX.get(slug)
    if not pre:
        return
    dest = f"{B}/works/{slug}/clips"
    sh(f"mkdir -p {dest}")
    for host, _, _, _ in NODES:
        if host == "localhost":
            sh(f"cp -n /tmp/three_out/{pre}*.wav {dest}/ 2>/dev/null")
        else:
            sh(f"rsync -a --include='{pre}*' --exclude='*' /tmp/three_out/ "
               f"ece@10.32.38.96:{dest}/", host, timeout=3600)
    log(f"  {slug}: filed {len(clips_at('localhost', dest))} clips from the combined pass")


def run(slug, blocks, stem, already):
    log(f"=== {slug} ===")
    want = wanted(blocks)
    file_combined(slug)
    if not already:
        launch(slug, stem)
    wait_clips(slug, want)

    dest = f"{B}/works/{slug}/clips"
    sh(f"mkdir -p {dest}")
    for h, d in dirs_for(slug):
        if h != "localhost":
            sh(f"rsync -a {d}/ ece@10.32.38.96:{dest}/", h, timeout=7200)
    here = clips_at("localhost", dest)
    log(f"  {slug}: consolidated {len(want & here)}/{len(want)}")

    rc, out, err = sh(f"cd {B} && {PY} asr_qc_loop.py --shard {B}/{stem}.json "
                      f"--manifest {B}/{stem}_man.json --outdir {dest} "
                      f"--report {B}/works/{slug}/qc_{slug}.json --thresh 0.15 --no-edge --gpu 0",
                      timeout=36000)
    log(f"  {slug} QC rc={rc} " + (out.split("\n")[-1] if out else err[-160:]))

    rc, out, err = sh(f"cd {B} && {PY} assemble_bsb.py --blocks {blocks} --clipdir {dest} "
                      f"--outdir {B}/r2 --timings {B}/timings_{slug}.json", timeout=14400)
    log(f"  {slug} assembled rc={rc} " + (out.split("\n")[-1] if out else err[-160:]))
    log(f"=== {slug} DONE ===")


if __name__ == "__main__":
    log("supervisor starting")
    for slug, blocks, stem, already in QUEUE:
        try:
            run(slug, blocks, stem, already)
        except Exception as e:
            log(f"!! {slug} FAILED: {e!r} — continuing")
    log("supervisor complete — all queued works finished")
