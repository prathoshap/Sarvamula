#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bake the audio + karaoke tables into sarvamula.db — the Bhāgavatam arrangement.

Bhāgavatam does not map audio to character offsets. It bakes DISPLAY LINES at build time
(`text_dev` = lines joined by \\n; the reader splits on \\n into
`<span class="ln" data-i="N">`) and its `timings.segs` reference those line indices
(`[{"s":.., "e":.., "ln":[0,1]}]`). Karaoke then just toggles a class on matching spans.

Same shape here, with ONE LINE PER UNIT: a unit is a prose clause or one quoted mantra,
which is the granularity a reader follows in a bhāṣya, and assemble_from_units already
emits one seg per unit — so seg.u IS the line index within its part.

Tables (work-scoped, so the other 37 works can follow):
    audio(work, block, part, path, dur, lines)      lines = "\\n"-joined display lines
    audio_timings(work, block, part, segs)          [{s,e,ln:[i]}]
Both keyed by (work, block, part); `path` is relative to the audio base.
"""
import argparse, json, os, re, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from assemble_block import FIRST_SUTRA_BLOCKS

DB = "/Users/prathosh/Sarvamula/web/sarvamula.db"

# Refs are normalised to ASCII digits so they can key filenames (BhTN_1.1.1.m4a), but the
# reader shows the edition, which numbers its verses in Devanagari.
_ASCII2DEVA = str.maketrans("0123456789", "०१२३४५६७८९")


def deva_num(x):
    return str(x).translate(_ASCII2DEVA)
WORK = "sutra_bhashya"

DDL = """
CREATE TABLE IF NOT EXISTS audio (
    work TEXT, block TEXT, part INTEGER,
    path TEXT,          -- relative to the audio base (R2 or local web/audio)
    dur  REAL,
    kind TEXT,          -- sutra | bhashya
    ref  TEXT,          -- 1/1/2
    seq  INTEGER,       -- entries.seq this part is ANCHORED at (where the player shows)
    lines TEXT,         -- display lines as JSON [{t,k}]; index = karaoke ln
    covers TEXT         -- JSON [seq…]: every entry this part recites, so the reader can
                        -- print that text once (here) instead of twice
);
CREATE TABLE IF NOT EXISTS audio_timings (
    work TEXT, block TEXT, part INTEGER,
    segs TEXT           -- [{"s":..,"e":..,"ln":[i]}]
);
CREATE INDEX IF NOT EXISTS idx_audio_seq ON audio(work, seq);
"""


_DROP = set('।॥*0123456789०१२३४५६७८९')
_LET = lambda ch: 'ऀ' <= ch <= 'ॿ' and ch not in _DROP


def _bare(s):
    return ''.join(ch for ch in (s or '') if _LET(ch))


_EL = None          # {"work|seq": [interior cut offsets]} from build_entry_lines.py
_ENT = {}           # (work, seq) -> bare(text_dev), cached per process


def load_entry_lines(path):
    global _EL
    _EL = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    return len(_EL)


def regroup_to_edition(disp_lines, idx, work, covers, con, stats):
    """Merge consecutive per-pada display lines that the EDITION prints as one line.

    Returns (disp_lines, idx). Falls through unchanged — and counts why — whenever the
    recitable text cannot be aligned to the covered entries, which is the honest answer for
    the ~1.4k entries reciting mūla from another book (upaniṣad prose, Ṛgveda mantras) that
    is absent from this work's source JSON. Guessing a line structure there would invent
    breaks exactly like the ones this function exists to remove.
    """
    LIST = lambda d: {k: (v if isinstance(v, list) else [v]) for k, v in d.items()}
    if not _EL:
        return disp_lines, LIST(idx)
    # legal break offsets across the covered entries, in seq order
    legal, total = set(), 0
    for s in sorted(covers):
        key = f"{work}|{s}"
        if key not in _EL:
            stats["no-structure"] += 1
            return disp_lines, LIST(idx)
        if (work, s) not in _ENT:
            row = con.execute("SELECT text_dev FROM entries WHERE work=? AND seq=?",
                              (work, s)).fetchone()
            _ENT[(work, s)] = _bare(row[0]) if row else ""
        for cut in _EL[key]:
            legal.add(total + cut)
        total += len(_ENT[(work, s)])
        legal.add(total)

    rec = [i for i, l in enumerate(disp_lines) if l["k"] != "gap"]
    if sum(len(_bare(disp_lines[i].get("_p", ""))) for i in rec) != total:
        stats["unaligned"] += 1        # display text != covered entries; leave it alone
        return disp_lines, LIST(idx)

    # group the recitable lines: a group ends where the edition ends a line
    groups, cur, off = [], [], 0
    for i in rec:
        cur.append(i)
        off += len(_bare(disp_lines[i].get("_p", "")))
        if off in legal:
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)

    # A pāda may also SPAN an edition line, which merging alone cannot fix. fit_padas absorbs
    # a runt into its neighbour across a soft boundary, so the speaker tag 'श्रीभगवानुवाच-' (6
    # akṣaras, ending in a hyphen, not a daṇḍa) was swallowed by the verse that follows it and
    # printed on the same line — while 'अर्जुन उवाच ।' survived because a daṇḍa is HARD. The
    # edition puts the tag on its own line, so split there too. This is display-only: the clip
    # is untouched and its seg simply lights both lines.
    def split_line(l):
        """Cut one display line at the edition boundaries interior to it."""
        body = l.get("_p", "")
        letters = [(ch, n) for n, ch in enumerate(body) if _LET(ch)]
        cuts = [k for k in range(1, len(letters)) if (off_of[id(l)] + k) in legal]
        if not cuts:
            return [l]
        pieces, prev = [], 0
        for k in cuts + [len(letters)]:
            end = letters[k][1] if k < len(letters) else len(body)
            seg = body[prev:end].strip()
            if seg:
                pieces.append(seg)
            prev = end
        if len(pieces) < 2:
            return [l]
        out = []
        for n, seg in enumerate(pieces):
            last = n == len(pieces) - 1
            # an interior piece takes the daṇḍa the edition prints at that line end — unless it
            # is a lead-in ending in a hyphen ('श्रीभगवानुवाच-'), which the edition leaves bare
            mark = l.get("_m", "") if last else ("" if seg[-1] in "-–—" else "।")
            out.append({"t": (seg + " " + mark).strip(), "k": l["k"], "_p": seg, "_m": mark})
        return out

    off_of, run = {}, 0
    for i in rec:
        off_of[id(disp_lines[i])] = run
        run += len(_bare(disp_lines[i].get("_p", "")))

    if all(len(g) == 1 for g in groups) and \
       not any(len(split_line(disp_lines[i])) > 1 for i in rec):
        return disp_lines, LIST(idx)  # already 1:1 with the edition

    # rebuild, keeping gap lines where they sit relative to the recitable ones
    maps = {}                          # old line index -> [new line indices]
    out, gi = [], 0
    for i, l in enumerate(disp_lines):
        if l["k"] == "gap":
            out.append(l)
            continue
        if gi < len(groups) and i == groups[gi][0]:
            g = groups[gi]
            if len(g) > 1:
                body = " ".join(disp_lines[j].get("_p", "") for j in g).strip()
                tail = disp_lines[g[-1]].get("_m", "")
                out.append({"t": (body + " " + tail).strip(),
                            "k": disp_lines[g[-1]]["k"], "_p": body, "_m": tail})
                for j in g:
                    maps[j] = [len(out) - 1]
                stats["merged-lines"] += len(g) - 1
            else:
                pieces = split_line(disp_lines[g[0]])
                start = len(out)
                out.extend(pieces)
                maps[g[0]] = list(range(start, len(out)))
                if len(pieces) > 1:
                    stats["split-lines"] += len(pieces) - 1
            gi += 1
    stats["rows-regrouped"] += 1
    return out, {k: maps.get(v, [v]) for k, v in idx.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", default="blocks_bsb.json")
    ap.add_argument("--timings", required=True, help="t_A.json / t_B.json from assemble_bsb")
    ap.add_argument("--db", default=DB)
    ap.add_argument("--only", default="")
    ap.add_argument("--existing_only", action="store_true",
                    help="refresh only rows already in the DB; never add a tile (see below)")
    ap.add_argument("--entry_lines",
                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "entry_lines.json"),
                    help="edition line structure from build_entry_lines.py; '' disables regrouping")
    ap.add_argument("--work", default=WORK,
                    help="entries.work this audio belongs to (sutra_bhashya, anu_vyakhyana, …)")
    a = ap.parse_args()
    globals()["WORK"] = a.work
    import collections
    stats = collections.Counter()
    n_el = load_entry_lines(a.entry_lines) if a.entry_lines else 0

    blocks = {b["id"]: b for b in json.load(open(a.blocks, encoding="utf-8"))}
    tim = json.load(open(a.timings, encoding="utf-8"))
    if a.only:
        want = {x.strip() for x in a.only.split(",")}
        tim = [t for t in tim if t["block"] in want]

    con = sqlite3.connect(a.db)
    if a.existing_only:
        # Rebuild ONLY the (block, part) rows the database already has. A work can be voiced
        # by more than one pipeline: Dvādaśa Stotra and the Ṛgveda mantras are the user's own
        # recitation, and their TTS blocks were deleted on purpose. Re-inserting from the TTS
        # timings would resurrect them and show every verse twice — the "display shows both TTS
        # and chanted ones" fault. So a display-only pass must never ADD a tile, only refresh one.
        have = {(r[0], r[1]) for r in
                con.execute("SELECT block, part FROM audio WHERE work=?", (a.work,))}
        before = len(tim)
        tim = [t for t in tim if (t["block"], t["part"]) in have]
        stats["not-in-db"] += before - len(tim)
    con.executescript(DDL)
    cols = {r[1] for r in con.execute("PRAGMA table_info(audio)")}
    if "covers" not in cols:                       # table predates per-part coverage
        con.execute("ALTER TABLE audio ADD COLUMN covers TEXT")
    blocks_done = sorted({t["block"] for t in tim})
    con.execute("DELETE FROM audio WHERE work=? AND block IN (%s)" %
                ",".join("?" * len(blocks_done)), [WORK] + blocks_done)
    con.execute("DELETE FROM audio_timings WHERE work=? AND block IN (%s)" %
                ",".join("?" * len(blocks_done)), [WORK] + blocks_done)

    n = 0
    for t in tim:
        # A timings file outlives the segmentation that produced it: assemble_bsb.py --only
        # rewrites it with just the blocks it touched, and re-segmentation renumbers or drops
        # parts (ait_seq73 went from 6 parts to 4 when its fragmented verses merged). Rows for
        # a block/part that no longer exists are STALE — skipping them is what keeps them from
        # being re-inserted as tiles reciting text that belongs to another entry.
        if t["block"] not in blocks:
            stats["stale-block"] += 1
            continue
        b = blocks[t["block"]]
        cand = [p for p in b["parts"] if p["part"] == t["part"]]
        if not cand:
            stats["stale-part"] += 1
            continue
        part = cand[0]
        units = {u["n"]: u for u in b["units"]}
        # the part's units in order; seg.u indexes into exactly this list
        ordered = [units[x["n"]] for x in part["units"]]
        # ONE DISPLAY LINE PER PADA, with the daṇḍa restored. The cleaner strips daṇḍas
        # before TTS, but the reader must show them — and a verse needs its pāda breaks
        # visible, not a 24-pada wall of text. `k` lets the reader style verse and prose
        # differently, which is the point of separating them here rather than in CSS alone.
        disp_lines, idx = [], {}
        for ui, u in enumerate(ordered):
            # The sūtra is framed by a spliced ॐ before and after — audible since the first
            # assembly, but never shown. It belongs ON the sūtra's own line, not above and
            # below it: the aphorism reads as "ॐ ... ॐ", one utterance. The pranava segs
            # therefore point AT the sūtra line, so it stays lit while the ॐ sounds.
            # The opening sūtra of the work carries TWO leading pranavas (the maṅgala ॐ,
            # then the one integral to the aphorism).
            n_lead = 2 if (u["type"] == "sutra" and t["block"] in FIRST_SUTRA_BLOCKS) else \
                     (1 if u["type"] == "sutra" else 0)
            bounds = u.get("bounds") or ["hard"]*len(u["padas"])
            gapafter = u.get("gapafter") or [False]*len(u["padas"])
            # A lacuna line carries NO seg, so karaoke simply never lights it: the reader
            # sees the hole and hears the silence, and nothing claims to recite it.
            if u.get("lead_gap"):
                disp_lines.append({"t": "— — —", "k": "gap"})
            for pi, p in enumerate(u["padas"]):
                last = pi == len(u["padas"]) - 1
                if n_lead and pi == 0:
                    # the aphorism is bracketed by daṇḍas as the edition prints it:
                    # ॥ ॐ अथातो ब्रह्मजिज्ञासा ॐ॥
                    p = "॥ " + ("ॐ " * n_lead) + p
                if u["type"] == "sutra" and last:
                    # the edition prints the closing pranava INSIDE the daṇḍa
                    # (॥ ॐ अथातो ब्रह्मजिज्ञासा ॐ॥), so the ॐ comes first and the daṇḍa
                    # closes the whole aphorism
                    p = p + " ॐ॥"
                hard = bounds[pi] if pi < len(bounds) else "hard"
                # A śloka closes on its number as the edition prints it (॥ १५६ ॥). The
                # number is stripped before TTS — it is not recited — but the reader needs
                # it to find a verse, so it is restored on the closing line here.
                vn = u.get("verse")
                mark = (("॥ %s ॥" % deva_num(vn) if vn else "॥") if (last and u["type"] == "padya")
                        else ("।" if hard == "hard" else ""))
                if u["type"] == "sutra" and last:
                    mark = ""
                # `_p`/`_m` are kept alongside `t` so regroup_to_edition() can recompose a
                # merged line WITHOUT the interior daṇḍa: the mark below is added by US for a
                # pada boundary, and where the edition prints one line ('कर्मभिः शुद्धसत्त्वानां
                # …') that mark is the fabricated 'कर्मभिः ।'. They are stripped before the
                # row is serialised.
                disp_lines.append({"t": (p + " " + mark).strip(), "k": u["type"],
                                   "_p": p, "_m": mark})
                idx[(ui, pi)] = len(disp_lines) - 1
                if n_lead and pi == 0:                       # leading ॐ light this line
                    for k in range(n_lead):
                        idx[(ui, f"om{k}")] = len(disp_lines) - 1
                if u["type"] == "sutra" and last:
                    idx[(ui, "omT")] = len(disp_lines) - 1
                if pi < len(gapafter) and gapafter[pi]:
                    disp_lines.append({"t": "— — —", "k": "gap"})
        # ONE DISPLAY LINE PER EDITION LINE — regroup the per-pada lines above so the reader
        # shows what the book prints. A pada is a TTS unit chosen for render stability (16–45
        # akṣaras, split at visargas); an edition line is what a reader expects to see. Welding
        # them together is what put 'कर्मभिः ।' on its own line, mid-hemistich, in every work
        # whose verse `is_padya` failed to mark. `segs.ln` is a list precisely so several clips
        # can light one line, so nothing about the audio has to change for this.
        disp_lines, idx = regroup_to_edition(disp_lines, idx, WORK,
                                             json.loads(json.dumps(part.get("covers")
                                                        or [part.get("seq", b.get("seq"))])),
                                             con, stats)
        for l in disp_lines:
            l.pop("_p", None); l.pop("_m", None)
        lines = json.dumps(disp_lines, ensure_ascii=False)
        segs = [{"s": s["s"], "e": s["e"], "ln": idx[(s["u"], s.get("p", 0))]}
                for s in t["segs"] if (s["u"], s.get("p", 0)) in idx]
        # Since display lines follow the EDITION, several clips may light one line, so segs
        # outnumbering lines is expected — not a fault. What must never happen is a recitable
        # line with NO seg: that line would sit dark through the whole recitation.
        n_gap = sum(1 for l in disp_lines if l["k"] == "gap")
        lit = {i for s in segs for i in s["ln"]}
        dark = [i for i, l in enumerate(disp_lines) if l["k"] != "gap" and i not in lit]
        if dark:
            print(f"  [warn] {part['id']}: {len(dark)} recitable line(s) with no seg "
                  f"(of {len(disp_lines)-n_gap}); first={dark[:3]}")
        # columns named, not positional: `base` was added later for the two-bucket work and
        # a positional insert silently went out of step with the table
        con.execute("INSERT INTO audio (work,block,part,path,dur,kind,ref,seq,lines,covers) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (WORK, t["block"], t["part"], t["path"], t["dur"],
                     part.get("kind"), b.get("ref"),
                     part.get("seq", b.get("seq")), lines,
                     json.dumps(part.get("covers") or [part.get("seq", b.get("seq"))])))
        con.execute("INSERT INTO audio_timings (work,block,part,segs) VALUES (?,?,?,?)",
                    (WORK, t["block"], t["part"], json.dumps(segs, ensure_ascii=False)))
        n += 1
    con.commit()
    if n_el:
        print(f"  edition-line regroup: rows={stats['rows-regrouped']} "
              f"lines_merged={stats['merged-lines']} "
              f"unaligned={stats['unaligned']} no_structure={stats['no-structure']} "
              f"stale={stats['stale-block']+stats['stale-part']} "
              f"not_in_db={stats['not-in-db']}")

    tot = con.execute("SELECT count(*), round(sum(dur)/60,2) FROM audio WHERE work=?",
                      (WORK,)).fetchone()
    con.close()
    print(f"wrote {n} audio rows -> {a.db}")
    print(f"  work total: {tot[0]} files, {tot[1]} min")


if __name__ == "__main__":
    main()
