#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MBTN — segment against clips that ALREADY EXIST.

Every other work is segmented and then rendered. MBTN was rendered a year earlier for the
YouTube series (32 adhyāyas, 10,220 clips at
`ece-box:/home/ece/BigDisk/mbtn_prod/work/adhNN/wav`), and the user's call (2026-08-08) is
to reuse it as is. So this segmenter does not mint clip ids — it MATCHES our text to the
clips that exist and adopts their ids.

Consequences of reuse, all deliberate:
  * granularity is the HEMISTICH, not the pāda: karaoke lights two metrical lines at once,
    unlike BSB/Anuvyākhyāna. Re-rendering per pāda would cost ~36 GPU-h.
  * matching is on normalised text (Devanagari letters only), because the two pipelines
    punctuate and number differently.
  * anything unmatched is reported, never silently dropped — the colophons have no clips.

    segment_mbtn.py --clips mbtn_all_clips.json --out blocks_mbtn.json
"""
import argparse, json, os, re, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import segment_bsb as SB

DB = "/Users/prathosh/Sarvamula/web/sarvamula.db"
WORK = "mbtn"
# mbtn numbers its verses adhyāya/verse — '॥ १९/९६॥' — which the plain ॥ N ॥ pattern misses.
VNUM = re.compile(r"॥\s*([०-९\d]+)\s*/\s*([०-९\d]+)\s*॥")
AK = re.compile(r"[अ-हऽ]")
MAX_SEC = 900.0          # split a block into parts beyond ~15 min


def norm(s):
    return re.sub(r"[^ऀ-ॿ]", "", re.sub(r"[०-९।॥]", "", s or ""))


def clean(t):
    t = re.sub(r"[०-९]+", "", t or "")
    return re.sub(r"\s+", " ", t).strip(" ।॥,;-“”‘’\"'()")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--clips", default="/private/tmp/mbtn_all_clips.json")
    ap.add_argument("--out", default="blocks_mbtn.json")
    a = ap.parse_args()

    clips = json.load(open(a.clips, encoding="utf-8"))
    # index by normalised text; a duplicated line keeps its first clip (they are identical
    # renders of identical text, so either is correct)
    idx = {}
    for c in clips:
        idx.setdefault(norm(c["text"]), c)
    print(f"clip bank: {len(clips)} clips, {len(idx)} distinct texts")

    con = sqlite3.connect(a.db); con.row_factory = sqlite3.Row
    rows = list(con.execute(
        "select seq, content_type, heading_level, text_dev from entries "
        "where work=? order by seq", (WORK,)))
    con.close()

    blocks, h, matched, missed, miss_ak = [], {1: None, 2: None, 3: None}, 0, 0, 0
    for r in rows:
        ct, txt = r["content_type"] or "", r["text_dev"] or ""
        if ct.startswith("Heading"):
            lvl = r["heading_level"] or int(ct[-1] or 1)
            h[lvl] = txt
            for d in range(lvl + 1, 4):
                h[d] = None
            continue
        if ct not in ("Sarvamula", "Colophon_Sarvamula"):
            continue

        units, pos = [], 0
        pieces = []
        for m in VNUM.finditer(txt):
            pieces.append((txt[pos:m.start()],
                           f"{m.group(1).translate(SB._DEVA_DIGITS)}/"
                           f"{m.group(2).translate(SB._DEVA_DIGITS)}"))
            pos = m.end()
        if txt[pos:].strip():
            pieces.append((txt[pos:], None))

        for body, vref in pieces:
            # hemistichs, as the clip bank cut them: split on the daṇḍa
            hemis = [clean(x) for x in re.split(r"[।॥]", body)]
            hemis = [x for x in hemis if x and AK.search(x)]
            if not hemis:
                continue
            ids, texts, meters, ok = [], [], [], True
            for x in hemis:
                c = idx.get(norm(x))
                if c is None:
                    ok = False
                    missed += 1
                    miss_ak += len(AK.findall(x))
                    continue
                ids.append(c["id"]); texts.append(x)
                meters.append(SB.METER_ALIAS.get(c.get("meter"), c.get("meter")) or "anuṣṭubh")
                matched += 1
            if not ids:
                continue
            units.append({"n": len(units) + 1, "type": "padya", "verse": vref,
                          "padas": texts, "clips": ids, "meter": meters[0],
                          "meter_src": "reused:mbtn_prod",
                          "bounds": ["hard"] * len(texts),
                          "text": " ".join(texts), "complete": ok})
        if not units:
            continue
        bid = f"mbtn_{r['seq']:04d}"
        est = SB.block_seconds(units)
        n_parts = max(1, int(est // MAX_SEC) + (1 if est % MAX_SEC else 0))
        per = (len(units) + n_parts - 1) // n_parts
        parts = []
        for k in range(n_parts):
            us = units[k * per:(k + 1) * per]
            if not us:
                continue
            parts.append({"part": k + 1, "kind": "nirnaya",
                          "id": bid if n_parts == 1 else f"{bid}_p{k+1}",
                          "from": us[0]["n"], "to": us[-1]["n"],
                          "seq": r["seq"], "covers": [r["seq"]],
                          "units": [{"n": u["n"], "type": u["type"], "clips": u["clips"],
                                     "bounds": u["bounds"]} for u in us],
                          "clips": [c for u in us for c in u["clips"]],
                          "est_sec": round(SB.block_seconds(us), 1),
                          "path": f"mbtn/{bid}" + (f"_p{k+1}" if n_parts > 1 else "") + ".m4a"})
        blocks.append({"id": bid, "ref": None, "seq": r["seq"], "kind": "vyakhyana",
                       "adhyaya": h[1], "pada": h[2], "adhikarana": h[3],
                       "est_sec": round(est, 1), "parts": parts, "units": units})

    json.dump(blocks, open(a.out, "w"), ensure_ascii=False, indent=1)
    nu = sum(len(b["units"]) for b in blocks)
    print(f"blocks   : {len(blocks)}")
    print(f"units    : {nu}")
    print(f"clips    : {matched} matched, {missed} unmatched ({miss_ak} akṣaras — these need rendering)")
    print(f"files    : {sum(len(b['parts']) for b in blocks)}")
    print(f"est audio: {sum(b['est_sec'] for b in blocks)/3600:.2f} h")
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
