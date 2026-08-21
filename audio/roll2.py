#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Per-card queue: as each Gītā Bhāṣya shard finishes, that card takes a slice of the
re-render delta first, then moves on to Gītā Tātparya.

The delta is the 449 clips whose text changed when parentheticals were stripped from
recitation and the maṅgala verse was promoted out of prose. Running it on one card took
~85 min and blocked the BT re-assembly behind it; split seven ways it is ~12 min, and it
runs on cards that would otherwise already have moved on to GTN.

Order per card:  GB shard done  ->  delta slice  ->  GTN shard
so no card is ever doing two things at once, and GTN starts only after the corrections
this work depends on are in hand.
"""
import json, os, subprocess, time

B = "/home/ece/BigDisk/Prathosh/sarvamula_audio"
PY = "/home/ece/Prathosh/miniconda3/envs/indicf5/bin/python"
NODES = [
    ("localhost",    f"{B}/works/gita_bhashya", f"{B}/works/gita_tatparya", 1, 1),
    ("10.32.38.180", "/home/ece/n3_gita_bhashya", "/home/ece/n3_gita_tatparya", 0, 2),
    ("10.32.38.180", "/home/ece/n3_gita_bhashya", "/home/ece/n3_gita_tatparya", 1, 3),
    ("10.32.38.162", "/home/ece/n4_gita_bhashya", "/home/ece/n4_gita_tatparya", 0, 4),
    ("10.32.38.162", "/home/ece/n4_gita_bhashya", "/home/ece/n4_gita_tatparya", 1, 5),
    ("10.32.38.167", "/home/ece/n5_gita_bhashya", "/home/ece/n5_gita_tatparya", 0, 6),
    ("10.32.38.167", "/home/ece/n5_gita_bhashya", "/home/ece/n5_gita_tatparya", 1, 7),
]


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def sh(cmd, host, wait=True):
    if host != "localhost":
        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
               "-o", "ConnectTimeout=10", f"ece@{host}", cmd]
    else:
        cmd = ["bash", "-lc", cmd]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def push(host, src, dst):
    if host == "localhost":
        sh(f"cp {src} {dst}", host)
    else:
        subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
                        "-q", src, f"ece@{host}:{dst}"])


def main():
    pending = list(NODES)
    while pending:
        still = []
        for host, gbw, gtw, gpu, k in pending:
            rc, _ = sh(f"test -f {gbw}/logs/render.{k}.done", host)
            if rc != 0:
                still.append((host, gbw, gtw, gpu, k)); continue
            log(f"GB shard {k} done on {host} gpu{gpu}")

            # 1. the card's slice of the delta, rendered where its clips must land
            slice_path = f"{B}/delta.{k}.json"
            if os.path.exists(slice_path):
                sh(f"mkdir -p {gtw}/../delta_{k}", host)
                push(host, slice_path, f"/tmp/delta.{k}.json")
                log(f"  delta slice {k} -> {host} gpu{gpu}")
                sh(f"cd /home/ece/Prathosh/production && CUDA_VISIBLE_DEVICES={gpu} {PY} "
                   f"render_batch.py --shard /tmp/delta.{k}.json "
                   f"--results /tmp/delta_res.{k}.json --outdir /tmp/delta_out.{k} "
                   f"--gap 0.55 > /tmp/delta.{k}.log 2>&1", host)
                rc, n = sh(f"grep -c '^OK' /tmp/delta.{k}.log || true", host)
                log(f"  delta slice {k}: {n} clips")
                # clips must end up on box1, where assembly reads them
                if host != "localhost":
                    sh(f"rsync -a /tmp/delta_out.{k}/ ece@10.32.38.96:{B}/works/_delta_in/", host)
                else:
                    sh(f"mkdir -p {B}/works/_delta_in && cp -n /tmp/delta_out.{k}/*.wav "
                       f"{B}/works/_delta_in/ 2>/dev/null", host)

            # 2. then GTN
            sh(f"mkdir -p {gtw}/clips {gtw}/logs {gtw}/shards", host)
            push(host, f"{B}/gt_all.{k}.json", f"{gtw}/shards/bsb_all.{k}.json")
            push(host, f"{B}/render_node.sh", f"{gtw}/render_node.sh")
            sh(f"chmod +x {gtw}/render_node.sh; rm -f {gtw}/logs/render.{k}.done "
               f"{gtw}/logs/render.{k}.failed; "
               f"nohup {gtw}/render_node.sh {k} {gpu} {gtw} >/dev/null 2>&1 &", host)
            log(f"  GTN shard {k} started on {host} gpu{gpu}")
        pending = still
        if pending:
            time.sleep(45)
    log("all cards rolled through delta -> GTN")


if __name__ == "__main__":
    main()
