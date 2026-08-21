#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Two reading works that are pure mūla: the Brahmasūtras and the Bhagavad-Gītā.

Both texts are already in the corpus and already recited — but only ever *inside* a
commentary, cut the way a commentary quotes them. These are the root texts on their own
terms, and the audio is the PĀRĀYAṆA cut: one continuous track per pāda (Brahmasūtra) and
per adhyāya (Gītā), because these two are recited straight through rather than consulted a
sūtra at a time. Karaoke stays per sūtra / per verse inside the track.

Nothing is rendered: assemble_parayana.py restitches the existing clips.

    assemble_parayana.py ...            # build the tracks (on the box, where the clips are)
    build_mula_works.py                 # then write entries, works and audio rows here
    build_mula_works.py --drop          # remove both works again
"""
import argparse, json, re, sqlite3

DB = "/Users/prathosh/Sarvamula/web/sarvamula.db"
BS, GT = "brahmasutra", "bhagavadgita"
_D = str.maketrans("0123456789", "०१२३४५६७८९")
deva = lambda x: str(x).translate(_D)
_A = str.maketrans("०१२३४५६७८९", "0123456789")


def headings_of(con, work, level):
    return [r[0] for r in con.execute(
        "select text_dev from entries where work=? and content_type=? order by seq",
        (work, f"Heading{level}"))]


def wipe(con):
    for w in (BS, GT):
        for t in ("entries", "audio", "audio_timings"):
            con.execute(f"DELETE FROM {t} WHERE work=?", (w,))
        con.execute("DELETE FROM works WHERE slug=?", (w,))


def add(con, work, seq, ct, text, lvl=None, adh=None, verse=None, padya=0):
    con.execute("INSERT INTO entries (work,seq,content_type,heading_level,is_padya,"
                "skandha,adhyaya,verse,text_dev) VALUES (?,?,?,?,?,?,?,?,?)",
                (work, seq, ct, lvl, padya, None, adh, verse, text))


def unit_text(u, mark, pranava=False, double=False):
    """The recited text of one unit, with its reference restored for the reader.

    A sūtra is SHOWN with the pranavas it is recited with — ॐ … ॐ, and two at the head of
    the first sūtra of the work — so the page matches what the track says. The pādas
    themselves never carry ॐ (it is stripped before TTS and spliced from the exemplar), so
    it is restored here for display only."""
    body = " । ".join(p.replace("ॐ", "").strip(" ।॥") for p in u["padas"]) \
           if len(u["padas"]) > 1 and not pranava else \
           " ".join(u["padas"]).replace("ॐ", "").strip(" ।॥")
    if pranava:
        body = ("ॐ ॐ " if double else "ॐ ") + body + " ॐ"
    return body + f"॥ {mark}॥"


# a speaker tag lifted onto its own line: '…वाच-' followed by verse on the same pāda.
# Hyphen-terminated, which in the Gītā source is always a tag and never the verb.
_TAG = re.compile(r'^(\S{0,24}?वाच-)\s+(\S.*)$')


def unit_lines(u, mark):
    """One display line per PĀDA, with the daṇḍa the edition prints between hemistichs.

    Joining the pādas into a single string dropped the mid-verse daṇḍa, so the pārāyaṇa
    Gītā read 'समवेता युयुत्सवः मामकाः पाण्डवाश्चैव' as one run — the two hemistichs fused with
    no break, where Gītā Bhāṣya prints the same verse on two lines. The recitation is
    unaffected (one clip per pāda already); only the page was wrong. A verse's single seg
    lights every line it produced, which `segs.ln` being a list already allows.
    """
    pad = [p.replace("ॐ", "").strip(" ।॥") for p in u["padas"] if p.strip()]
    if not pad:
        return []
    # Lift a speaker tag onto its own line. fit_padas absorbs 'श्रीभगवानुवाच-' into the verse
    # after it — 6 akṣaras ending in a HYPHEN, which is a soft boundary — so it printed as
    # 'श्रीभगवानुवाच- इदं शरीरं कौन्तेय…' in all 18 adhyāyas, while 'अर्जुन उवाच ।' survived
    # because a daṇḍa is hard. In the Gītā source a hyphen-terminated …वाच- occurs 28 times and
    # is ALWAYS a standalone tag, never inline, so the hyphen is a safe signal — unlike bare
    # 'उवाच', which is usually the finite verb ('उवाच पार्थ पश्यैतान्', 1/25).
    out = []
    for p in pad:
        m = _TAG.match(p)
        if m:
            out.append((m.group(1), False))     # the tag itself takes no daṇḍa
            out.append((m.group(2), True))
        else:
            out.append((p, True))
    lines, last = [], max(i for i, (_, v) in enumerate(out) if v)
    for i, (t, versey) in enumerate(out):
        if not versey:
            lines.append(t)
        elif i == last:
            lines.append(t + f" ॥ {mark}॥")
        else:
            lines.append(t + " ।")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--parayana", default="timings_parayana.json")
    ap.add_argument("--blocks-bsb", default="blocks_bsb.json")
    ap.add_argument("--blocks-gita", default="blocks_gt.json")
    ap.add_argument("--drop", action="store_true")
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    wipe(con)
    if a.drop:
        con.commit(); print("removed brahmasutra and bhagavadgita"); return

    tracks = json.load(open(a.parayana, encoding="utf-8"))
    bsb = json.load(open(a.blocks_bsb, encoding="utf-8"))
    gita = json.load(open(a.blocks_gita, encoding="utf-8"))

    # the text of every sūtra and every Gītā verse, by reference
    sutra = {}
    for b in bsb:
        if not b.get("ref"):
            continue
        for u in b["units"]:
            if u["type"] == "sutra":
                sutra[b["ref"]] = u
    verse = {}
    for b in gita:
        for u in b["units"]:
            if u.get("is_mula") and u.get("verse"):
                verse[u["verse"]] = u

    adh_bs = headings_of(con, "sutra_bhashya", 1)
    pada_bs = headings_of(con, "sutra_bhashya", 2)
    adh_bg = headings_of(con, "gita_tatparya", 1)

    counts = {}
    for work, title, order in ((BS, "Brahmasūtra", 1), (GT, "Bhagavad-Gītā", 2)):
        ts = [t for t in tracks if t["work"] == work]
        seq, cur_a, n_units, dur = 0, None, 0, 0.0
        arows, trows = [], []
        for t in ts:
            first = t["segs"][0]["ref"] if t["segs"] else None
            if not first:
                continue
            bits = first.split("/")
            adh = int(bits[0].translate(_A))
            if adh != cur_a:
                names = adh_bs if work == BS else adh_bg
                nm = names[adh-1] if adh <= len(names) else f"अध्यायः {deva(adh)}"
                add(con, work, seq, "Heading1", nm, lvl=1, adh=adh); seq += 1
                cur_a = adh
            if work == BS:                       # a pāda heading under the adhyāya
                pada = int(bits[1].translate(_A))
                i = (adh-1)*4 + pada - 1
                nm = pada_bs[i] if i < len(pada_bs) else f"पादः {deva(pada)}"
                add(con, work, seq, "Heading2", nm, lvl=2, adh=adh); seq += 1

            # one entry per sūtra / verse, and one AUDIO ROW for the whole track
            lines, covers, anchor, segs = [], [], None, []
            for k, sg in enumerate(t["segs"]):
                ref = sg["ref"]
                u = sutra.get(ref) if work == BS else verse.get(ref)
                if u is None:
                    continue
                mark = " ".join(deva(x) for x in ref.split("/")) if work == BS else deva(ref)
                # For the Gītā the entry text is the display lines joined, so the reader's body
                # text and the karaoke pane agree — including the speaker tag standing alone.
                vlines = unit_lines(u, mark) if work == GT else None
                txt = " ".join(vlines) if vlines else \
                      unit_text(u, mark.replace(" ", "।") if work == BS else mark,
                                pranava=(work == BS),
                                double=(work == BS and ref == "1/1/1"))
                add(con, work, seq, "Mula", txt, adh=adh,
                    verse=int(bits[-1].translate(_A)) if work == BS else None, padya=1)
                if anchor is None:
                    anchor = seq
                covers.append(seq)
                # The Gītā is printed one hemistich per line; a sūtra is one aphorism and stays
                # on one line (its pādas are not metrical, and it carries the framing pranavas).
                # The verse's single seg lights every line it produced, so karaoke keeps the
                # whole śloka highlighted while it is recited.
                vlines = vlines or [txt]
                first = len(lines)
                lines += [{"t": t, "k": "padya"} for t in vlines]
                segs.append({"s": sg["s"], "e": sg["e"],
                             "ln": list(range(first, len(lines)))})
                seq += 1; n_units += 1
            if anchor is None:
                continue
            arows.append((work, t["block"], 0, t["path"], t["dur"], "mula", first, anchor,
                          json.dumps(lines, ensure_ascii=False),
                          json.dumps(covers), None))
            trows.append((work, t["block"], 0, json.dumps(segs, ensure_ascii=False)))
            dur += t["dur"]
        con.executemany("INSERT INTO audio (work,block,part,path,dur,kind,ref,seq,lines,covers,base) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)", arows)
        con.executemany("INSERT INTO audio_timings (work,block,part,segs) VALUES (?,?,?,?)", trows)
        ntop = len(adh_bs) + len(pada_bs) if work == BS else len(adh_bg)
        con.execute("INSERT INTO works (slug,title,ord,n_blocks,n_padya,n_topics) VALUES (?,?,?,?,?,?)",
                    (work, title, order, n_units, n_units, ntop))
        counts[work] = (n_units, len(arows), dur)
    con.commit()

    for w, (n, tr, d) in counts.items():
        print(f"{w:14s} {n:4d} units, {tr:2d} pārāyaṇa tracks, {d/60:.0f} min")
    print("audio is the pārāyaṇa cut — continuous per pāda / adhyāya, karaoke per sūtra / verse")


if __name__ == "__main__":
    main()
