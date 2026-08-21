#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render the newly-inserted Upaniṣad mūla for Chāndogya / Kāṇva / Aitareya. Runs ON box1.

The mūla was reverse-fetched from anandamakaranda.in by matching the bhāṣya and spliced
into `entries` (insert_upanishad_mula.py), so these three now segment with a mūla they
never had. Only the mūla is new work: 9,954 of the ~14,700 clips are byte-identical in
content to ones already on disk and are COPIED rather than synthesised — the ids changed
only because they carry their position in the work, not because the audio did.

Nodes: SIX cards (box1 ×2, .162 ×2, .167 ×2); box3 (.180) has been dead since 10 Aug.

.167 is used despite `nvidia-smi` failing with "Driver/library version mismatch". That is a
PATCH-LEVEL split between the kernel module (560.35.03) and the NVML userspace library
(560.35.05), and NVML is only the monitoring interface: torch reports cuda.is_available()
True and device_count 2 on that box, and render_node.sh selects its card with
CUDA_VISIBLE_DEVICES rather than by asking nvidia-smi. So the cards synthesise perfectly
well; only the reporting is broken. Nothing needs a reboot — the node just cannot be
monitored, so its progress is judged, like every other node's, by clips on disk.

Progress is judged by clips on disk, never by .done flags — a flag is written by the node
and vanishes if it is killed or restaged.
"""
import json, os, subprocess, sys, time

B = "/home/ece/BigDisk/Prathosh/sarvamula_audio"
PY = "/home/ece/Prathosh/miniconda3/envs/indicf5/bin/python"
NODES = [("localhost", B + "/works/%s", 0, 0), ("localhost", B + "/works/%s", 1, 1),
         ("10.32.38.162", "/home/ece/n4_%s", 0, 2), ("10.32.38.162", "/home/ece/n4_%s", 1, 3),
         ("10.32.38.167", "/home/ece/n5_%s", 0, 4), ("10.32.38.167", "/home/ece/n5_%s", 1, 5)]

QUEUE = [("rg_bhashya", "blocks_rgb.json", "rgb_all")]


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
    return {c for b in json.load(open(f"{B}/{blocks}", encoding="utf-8"))
            for u in b["units"] for c in u["clips"]}


def reuse_disabled(slug, want):
    """Copy clips whose audio we already have to the ids the new segmentation asks for."""
    m = json.load(open(f"{B}/mula_reuse_map.json", encoding="utf-8"))
    dest = f"{B}/works/{slug}/clips"
    sh(f"mkdir -p {dest}")
    have = clips_at("localhost", dest)
    todo = [(new, old) for new, old in m.items()
            if new in want and new not in have and old in have]
    script = "\n".join(f"cp -n {dest}/{o}.wav {dest}/{n}.wav" for n, o in todo)
    if script:
        open(f"/tmp/reuse_{slug}.sh", "w").write(script)
        sh(f"bash /tmp/reuse_{slug}.sh", timeout=3600)
    log(f"  {slug}: reused {len(todo)} clips by copy")


def launch(slug, stem):
    for host, tmpl, gpu, k in NODES:
        wd = tmpl % slug
        sh(f"mkdir -p {wd}/clips {wd}/logs {wd}/shards", host)
        src = f"{B}/{stem}.{k}.json"
        if host == "localhost":
            sh(f"cp {src} {wd}/shards/bsb_all.{k}.json; cp {B}/render_node.sh {wd}/render_node.sh")
        else:
            for f, d in ((src, f"{wd}/shards/bsb_all.{k}.json"),
                         (f"{B}/render_node.sh", f"{wd}/render_node.sh")):
                subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
                                "-q", f, f"ece@{host}:{d}"])
        sh(f"chmod +x {wd}/render_node.sh; rm -f {wd}/logs/render.{k}.done {wd}/logs/render.{k}.failed; "
           f"nohup {wd}/render_node.sh {k} {gpu} {wd} >/dev/null 2>&1 &", host)
    log(f"  {slug}: {len(NODES)} shards launched")


def run(slug, blocks, stem):
    log(f"=== {slug} ===")
    want = wanted(blocks)
    pass   # nothing to reuse: rg_bhashya has never been rendered
    launch(slug, stem)

    dirs = [(h, (t % slug) + "/clips") for h, t, _, _ in NODES]
    last, stuck, relaunched = -1, 0, False
    while True:
        got = set()
        for h, d in dirs:
            got |= clips_at(h, d)
        n = len(want & got)
        if n != last:
            log(f"  {slug}: {n}/{len(want)} clips ({100*n/len(want):.1f}%)")
            last, stuck = n, 0
        else:
            stuck += 1
        if n >= len(want):
            break
        if stuck >= 25:
            if relaunched:
                log(f"  {slug}: STALLED at {n}/{len(want)} — moving on"); break
            log(f"  {slug}: no progress ~25 min, relaunching"); launch(slug, stem)
            relaunched, stuck = True, 0
        time.sleep(60)

    dest = f"{B}/works/{slug}/clips"
    for h, d in dirs:
        if h != "localhost":
            sh(f"rsync -a {d}/ ece@10.32.38.96:{dest}/", h, timeout=7200)
    log(f"  {slug}: consolidated {len(want & clips_at('localhost', dest))}/{len(want)}")

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
    log(f"upaniṣad mūla restage starting — {len(NODES)} cards (box3 down; .167 used despite NVML)")
    for slug, blocks, stem in QUEUE:
        try:
            run(slug, blocks, stem)
        except Exception as e:
            log(f"!! {slug} FAILED: {e!r} — continuing")
    log("restage complete")
