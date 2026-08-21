#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Corpus-wide assembly: turn rendered per-unit clips into the playable files the
reader streams, plus the karaoke timings the reader bakes into its DB.

Input   blocks_bsb.json      (segment_bsb.py) — blocks, units, parts, R2 paths
        <clipdir>/*.wav      (render_batch.py --outdir) — one wav per unit clip
Output  <outdir>/<path>.m4a  mirroring the R2 layout, ready to sync to the bucket
        timings_bsb.json     [{block, part, path, dur, segs:[{s,e,u,type}]}]
        (--sql) timings_bsb.sql to load into sarvamula.db

One file per SUTRA (median ~38s); only the few long blocks are split into parts —
see split_parts() in segment_bsb.py. AAC .m4a, not opus: opus in <audio> is
unreliable on iOS/Safari and the reader ships as an iOS app. This mirrors the
Bhāgavatam player, where audio URLs are DERIVED from structure (no manifest to keep
in sync) and karaoke timings live in the bundled DB (offline, no extra fetch).

Usage:
  assemble_bsb.py --clipdir out16 --outdir r2_stage --blocks blocks_bsb.json
  assemble_bsb.py --clipdir out16 --outdir r2_stage --only bsb_1_1_2 --keep_wav
"""
import argparse, json, os, subprocess, sys
import numpy as np, soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from assemble_block import assemble_from_units, SR

AUDIO = os.path.dirname(os.path.abspath(__file__))
# Hand-approved assemblies used verbatim instead of re-framing from the clip.
# BSB 1.1.1's sutra was built and signed off on 2026-07-31 (assemble.py first-sutra
# rule: EX +0.25+ EX +0.08+ body +0.25+ EX, over the out6/fix_omprimer render).
# Keyed on the CONTENT-ADDRESSED clip id on purpose: if the sutra text ever changes,
# the id changes and this approved audio stops being applied instead of being attached
# to text it does not say.
# The approved BODY of BSB 1.1.1's sūtra, without its framing — assemble_block adds the
# pranavas itself now, so the hand-approved recitation survives while the frame follows the
# corpus rule (2026-08-09: exemplar re-cut to 0.877 s).
PREBUILT = {
    "bsb_1_1_1_u01_sutra_050706": os.path.join(AUDIO, "assets", "sutra_1_1_1_body.wav"),
    # Bhāgavata Tātparya's maṅgala, second hemistich. The model gives every visarga its
    # learned echo, which put a 0.6 s gap inside the line at "समस्ताः सकलगुणनिधिः". Removing
    # the WORD BOUNDARY (समस्ताःसकल…, which is what sandhi does anyway) closes it, at seed
    # 62 — the letter alone does not, nor the seed alone. Approved by ear 2026-08-09.
    # The printed text with its space is untouched, so the reader still shows the edition;
    # only the audio comes from the joined rendering.
    "bt_1_1_1_u02_padya_p02_aafaaf": os.path.join(AUDIO, "assets", "bt_mangala_h2_approved.wav"),
}


def encode(wav_path, out_path, bitrate="128k"):
    """+faststart is REQUIRED, not cosmetic: without it the moov atom sits after mdat and
    a browser cannot seek into the file — <audio>.currentTime is silently ignored and
    playback restarts at 0, which breaks karaoke seek everywhere."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav_path,
                    "-c:a", "aac", "-b:a", bitrate,
                    "-movflags", "+faststart", out_path], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", default="blocks_bsb.json")
    ap.add_argument("--clipdir", required=True)
    ap.add_argument("--outdir", required=True, help="staging dir mirroring the R2 layout")
    ap.add_argument("--timings", default="timings_bsb.json")
    ap.add_argument("--sql", default="", help="also emit an SQL file for sarvamula.db")
    ap.add_argument("--only", default="", help="comma-separated block ids (default: all)")
    ap.add_argument("--bitrate", default="128k")
    ap.add_argument("--keep_wav", action="store_true")
    ap.add_argument("--unit_gap", type=float, default=0.75)
    ap.add_argument("--quote_lead", type=float, default=0.30)
    ap.add_argument("--pada_gap", type=float, default=0.55,
                    help="pause between padas inside a unit; 0 = the model's own padding only")
    a = ap.parse_args()

    blocks = json.load(open(a.blocks, encoding="utf-8"))
    if a.only:
        want = {x.strip() for x in a.only.split(",")}
        blocks = [b for b in blocks if b["id"] in want]

    rows, missing, done, total_sec = [], [], 0, 0.0
    for b in blocks:
        for p in b["parts"]:
            absent = [c for c in p["clips"]
                      if c not in PREBUILT
                      and not os.path.exists(os.path.join(a.clipdir, c + ".wav"))]
            if absent:
                missing.append((p["id"], len(absent), len(p["clips"])))
                continue
            # The bhāṣya-opening ॐ is NOT spliced back (user call, 2026-08-02): the
            # sutra file already closes on a pranava, so another one at the head of the
            # bhāṣya is redundant — and the exemplar is +7.6 dB louder in RMS than the
            # speech after it, so it masked the verse's opening word. The lone ॐ is
            # still kept out of the TTS text (the model collapses it), just dropped.
            audio, segs = assemble_from_units(p["units"], a.clipdir,
                                              a.unit_gap, a.quote_lead,
                                              pada_gap=a.pada_gap, prebuilt=PREBUILT)
            dur = len(audio)/SR
            out_m4a = os.path.join(a.outdir, p["path"])
            wav_tmp = os.path.splitext(out_m4a)[0] + ".wav"
            os.makedirs(os.path.dirname(out_m4a), exist_ok=True)
            sf.write(wav_tmp, audio, SR, subtype="PCM_16")
            encode(wav_tmp, out_m4a, a.bitrate)
            if not a.keep_wav:
                os.unlink(wav_tmp)
            rows.append({"block": b["id"], "ref": b["ref"], "part": p["part"],
                         "path": p["path"], "dur": round(dur, 3),
                         "from_unit": p["from"], "segs": segs})
            done += 1; total_sec += dur
            # est_sec is the planning model; dur is the truth. A large gap means the
            # model needs recalibrating before it is trusted for the next work.
            if p["est_sec"] and abs(dur - p["est_sec"])/max(dur, 1) > 0.25:
                print(f"  [est off] {p['id']}: est {p['est_sec']:.1f}s vs actual {dur:.1f}s")

    json.dump(rows, open(a.timings, "w"), ensure_ascii=False)

    if a.sql:
        with open(a.sql, "w") as f:
            f.write("CREATE TABLE IF NOT EXISTS audio_timings (\n"
                    "    work    TEXT,\n"
                    "    block   TEXT,   -- e.g. bsb_1_1_2\n"
                    "    part    INTEGER,\n"
                    "    path    TEXT,   -- R2 path, relative to AUDIO_BASE\n"
                    "    dur     REAL,\n"
                    "    segs    TEXT    -- [{\"s\":..,\"e\":..,\"u\":..,\"type\":..}] per UNIT\n"
                    ");\n")
            f.write("DELETE FROM audio_timings WHERE work='sutra_bhashya';\n")
            for r in rows:
                segs = json.dumps(r["segs"], ensure_ascii=False).replace("'", "''")
                f.write("INSERT INTO audio_timings VALUES('sutra_bhashya',"
                        f"'{r['block']}',{r['part']},'{r['path']}',{r['dur']},'{segs}');\n")

    print(f"\nassembled {done} file(s), {total_sec/3600:.2f} h -> {a.outdir}")
    print(f"timings -> {a.timings}" + (f"  sql -> {a.sql}" if a.sql else ""))
    if missing:
        print(f"\nSKIPPED {len(missing)} part(s) with un-rendered clips:")
        for pid, n, tot in missing[:10]:
            print(f"  {pid:22s} {n}/{tot} clips missing")
        if len(missing) > 10:
            print(f"  … and {len(missing)-10} more")


if __name__ == "__main__":
    main()
