#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bhāgavata Tātparya's mūla — reuse, do not render.

All 16,017 `Bhagavatam` verses in this work are verbatim in the Bhāgavata-VāNi corpus,
which already has one .m4a per verse AND per-verse karaoke timings. Verified exhaustively
(2026-08-08): 345/345 chapters, identical verse counts, 16,017/16,017 exact text matches by
chapter rank. So the mūla costs no GPU and no storage — only rows pointing at the other
project's bucket.

Two things this needs that the single-bucket build did not:

  * a PER-ROW audio base. The commentary lives in `sarvamoola`, the mūla in the Bhāgavatam
    bucket, and one AUDIO_BASE cannot serve both.
  * THEIR display lines, not ours. Their `timings.segs` index the lines of their own
    `text_dev` (split on \\n); our build joins the same text with spaces, so reusing their
    segs against our single-line text would light nothing. The text is identical either
    way — only the line breaks differ, and theirs are the ones the timings describe.

    bridge_bhagavatam.py            # then rebuild nothing else; commentary rows are untouched
"""
import argparse, json, re, sqlite3

SV = "/Users/prathosh/Sarvamula/web/sarvamula.db"
BH = "/Users/prathosh/Bhagavatam/web/bhagavatam.db"
WORK = "bhagavata_tatparya"
BASE = "https://pub-303f7559721c4b40bf6712eb557e350c.r2.dev/Bhagavata_Audio"

norm = lambda s: re.sub(r"[^ऀ-ॿ]", "", re.sub(r"[०-९।॥]", "", s or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sv", default=SV)
    ap.add_argument("--bh", default=BH)
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    sv = sqlite3.connect(a.sv)
    bh = sqlite3.connect(a.bh)
    cols = {r[1] for r in sv.execute("PRAGMA table_info(audio)")}
    if "base" not in cols:
        sv.execute("ALTER TABLE audio ADD COLUMN base TEXT")   # NULL = the app's own base

    # their side, indexed by (skandha, adhyaya) in chapter order
    theirs = {}
    for sk, ad, seq, aid, txt in bh.execute(
            "select skandha, adhyaya, seq_in_adhyaya, audio_id, text_dev from entries "
            "where content_type='Bhagavatam' order by skandha, adhyaya, seq_in_adhyaya"):
        theirs.setdefault((sk, ad), []).append((aid, txt))
    tim = {(r[0], r[1], r[2]): r[3] for r in bh.execute(
        "select skandha, adhyaya, audio_id, segs from timings")}

    # ours, in the same order
    ours = {}
    for sk, ad, seq, txt in sv.execute(
            "select skandha, adhyaya, seq, text_dev from entries "
            "where work=? and content_type='Bhagavatam' order by seq", (WORK,)):
        ours.setdefault((sk, ad), []).append((seq, txt))

    rows, trows, bad = [], [], 0
    for key, mine in sorted(ours.items()):
        their = theirs.get(key, [])
        for rank, (seq, mytxt) in enumerate(mine, 1):
            if rank > len(their):
                bad += 1
                continue
            aid, theirtxt = their[rank - 1]
            if norm(mytxt) != norm(theirtxt):       # never attach audio to unverified text
                bad += 1
                continue
            sk, ad = key
            path = f"skandha_{sk:02d}/adhyaya_{ad:03d}/BhP_{sk:02d}.{ad:03d}.{rank:03d}.m4a"
            segs = json.loads(tim.get((sk, ad, aid), "[]"))
            dur = max((s["e"] for s in segs), default=0.0)
            # their line breaks are what their segs index
            lines = [{"t": l.strip(), "k": "padya"} for l in (theirtxt or "").split("\n") if l.strip()]
            block = f"bt_mula_{sk}_{ad}_{rank}"
            rows.append((WORK, block, 0, path, dur, "mula", f"{sk}/{ad}/{rank}", seq,
                         json.dumps(lines, ensure_ascii=False), json.dumps([seq]), a.base))
            trows.append((WORK, block, 0, json.dumps(segs, ensure_ascii=False)))

    print(f"mūla rows: {len(rows)}  (skipped {bad} unmatched)")
    if a.dry:
        for r in rows[:3]:
            print("  ", r[1], r[3], f"{r[4]:.1f}s", json.loads(r[8])[0]["t"][:44])
        return

    sv.execute("DELETE FROM audio WHERE work=? AND kind='mula'", (WORK,))
    sv.execute("DELETE FROM audio_timings WHERE work=? AND block LIKE 'bt_mula_%'", (WORK,))
    sv.executemany("INSERT INTO audio VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    sv.executemany("INSERT INTO audio_timings VALUES (?,?,?,?)", trows)
    sv.commit()
    n, mins = sv.execute("SELECT count(*), round(sum(dur)/60,1) FROM audio WHERE work=? AND kind='mula'",
                         (WORK,)).fetchone()
    tot = sv.execute("SELECT count(*), round(sum(dur)/3600,2) FROM audio WHERE work=?", (WORK,)).fetchone()
    print(f"wrote {n} mūla rows ({mins} min, reused — 0 GPU)")
    print(f"  bhagavata_tatparya total: {tot[0]} files, {tot[1]} h")


if __name__ == "__main__":
    main()
