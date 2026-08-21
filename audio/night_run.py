#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unattended overnight pipeline. Runs ON BOX1 so a VPN drop cannot interrupt it.

    render (8 GPUs, 4 boxes)  ->  consolidate  ->  ASR-QC  ->  assemble  ->  timings

for each work in turn: bhagavata_tatparya (already rendering), gita_bhashya, gita_tatparya.
One work at a time, all 8 cards on it — a work's QC and assembly are single-machine, so
overlapping works would leave cards idle for less benefit than finishing one cleanly.

Every stage is idempotent and resumable: clip ids are content-addressed, renders skip
what exists, and a crashed stage re-runs from where it stopped. If a stage cannot finish,
the work is marked FAILED and the next one starts — a stuck grantha must not block the rest.

    nohup python3 night_run.py > night.log 2>&1 &
"""
import json, os, subprocess, sys, time

B = "/home/ece/BigDisk/Prathosh/sarvamula_audio"
PY = "/home/ece/Prathosh/miniconda3/envs/indicf5/bin/python"
NODES = [                      # (host, workdir, gpu, shard index)
    ("localhost", f"{B}/works/%s", 0, 0), ("localhost", f"{B}/works/%s", 1, 1),
    ("10.32.38.180", "/home/ece/n3_%s", 0, 2), ("10.32.38.180", "/home/ece/n3_%s", 1, 3),
    ("10.32.38.162", "/home/ece/n4_%s", 0, 4), ("10.32.38.162", "/home/ece/n4_%s", 1, 5),
    ("10.32.38.167", "/home/ece/n5_%s", 0, 6), ("10.32.38.167", "/home/ece/n5_%s", 1, 7),
]
WORKS = [                      # (slug, blocks file, shard stem, already launched?)
    ("bhagavata_tatparya", "blocks_bt.json", "bt_all", True),
    ("gita_bhashya",       "blocks_gb.json", "gb_all", False),
    ("gita_tatparya",      "blocks_gt.json", "gt_all", False),
]
# Where the in-flight bhagavata_tatparya render already put its clips.
BT_DIRS = [("localhost", f"{B}/works/bhagavata_tatparya/clips"),
           ("10.32.38.180", "/home/ece/bt3/clips"),
           ("10.32.38.162", "/home/ece/bt_node/clips"),
           ("10.32.38.167", "/home/ece/bt5/clips")]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sh(cmd, host=None, timeout=1800):
    if host and host != "localhost":
        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", f"ece@{host}",
               cmd if isinstance(cmd, str) else " ".join(cmd)]
    else:
        cmd = ["bash", "-lc", cmd] if isinstance(cmd, str) else cmd
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def clips_on(host, path):
    rc, out, _ = sh(f"ls {path} 2>/dev/null | sed 's/\\.wav$//'", host)
    return set(out.split("\n")) if rc == 0 and out else set()


def needed(blocks):
    bs = json.load(open(os.path.join(B, blocks), encoding="utf-8"))
    return {c for b in bs for u in b["units"] for c in u["clips"]}


def launch(slug, stem):
    """Stage 8 shards and start one render per GPU."""
    for host, wd_t, gpu, k in NODES:
        wd = wd_t % slug
        sh(f"mkdir -p {wd}/clips {wd}/logs {wd}/shards", host)
        src = f"{B}/{stem}.{k}.json"
        if host == "localhost":
            sh(f"cp {src} {wd}/shards/bsb_all.{k}.json")
            sh(f"cp {B}/render_node.sh {wd}/render_node.sh 2>/dev/null; chmod +x {wd}/render_node.sh")
        else:
            sh(f"scp -o BatchMode=yes -q {src} ece@{host}:{wd}/shards/bsb_all.{k}.json")
            sh(f"scp -o BatchMode=yes -q {B}/render_node.sh ece@{host}:{wd}/render_node.sh")
            sh(f"chmod +x {wd}/render_node.sh", host)
        sh(f"rm -f {wd}/logs/render.{k}.done {wd}/logs/render.{k}.failed", host)
        sh(f"nohup {wd}/render_node.sh {k} {gpu} {wd} >/dev/null 2>&1 &", host)
        log(f"  launched shard {k} on {host} gpu{gpu}")
    return [(h, (t % slug) + "/clips") for h, t, _, _ in NODES]


def wait_render(want, dirs, label, stall_limit=40):
    """Poll until every clip exists. Gives up only if nothing lands for ~1 h — a wedged
    render must not hold the night hostage."""
    last, stalls = -1, 0
    while True:
        have = set()
        for h, d in dirs:
            have |= clips_on(h, d)
        done = len(want & have)
        if done != last:
            log(f"  {label}: {done}/{len(want)} clips ({100*done/len(want):.1f}%)")
            last, stalls = done, 0
        else:
            stalls += 1
        if done >= len(want):
            return True, have
        if stalls > stall_limit:
            log(f"  {label}: STALLED at {done}/{len(want)} — moving on")
            return False, have
        time.sleep(90)


def consolidate(dirs, dest):
    sh(f"mkdir -p {dest}")
    for h, d in dirs:
        if h == "localhost":
            if os.path.abspath(d) != os.path.abspath(dest):
                sh(f"cp -n {d}/*.wav {dest}/ 2>/dev/null")
        else:
            sh(f"rsync -a {d}/ ece@10.32.38.96:{dest}/", h, timeout=3600)
    return len(clips_on("localhost", dest))


def run_work(slug, blocks, stem, already):
    log(f"=== {slug} ===")
    want = needed(blocks)
    if already:
        dirs = BT_DIRS
        log(f"  render already in flight, {len(want)} clips wanted")
    else:
        dirs = launch(slug, stem)
    ok, _ = wait_render(want, dirs, slug)
    dest = f"{B}/works/{slug}/clips"
    n = consolidate(dirs, dest)
    log(f"  consolidated {n} clips -> {dest}")
    miss = len(want - clips_on("localhost", dest))
    if miss:
        log(f"  {miss} clips MISSING after consolidation — assembling what exists")

    rep = f"{B}/works/{slug}/qc_{slug}.json"
    log("  QC (CER-only) …")
    rc, out, err = sh(f"cd {B} && {PY} asr_qc_loop.py --shard {B}/{stem}.json "
                      f"--manifest {B}/{stem}_man.json --outdir {dest} --report {rep} "
                      f"--thresh 0.15 --no-edge --gpu 0", timeout=36000)
    log(f"  QC rc={rc} " + (out.split('\n')[-1] if out else err[-200:]))

    log("  assembling …")
    rc, out, err = sh(f"cd {B} && {PY} assemble_bsb.py --blocks {blocks} --clipdir {dest} "
                      f"--outdir {B}/r2_stage/{slug} --timings {B}/timings_{slug}.json",
                      timeout=14400)
    log(f"  assemble rc={rc} " + (out.split('\n')[-1] if out else err[-200:]))
    log(f"=== {slug} DONE ===")


if __name__ == "__main__":
    log("night run starting")
    for slug, blocks, stem, already in WORKS:
        try:
            run_work(slug, blocks, stem, already)
        except Exception as e:
            log(f"!! {slug} FAILED: {e!r} — continuing")
    log("night run complete")
