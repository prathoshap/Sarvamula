#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render five short works in ONE pass: Yamaka Bhārata, Pariśiṣṭa, Yati Praṇava Kalpa,
Jayantī Kalpa, Nyāsa Paddhati. Runs ON box1.

346 clips between them — far too little to justify five render passes, since the model load
(~15 s per process) and the QC model load would cost more than the synthesis. So they go out
as one combined shard set over the six cards, are QC'd once, and are assembled per work from
each work's own blocks file. Clip ids carry the work prefix (ymb/prs/ypk/jyk/nyp), so a
single clip directory serves all five without ambiguity.

Waits for any ASR QC already running — Ṛg Bhāṣya's rescue rounds hold GPU 0, and starting a
six-card render on top of that would have both crawl.
"""
import json, os, subprocess, sys, time

B = "/home/ece/BigDisk/Prathosh/sarvamula_audio"
PY = "/home/ece/Prathosh/miniconda3/envs/indicf5/bin/python"
NODES = [("localhost", B + "/works/five/%d", 0, 0), ("localhost", B + "/works/five/%d", 1, 1),
         ("10.32.38.162", "/home/ece/n4_five_%d", 0, 2), ("10.32.38.162", "/home/ece/n4_five_%d", 1, 3),
         ("10.32.38.167", "/home/ece/n5_five_%d", 0, 4), ("10.32.38.167", "/home/ece/n5_five_%d", 1, 5)]

WORKS = [("yamaka_bharata", "blocks_ymb.json"), ("parishishta", "blocks_prs.json"),
         ("yati_pranava_kalpa", "blocks_ypk.json"), ("jayanti_kalpa", "blocks_jyk.json"),
         ("nyasa_paddhati", "blocks_nyp.json")]
DEST = B + "/works/five/clips"


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


def wait_for_qc():
    """Do not start six cards while an ASR rescue holds GPU 0."""
    for _ in range(180):
        rc, out, _ = sh("pgrep -cf 'asr_qc_loo[p].py'")
        if out.strip() in ("", "0"):
            return
        log("  waiting: an ASR QC is still running")
        time.sleep(60)


def launch():
    for host, tmpl, gpu, k in NODES:
        wd = tmpl % k
        sh(f"mkdir -p {wd}/clips {wd}/logs {wd}/shards", host)
        src = f"{B}/five_all.{k}.json"
        if host == "localhost":
            sh(f"cp {src} {wd}/shards/bsb_all.{k}.json; cp {B}/render_node.sh {wd}/render_node.sh")
        else:
            for f, d in ((src, f"{wd}/shards/bsb_all.{k}.json"),
                         (f"{B}/render_node.sh", f"{wd}/render_node.sh")):
                subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
                                "-q", f, f"ece@{host}:{d}"])
        sh(f"chmod +x {wd}/render_node.sh; rm -f {wd}/logs/render.{k}.done {wd}/logs/render.{k}.failed; "
           f"nohup {wd}/render_node.sh {k} {gpu} {wd} >/dev/null 2>&1 &", host)
    log(f"  {len(NODES)} shards launched")


def main():
    log("five short works — one combined pass")
    want = {c["id"] for c in json.load(open(f"{B}/five_all.json", encoding="utf-8"))}
    wait_for_qc()
    sh(f"mkdir -p {DEST}")
    launch()

    dirs = [(h, (t % k) + "/clips") for h, t, _, k in NODES]
    last, stuck = -1, 0
    while True:
        got = set()
        for h, d in dirs:
            got |= clips_at(h, d)
        n = len(want & got)
        if n != last:
            log(f"  {n}/{len(want)} clips ({100*n/len(want):.1f}%)")
            last, stuck = n, 0
        else:
            stuck += 1
        if n >= len(want) or stuck >= 20:
            break
        time.sleep(45)

    for h, d in dirs:
        if h == "localhost":
            sh(f"cp -n {d}/*.wav {DEST}/ 2>/dev/null")
        else:
            sh(f"rsync -a {d}/ ece@10.32.38.96:{DEST}/", h, timeout=3600)
    log(f"  consolidated {len(want & clips_at('localhost', DEST))}/{len(want)}")

    rc, out, err = sh(f"cd {B} && {PY} asr_qc_loop.py --shard {B}/five_all.json "
                      f"--manifest {B}/five_all_man.json --outdir {DEST} "
                      f"--report {B}/qc_five.json --thresh 0.15 --no-edge --gpu 0", timeout=18000)
    log(f"  QC rc={rc} " + (out.split("\n")[-1] if out else err[-160:]))

    for slug, blocks in WORKS:
        rc, out, err = sh(f"cd {B} && {PY} assemble_bsb.py --blocks {blocks} --clipdir {DEST} "
                          f"--outdir {B}/r2 --timings {B}/timings_{slug}.json", timeout=3600)
        log(f"  {slug} assembled rc={rc} " + (out.split("\n")[-1] if out else err[-140:]))
    log("five works complete")


if __name__ == "__main__":
    main()
