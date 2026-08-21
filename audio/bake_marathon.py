#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bake the four outstanding Upaniṣad bhāṣyas into the reader as each one lands, unattended.

The marathon on box1 renders → QCs → assembles one work at a time; baking is a Mac-side
step (the db lives here), so the two have to meet. Rather than wake up to run four
commands by hand, this waits for each work's timings file to appear on the box, pulls it
and bakes it.

Two things it is careful about:

  * a timings file is only pulled once its SIZE HAS STOPPED CHANGING — assemble writes it
    in one go, but scp'ing a file mid-write yields truncated JSON that bakes a half work;
  * every ssh/scp is retried, because the link to the lab drops with the VPN and a
    dropped poll must not be mistaken for "not ready yet".

Idempotent: a work already in the db is skipped, so a re-run after a crash costs nothing.
"""
import json, os, re, sqlite3, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
BOX = "ece-box"
B = "/home/ece/BigDisk/Prathosh/sarvamula_audio"
DB = "/Users/prathosh/Sarvamula/web/sarvamula.db"
PY = os.path.join(HERE, ".venv/bin/python")

WORKS = [  # in the order the marathon renders them
    ("taittiriya_bhashya", "blocks_tai.json"),
    ("chandogya_bhashya",  "blocks_cha.json"),
    ("aitareya_bhashya",   "blocks_ait.json"),
    ("kanva_bhashya",      "blocks_kan.json"),
]
DEADLINE = 14 * 3600     # give up after 14 h; the last ETA is ~7 h out


def log(m):
    print(f"[{time.strftime('%m-%d %H:%M:%S')}] {m}", flush=True)


def ssh(cmd, tries=3):
    """Returns stdout, or None if the box could not be reached — never raises, because a
    VPN blip must read as 'unknown', not as 'absent'."""
    for _ in range(tries):
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                            BOX, cmd], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
        time.sleep(10)
    return None


def size_of(work):
    out = ssh(f"stat -c %s {B}/timings_{work}.json 2>/dev/null || echo -")
    if out is None:
        return "unreachable"
    return None if out.strip() in ("", "-") else int(out.strip())


def pull(work):
    dst = os.path.join(HERE, f"timings_{work}.json")
    for _ in range(4):
        r = subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "-q",
                            f"{BOX}:{B}/timings_{work}.json", dst], capture_output=True, text=True)
        if r.returncode == 0:
            try:
                json.load(open(dst, encoding="utf-8"))   # truncated transfer -> retry
                return dst
            except Exception:
                pass
        time.sleep(15)
    return None


def in_db(work):
    con = sqlite3.connect(DB)
    n = con.execute("SELECT count(*) FROM audio WHERE work=?", (work,)).fetchone()[0]
    con.close()
    return n


def bake(work, blocks, timings):
    r = subprocess.run([PY, "build_audio_db.py", "--work", work, "--blocks", blocks,
                        "--timings", timings, "--db", DB],
                       cwd=HERE, capture_output=True, text=True)
    tail = (r.stdout or r.stderr).strip().split("\n")[-1]
    log(f"  {work}: {tail}" + (f"  [rc={r.returncode}]" if r.returncode else ""))
    return r.returncode == 0


def bump_rev():
    """The reader caches the db under DB_REV. Baking behind an unchanged key would serve
    yesterday's db out of the browser cache; the last thing this does is invalidate it."""
    p = "/Users/prathosh/Sarvamula/web/app.js"
    s = open(p, encoding="utf-8").read()
    m = re.search(r"const DB_REV='([^']+)';", s)
    if not m:
        log("!! DB_REV not found in app.js — bump it by hand"); return
    old = m.group(1)
    new = old[:-1] + chr(ord(old[-1]) + 1) if old[-1].isalpha() else old + "a"
    open(p, "w", encoding="utf-8").write(s.replace(f"const DB_REV='{old}';",
                                                   f"const DB_REV='{new}';"))
    log(f"DB_REV {old} -> {new}")


def main():
    t0 = time.time()
    for work, blocks in WORKS:
        if in_db(work):
            log(f"{work}: already baked ({in_db(work)} rows) — skipping")
            continue
        log(f"=== waiting for {work} ===")
        stable, last = 0, None
        while True:
            if time.time() - t0 > DEADLINE:
                log(f"!! deadline reached with {work} unbaked — stopping"); return
            s = size_of(work)
            if s == "unreachable":
                log(f"  {work}: box unreachable (VPN?) — will keep trying")
                stable = 0
            elif s is None:
                stable = 0
            elif s == last and s > 0:
                stable += 1
                if stable >= 2:                       # ~2 min unchanged: the write is done
                    break
            else:
                stable = 0
            last = s if s != "unreachable" else last
            time.sleep(60)

        p = pull(work)
        if not p:
            log(f"!! {work}: could not pull timings — leaving for the morning"); continue
        n = len(json.load(open(p, encoding="utf-8")))
        log(f"  {work}: pulled {n} timing entries")
        if bake(work, blocks, p):
            log(f"=== {work} PLAYABLE ({in_db(work)} rows) ===")

    bump_rev()
    con = sqlite3.connect(DB)
    w, n, d = con.execute("SELECT count(DISTINCT work), count(*), sum(dur)/3600.0 FROM audio").fetchone()
    log(f"ALL DONE — reader now {w} works, {n:,} files, {d:.1f} h")


if __name__ == "__main__":
    main()
