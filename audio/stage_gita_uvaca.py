#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Give the Gītā's 33 uvāca verses their pause. Runs ON box1, after Nyāya Vivaraṇa finishes.

The edition prints the speaker inline — "धृतराष्ट्र उवाच– धर्मक्षेत्रे…" — with no daṇḍa, so
the attribution landed inside the first pāda and was synthesised in one breath with the
opening line. No amount of assembly can fix that: the clip is a single sound. Splitting the
attribution into its own pāda (segment_bsb.mula_verse_units) gives assembly a boundary to
put a gap at, at the cost of re-rendering just the affected clips — 231 across both Gītā
works, everything else reused untouched.

Then three things must be rebuilt, because they all draw on these clips:
    gita_tatparya, gita_bhashya   per-verse tiles
    the PĀRĀYAṆA tracks           bhagavadgita's 18 continuous adhyāya tracks, which
                                  restitch the same mūla clips end to end
"""
import json, os, subprocess, sys, time

B = "/home/ece/BigDisk/Prathosh/sarvamula_audio"
PY = "/home/ece/Prathosh/miniconda3/envs/indicf5/bin/python"
NODES = [("localhost", B + "/works/gita2/%d", 0, 0), ("localhost", B + "/works/gita2/%d", 1, 1),
         ("10.32.38.162", "/home/ece/n4_gita2_%d", 0, 2), ("10.32.38.162", "/home/ece/n4_gita2_%d", 1, 3),
         ("10.32.38.167", "/home/ece/n5_gita2_%d", 0, 4), ("10.32.38.167", "/home/ece/n5_gita2_%d", 1, 5)]
DEST = B + "/works/gita2/clips"


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


def wait_idle():
    for _ in range(240):
        rc, out, _ = sh("pgrep -cf 'render_batc[h].py|asr_qc_loo[p].py'")
        if out.strip() in ("", "0"):
            return
        log("  waiting for the running render/QC to finish")
        time.sleep(60)


def launch():
    for host, tmpl, gpu, k in NODES:
        wd = tmpl % k
        sh(f"mkdir -p {wd}/clips {wd}/logs {wd}/shards", host)
        src = f"{B}/gita2_all.{k}.json"
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
    want = {c["id"] for c in json.load(open(f"{B}/gita2_all.json", encoding="utf-8"))}
    log(f"gītā uvāca fix — {len(want)} clips to render")
    wait_idle()
    sh(f"mkdir -p {DEST}")

    # a handful of clips only changed NAME (pāda index shifted); copy rather than re-render
    remap = json.load(open(f"{B}/gita_remap.json", encoding="utf-8"))
    for w, m in remap.items():
        d = f"{B}/works/{w}/clips"
        for new, old in m.items():
            sh(f"cp -n {d}/{old}.wav {d}/{new}.wav")
        if m:
            log(f"  {w}: {len(m)} clips renamed by copy")

    launch()
    last, stuck = -1, 0
    dirs = [(h, (t % k) + "/clips") for h, t, _, k in NODES]
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
        if n >= len(want) or stuck >= 15:
            break
        time.sleep(30)

    for h, d in dirs:
        if h == "localhost":
            sh(f"cp -n {d}/*.wav {DEST}/ 2>/dev/null")
        else:
            sh(f"rsync -a {d}/ ece@10.32.38.96:{DEST}/", h, timeout=1800)
    log(f"  consolidated {len(want & clips_at('localhost', DEST))}/{len(want)}")

    rc, out, err = sh(f"cd {B} && {PY} asr_qc_loop.py --shard {B}/gita2_all.json "
                      f"--manifest {B}/gita2_all_man.json --outdir {DEST} "
                      f"--report {B}/qc_gita2.json --thresh 0.15 --no-edge --gpu 0", timeout=10800)
    log(f"  QC rc={rc} " + (out.split("\n")[-1] if out else err[-160:]))

    # the new clips must sit in each work's own dir before assembly looks for them
    for w in ("gita_tatparya", "gita_bhashya"):
        sh(f"cp -n {DEST}/*.wav {B}/works/{w}/clips/ 2>/dev/null")

    for slug, blocks in (("gita_tatparya", "blocks_gt.json"), ("gita_bhashya", "blocks_gb.json")):
        rc, out, err = sh(f"cd {B} && {PY} assemble_bsb.py --blocks {blocks} "
                          f"--clipdir {B}/works/{slug}/clips --outdir {B}/r2 "
                          f"--timings {B}/timings_{slug}.json", timeout=14400)
        log(f"  {slug} assembled rc={rc} " + (out.split("\n")[-1] if out else err[-140:]))

    rc, out, err = sh(f"cd {B} && {PY} assemble_parayana.py --blocks-bsb blocks_bsb.json "
                      f"--blocks-gita blocks_gt.json --clips-bsb {B}/works/sutra_bhashya/clips "
                      f"--clips-gita {B}/works/gita_tatparya/clips --outdir {B}/r2 "
                      f"--timings {B}/timings_parayana.json", timeout=10800)
    log(f"  pārāyaṇa re-assembled rc={rc} " + (out.split("\n")[-1] if out else err[-160:]))
    log("gītā uvāca fix complete")


if __name__ == "__main__":
    main()
