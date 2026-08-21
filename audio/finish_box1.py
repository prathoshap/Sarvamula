#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
box1 GPU0's queue. That card is the only one with the ASR model, so it runs QC while the
other seven render — which means its own render shards (0) are still outstanding and the
work QC belongs to still needs assembling. This drains that queue in order:

    wait for BTN QC  ->  assemble BTN  ->  GB shard 0  ->  GTN shard 0

Also copies the 1,912 GTN clips whose text+metre match a Gītā Bhāṣya clip once GB is
complete, so GTN never renders them (renders are bit-deterministic given text/metre/seed).
"""
import json, os, subprocess, time

B = "/home/ece/BigDisk/Prathosh/sarvamula_audio"
PY = "/home/ece/Prathosh/miniconda3/envs/indicf5/bin/python"


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def sh(cmd, timeout=None):
    r = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def running(pat):
    rc, out, _ = sh(f"ps -eo pid,cmd --no-headers | grep -E '{pat}' | grep -v grep | grep -v 'bash -lc'")
    return bool(out.strip())


def wait_gone(pat, label):
    while running(pat):
        time.sleep(60)
    log(f"{label} finished")


def render_shard(work, k, gpu):
    wd = f"{B}/works/{work}"
    sh(f"mkdir -p {wd}/clips {wd}/logs {wd}/shards")
    stem = {"gita_bhashya": "gb_all", "gita_tatparya": "gt_all"}[work]
    sh(f"cp {B}/{stem}.{k}.json {wd}/shards/bsb_all.{k}.json; "
       f"cp {B}/render_node.sh {wd}/render_node.sh; chmod +x {wd}/render_node.sh; "
       f"rm -f {wd}/logs/render.{k}.done {wd}/logs/render.{k}.failed")
    sh(f"nohup {wd}/render_node.sh {k} {gpu} {wd} >/dev/null 2>&1 &")
    log(f"  launched {work} shard {k} on gpu{gpu}")
    while not os.path.exists(f"{wd}/logs/render.{k}.done"):
        if os.path.exists(f"{wd}/logs/render.{k}.failed"):
            log(f"  {work} shard {k} FAILED"); return False
        time.sleep(60)
    log(f"  {work} shard {k} done")
    return True


def main():
    log("box1 queue starting")
    wait_gone("asr_qc_loop.py", "BTN QC")

    log("assembling bhagavata_tatparya …")
    rc, out, err = sh(f"cd {B} && {PY} assemble_bsb.py --blocks blocks_bt.json "
                      f"--clipdir {B}/works/bhagavata_tatparya/clips --outdir {B}/r2 "
                      f"--timings {B}/timings_bhagavata_tatparya.json", timeout=14400)
    log(f"  BTN assemble rc={rc} " + (out.split('\n')[-1] if out else err[-160:]))

    render_shard("gita_bhashya", 0, 0)

    # MBTN's fill: 294 hemistichs that the YouTube clip bank does not contain. Without them
    # 77 units would recite with a line silently missing, which is worse than an audible
    # gap because nothing signals it. ~55 GPU-min, taken here while the other cards are
    # still on GB/GTN.
    log("rendering the MBTN fill (294 clips) …")
    rc, out, err = sh(f"cd /home/ece/Prathosh/production && CUDA_VISIBLE_DEVICES=0 {PY} "
                      f"render_batch.py --shard {B}/mbtn_fill_out.json "
                      f"--results {B}/mbtn_fill_res.json --outdir {B}/works/mbtn/fill "
                      f"--gap 0.55", timeout=7200)
    ok = out.count("\nOK") + (1 if out.startswith("OK") else 0)
    log(f"  MBTN fill rc={rc}, {ok} clips rendered")

    # GB is complete once every shard has landed; then GTN's shared clips can be copied.
    log("waiting for the rest of GB …")
    while running("render_node.sh|render_batch.py"):
        time.sleep(60)
    share = json.load(open(f"{B}/gt_share_map.json", encoding="utf-8"))
    src, dst = f"{B}/works/gita_bhashya/clips", f"{B}/works/gita_tatparya/clips"
    os.makedirs(dst, exist_ok=True)
    n = 0
    for gt_id, gb_id in share.items():
        s, d = f"{src}/{gb_id}.wav", f"{dst}/{gt_id}.wav"
        if os.path.exists(s) and not os.path.exists(d):
            sh(f"cp {s} {d}"); n += 1
    log(f"copied {n}/{len(share)} shared clips into gita_tatparya")

    render_shard("gita_tatparya", 0, 0)
    log("box1 queue complete")


if __name__ == "__main__":
    main()
