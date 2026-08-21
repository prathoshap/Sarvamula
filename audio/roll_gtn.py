#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Roll each card from Gītā Bhāṣya onto Gītā Tātparya the moment its own shard finishes,
instead of waiting for the whole work. Runs on box1.

Cards do not finish together — in the BTN run the fastest shard was done 46 min before the
slowest — so a barrier at the work boundary wastes exactly that much on every card that
finished early. Each card is still strictly serial: GB then GTN, never both.

GTN's shards already exclude the 1,912 clips whose text+metre match a Gītā Bhāṣya clip;
those are copied on box1 once GB is complete (renders are bit-deterministic given
text/metre/seed, so the copy is exact).
"""
import json, subprocess, time

B = "/home/ece/BigDisk/Prathosh/sarvamula_audio"
NODES = [                       # (host, gb workdir, gtn workdir, gpu, shard)
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


def sh(cmd, host):
    if host != "localhost":
        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
               "-o", "ConnectTimeout=10", f"ece@{host}", cmd]
    else:
        cmd = ["bash", "-lc", cmd]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def main():
    pending = list(NODES)
    while pending:
        still = []
        for host, gbw, gtw, gpu, k in pending:
            rc, _ = sh(f"test -f {gbw}/logs/render.{k}.done", host)
            if rc != 0:
                still.append((host, gbw, gtw, gpu, k))
                continue
            log(f"GB shard {k} done on {host} gpu{gpu} -> starting GTN")
            sh(f"mkdir -p {gtw}/clips {gtw}/logs {gtw}/shards", host)
            if host == "localhost":
                sh(f"cp {B}/gt_all.{k}.json {gtw}/shards/bsb_all.{k}.json && "
                   f"cp {B}/render_node.sh {gtw}/render_node.sh && chmod +x {gtw}/render_node.sh", host)
            else:
                subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no", "-q",
                                f"{B}/gt_all.{k}.json", f"ece@{host}:{gtw}/shards/bsb_all.{k}.json"])
                subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no", "-q",
                                f"{B}/render_node.sh", f"ece@{host}:{gtw}/render_node.sh"])
                sh(f"chmod +x {gtw}/render_node.sh", host)
            sh(f"rm -f {gtw}/logs/render.{k}.done {gtw}/logs/render.{k}.failed; "
               f"nohup {gtw}/render_node.sh {k} {gpu} {gtw} >/dev/null 2>&1 &", host)
        pending = still
        if pending:
            time.sleep(60)
    log("every card has rolled onto GTN")


if __name__ == "__main__":
    main()
