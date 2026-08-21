#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Publish version.json — the content revisions the READER should use.

Why: the iOS/Android binaries ship DB_REV and AUDIO_REV as constants, so a re-baked database
or a re-uploaded m4a never reached an installed app; it kept requesting the revision it was
built with and its own cache answered. The apps now read these two values from version.json at
launch instead, which turns every text/audio correction into an upload rather than a store
review.

Run this LAST in a release, after the database and audio are on R2 — it is what makes clients
switch. Reads the revisions straight out of web/app.js so the manifest cannot disagree with the
code, and refuses to publish if either is missing.

  publish_revs.py                 # print what would be published
  publish_revs.py --upload        # write it to R2 (via box1's bucket-scoped rclone remote)
"""
import argparse, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPJS = os.path.join(ROOT, "web", "app.js")
BOX = "ece-box"
REMOTE = "r2:sarvamula/version.json"


def read_revs():
    src = open(APPJS, encoding="utf-8").read()
    db = re.search(r"const\s+DB_REV\s*=\s*'([^']+)'", src)
    au = re.search(r"const\s+AUDIO_REV\s*=\s*'([^']+)'", src)
    if not db or not au:
        sys.exit("could not read DB_REV / AUDIO_REV from web/app.js")
    return {"db": db.group(1), "audio": au.group(1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--upload", action="store_true")
    a = ap.parse_args()

    rev = read_revs()
    body = json.dumps(rev, ensure_ascii=False)
    print("version.json ->", body)
    if not a.upload:
        print("(dry run; pass --upload to publish)")
        return

    # no-store: this object is the ONE thing that must never be served stale, or clients keep
    # using an old database for up to a year under the bucket's immutable default.
    stage = "/tmp/version.json"
    subprocess.run(["ssh", "-o", "BatchMode=yes", BOX,
                    f"printf '%s' {json.dumps(body)} > {stage}"], check=True)
    subprocess.run(["ssh", "-o", "BatchMode=yes", BOX,
                    "~/bin/rclone copyto " + stage + " " + REMOTE +
                    ' --header-upload "Cache-Control: no-store, max-age=0"'
                    ' --header-upload "Content-Type: application/json"'], check=True)
    print("published to", REMOTE)


if __name__ == "__main__":
    main()
