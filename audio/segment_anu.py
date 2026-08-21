#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anuvyākhyāna segmentation — the `Sarvamula`-only, all-verse shape (group B).

Simpler than BSB: no Mula pairing, no prose, no visarga rule, no quote detection.
    block = adhikaraṇa (a Heading3 span)
    unit  = śloka       (split on the verse number ॥ N ॥) — the karaoke unit
    pada  = metrical line (split on ।)                    — one clip each

Two things this work needs that BSB did not:

1. ŚLOKAS SPLIT ACROSS ENTRIES. The edition prints topic headings *inside* a verse, so
   śloka १५६ is the unnumbered tail of seq 36 plus the head of seq 38, with Heading3
   "आनन्दमयाधिकरणम्" between them. The Sarvamula entries are therefore concatenated into
   one stream before splitting; headings are structure, not text.

2. LACUNAE. 68 of 1995 ślokas (3.4%) carry lost text marked by dash runs
   ("शब्दानां प्रथमे पादे --- --- ---"). These are NOT rendered and NOT bridged: joining
   the surviving halves would make the recitation assert a line the manuscript does not
   have, and the join would be inaudible. Instead a lacuna becomes an explicit gap —
   silence in the audio, a visible un-highlighted line in the karaoke.

   Because a gap can be printed on BOTH sides of an entry break (the tail of seq 36 ends
   with one and the head of seq 38 begins with one — the SAME hole), adjacent gaps are
   COLLAPSED. One hole, one silence.

Fallback metre is anuṣṭubh here, not vasantatilakā: the work is overwhelmingly anuṣṭubh,
and a lacuna-broken śloka will always fail chandas detection.
"""
import argparse, hashlib, json, os, re, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import segment_bsb as SB

DB = "/Users/prathosh/Sarvamula/web/sarvamula.db"
WORK = "anu_vyakhyana"
FALLBACK_METER = "anuṣṭubh"

# ── shape B-verse registry ────────────────────────────────────────────────────
# All of these are Sarvamula-only ślokas; they differ only in how the edition delimits a
# verse and what the files should be called.
#   split "number" the verse ends at its printed number (॥ १५६ ॥ / ॥ १॥)
#         "danda"  the edition prints NO numbers, so each ॥-span is a verse
#                  (krshna_amrta_maharnava: 12,765 akṣaras, zero verse numbers)
#   parens strip "(…)" from recitation — editorial apparatus, off for the shipped work
WORKS = {
    "anu_vyakhyana":          dict(prefix="anu", split="number", parens=False,
                                   part_kind="vyakhyana"),
    "tantrasara_sangraha":    dict(prefix="tss", split="number", parens=True,
                                   part_kind="mula"),
    "sadachara_smriti":       dict(prefix="sas", split="number", parens=True,
                                   part_kind="mula"),
    "krshna_amrta_maharnava": dict(prefix="kam", split="danda",  parens=True,
                                   part_kind="mula"),
    # A verse summary of the Brahmasūtras in four adhyāyas — its own name is Bhāṣya, so it
    # keeps that label rather than the neutral one used for the prakaraṇas.
    "sangraha_bhashya":       dict(prefix="sgb", split="number", parens=True,
                                   part_kind="bhashya"),
    # Ṛg Bhāṣya. Verse throughout and split mid-śloka across entries exactly like
    # Anuvyākhyāna, so it belongs to this shape and not to BSB's — but it is numbered
    # differently: ONE printed "॥ N॥" in the whole work against 1,475 double daṇḍas, so the
    # daṇḍa has to end the verse. 242 lacuna runs (the edition's --- ---) are already handled.
    # The 455 accented ṛks are `Mula` entries and this segmenter reads only Sarvamula, so
    # they are excluded for free — they are being recited by hand, since no TTS should be
    # trusted with Vedic svara.
    "rg_bhashya":             dict(prefix="rgb", split="danda", parens=True,
                                   part_kind="bhashya"),
    # Five short works in Madhva's own voice — a yamaka poem, the stotra appendix, and three
    # ritual manuals. All Sarvamula-only verse with the number printed (81/15/27/16/12
    # occurrences), so they take Anuvyākhyāna's treatment unchanged; none carries svara or a
    # lacuna. part_kind "mula" because they are works, not commentary on one.
    "yamaka_bharata":         dict(prefix="ymb", split="number", parens=True,
                                   part_kind="mula"),
    "parishishta":            dict(prefix="prs", split="number", parens=True,
                                   part_kind="mula"),
    "yati_pranava_kalpa":     dict(prefix="ypk", split="number", parens=True,
                                   part_kind="mula"),
    "jayanti_kalpa":          dict(prefix="jyk", split="number", parens=True,
                                   part_kind="mula"),
    "nyasa_paddhati":         dict(prefix="nyp", split="number", parens=True,
                                   part_kind="mula"),
    # Dvādaśa Stotra: twelve adhyāya-sized slabs, verses delimited by the daṇḍa — only 12
    # printed numbers in the whole work (one per adhyāya), so numbers cannot split it.
    # Rendered by TTS while the hand recitation's timestamps are sorted out separately.
    "dvadasha_stotra":        dict(prefix="dvd", split="danda", parens=True,
                                   part_kind="mula"),
}


def cfg_for(work):
    if work not in WORKS:
        sys.exit(f"{work}: not a registered B-verse work (known: {', '.join(sorted(WORKS))})")
    return dict(WORKS[work], work=work)

# An asterisk stands in for a number where the edition leaves a verse unnumbered — the
# maṅgala and closing ślokas of the Saṅgraha Bhāṣya are printed "॥ *॥". Without this they
# do not close a verse, and the maṅgala runs on into the first numbered śloka. Only
# sangraha_bhashya uses the form (3 occurrences; zero in every other B-verse work), so
# accepting it cannot disturb anything already shipped.
_VNUM = re.compile(r"॥\s*(?:([०-९\d]+)|\*)\s*॥")
_DASH = re.compile(r"(?:-+\s*){2,}")          # lacuna: two or more dash groups
_AK = re.compile(r"[अ-हऽ]")
# Vedic accent. Anything carrying it is śruti and must NOT be synthesised: Ṛg Bhāṣya prints
# three ṛks (RV 1.2.6, 1.2.7, 1.28.8) inside its Sarvamula entries rather than tagging them
# Mula, so they reach this segmenter looking like commentary. They are recited by hand.
_SVARA = re.compile(r"[॒॑॓॔᳐-᳿꣠-ꣿ]")
# An edition mark standing where a verse number would go is not a pāda. Ṛg Bhāṣya prints
# "॥ छ॥" between verses; left alone it became three one-akṣara clips of a bare consonant.
_MARKER = re.compile(r"^(?:छ|छं|\*|॰|ऽ)$")
SKIPPED_SVARA = []                         # reported by main() so the held passages are logged
GAP = "—"                                 # em dash: the display marker for a lacuna


def clean(t):
    t = re.sub(r"[०-९]+", "", t or "")
    t = re.sub(r"[/]", "", t)
    # Square brackets are DELIMITERS, never sound — and unlike "(…)" they were never stripped:
    # .strip() below only removes listed characters at a pada's EDGE. The model duly voiced the
    # leading one of Saṅgraha Bhāṣya's maṅgala, "[नारायणं … उच्यते॥ *॥]", as "a".
    # A group holding text is recitation in an editorial wrapper -> unwrap it. A group holding
    # nothing recitable ("[-]", "[---]") marks a lacuna and is apparatus entire -> delete it,
    # so no bare dash is left behind to be split off as a pada of its own.
    t = SB._debracket(t)
    # curly quotes must be stripped too: a closing “ ” or ‘ ’ left stranded by a daṇḍa
    # split becomes a pada of its own, and 24 such quote-only "padas" were queued for
    # rendering. A pada with no akṣara is not recitable — see the caller's guard.
    return re.sub(r"\s+", " ", t).strip(" ।॥,;-“”‘’\"'()")


def split_sloka(body):
    """One śloka -> (padas, gapafter) where gapafter[i] means a lacuna follows pada i.
    A leading lacuna is reported separately so the caller can place silence before the
    first pada."""
    padas, gapafter, lead = [], [], False
    for i, chunk in enumerate(_DASH.split(body)):
        for p in re.split(r"[।॥]", chunk):
            p = clean(p)
            if not p or not _AK.search(p):  # nothing recitable — see clean()
                continue
            if _SVARA.search(p):
                SKIPPED_SVARA.append(p); continue
            if _MARKER.match(p) or len(_AK.findall(p)) < 2:
                continue                    # edition mark, not text
            padas.append(p); gapafter.append(False)
        if i < len(_DASH.split(body)) - 1:      # a lacuna followed this chunk
            if padas:
                gapafter[-1] = True
            else:
                lead = True
    return padas, gapafter, lead


def load_stream(db=DB, work=WORK):
    """ONE continuous verse stream for the work, plus a map of where each heading applies.

    Blocks must NOT be cut at headings: this edition prints topic headings *inside* a
    verse (Heading3 आनन्दमयाधिकरणम् sits between the two halves of śloka १५६), so cutting
    there split a śloka across two audio files and defeated the lacuna dedupe. Instead the
    whole work is one stream, and each śloka is assigned to the adhikaraṇa that was open
    where the śloka STARTS — so a verse is never divided."""
    con = sqlite3.connect(db); con.row_factory = sqlite3.Row
    rows = list(con.execute(
        "select seq, content_type, heading_level, text_dev from entries "
        "where work=? order by seq", (work,)))
    con.close()

    parts, marks, h, off = [], [], {1: None, 2: None, 3: None}, 0
    for r in rows:
        ct = r["content_type"] or ""
        if ct.startswith("Heading"):
            lvl = r["heading_level"] or int(ct[-1])
            h[lvl] = r["text_dev"]
            for d in range(lvl + 1, 4):
                h[d] = None
            marks.append((off, dict(h)))        # heading context takes effect here
            continue
        if ct not in ("Sarvamula", "Colophon_Sarvamula"):
            continue
        if not marks:
            marks.append((0, dict(h)))
        t = (r["text_dev"] or "") + " "
        parts.append((off, r["seq"], t))
        off += len(t)
    return "".join(t for _, _, t in parts), marks, parts


def context_at(marks, pos):
    ctx = marks[0][1]
    for at, m in marks:
        if at <= pos:
            ctx = m
        else:
            break
    return ctx


def seqs_in(parts, a, b):
    """Every entry seq whose text overlaps [a, b).

    A śloka is NOT contained in one entry: the edition breaks verses across entries (and
    a colophon is the tail of the śloka before it), so attributing a śloka to the entry it
    STARTS in leaves the continuation entries unclaimed — and the reader then printed their
    text a second time, raw, below the audio that already recites it."""
    out = []
    for at, sq, t in parts:
        if at < b and at + len(t) > a:
            out.append(sq)
    return out or ([parts[0][1]] if parts else [])


def seq_at(parts, pos):
    s = parts[0][1] if parts else None
    for at, sq, t in parts:
        if at <= pos:
            s = sq
        else:
            break
    return s


def split_stream(stream, detect, cfg=None):
    cfg = cfg or cfg_for(WORK)
    """Whole work -> flat list of ślokas, each tagged with its start offset."""
    out, pos = [], 0
    pieces = []
    if cfg["split"] == "number":
        for m in _VNUM.finditer(stream):
            pieces.append((m.group(1), stream[pos:m.start()], pos, m.end())); pos = m.end()
    else:
        # no printed numbers: the double daṇḍa itself ends each verse
        for m in re.finditer(r"॥", stream):
            body = stream[pos:m.start()]
            if _AK.search(body):
                pieces.append((None, body, pos, m.end()))
            pos = m.end()
    tail = stream[pos:]
    if tail.strip():
        pieces.append((None, tail, pos, len(stream)))

    # A piece begins where the PREVIOUS verse's daṇḍa ended, which is the space that
    # load_stream appends after every entry — one character short of where that entry's
    # heading mark was recorded. So `start` fell inside the previous section and
    # context_at() handed the śloka the previous heading: Pariśiṣṭa's five stotras each
    # ended up owning the first verse of the next one, putting the Kanduka Stuti inside the
    # Nṛsiṃha Nakha Stotra's tile. Advance past the whitespace so `start` is real text.
    pieces = [(num, body, start + (len(body) - len(body.lstrip())), end)
              for num, body, start, end in pieces]

    for num, body, start, end in pieces:
        padas, gapafter, lead = split_sloka(body)
        if not padas:
            continue
        meter = detect(" । ".join(padas)) or ""
        key = SB.METER_ALIAS.get(meter, meter)
        if not key or key not in SB.BANK_KEYS or meter in SB.NO_REFERENCE:
            key, src = FALLBACK_METER, "fallback"
        else:
            src = "detected"
        padas, bounds = SB.fit_padas(padas, ["hard"]*len(padas))
        gapafter = (gapafter + [False]*len(padas))[:len(padas)]
        out.append({"type": "padya", "verse": num, "start": start, "end": end,
                    "padas": padas, "bounds": bounds,
                    "gapafter": gapafter, "lead_gap": lead,
                    "meter": key, "meter_src": src, "opens_pranava": False,
                    "text": " ".join(padas)})

    # ONE HOLE, ONE SILENCE — a lacuna printed at the end of one entry and again at the
    # start of the next is the same hole. Collapsed across the whole stream, so it works
    # even when a heading falls between the two halves.
    for i in range(len(out) - 1):
        if out[i]["gapafter"] and out[i]["gapafter"][-1] and out[i+1]["lead_gap"]:
            out[i+1]["lead_gap"] = False
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--out", default="blocks_anu.json")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--work", default=WORK, help="B-verse work slug (see WORKS)")
    a = ap.parse_args()

    cfg = cfg_for(a.work)
    globals()["WORK"] = a.work
    detect = SB._make_detector()
    stream, marks, parts_map = load_stream(a.db, a.work)
    if cfg["parens"]:
        # Editorial apparatus, never recitation — see segment_bsb.load_blocks.
        # BLANKED, NOT DELETED. load_stream has already recorded where each entry begins in
        # this string, and seqs_in maps a śloka back to its entries by those offsets. Deleting
        # the parentheticals shortened the stream underneath that map, so every offset past
        # the first one drifted — 375 characters by the end of Ṛg Bhāṣya, which put 481 of its
        # 899 ślokas against the wrong entry. Same-length spaces keep every offset true, and
        # clean() collapses them, so nothing reaches the reciter either way.
        stream = re.sub(r"\([^)]{0,60}\)", lambda m: " " * len(m.group(0)), stream)
    slokas = split_stream(stream, detect, cfg)

    # group ślokas into blocks by the adhikaraṇa open where each śloka STARTS
    groups, order = {}, []
    for s in slokas:
        ctx = context_at(marks, s["start"])
        key = (ctx.get(1), ctx.get(2), ctx.get(3))
        if key not in groups:
            groups[key] = {"ctx": ctx, "seq": seq_at(parts_map, s["start"]), "sl": []}
            order.append(key)
        groups[key]["sl"].append(s)

    out = []
    for i, key in enumerate(order, 1):
        g = groups[key]
        bid = f"{cfg['prefix']}_{i:03d}"
        units = []
        for n, s in enumerate(g["sl"], 1):
            u = dict(s, n=n, seq=seq_at(parts_map, s["start"]),
                     seqs=seqs_in(parts_map, s["start"], s["end"]))
            u["clip"] = SB.clip_id(bid, n, "padya", u["padas"], u["meter"])
            u["clips"] = [SB.pada_clip_id(bid, n, "padya", k, p, u["meter"])
                          for k, p in enumerate(u["padas"], 1)]
            units.append(u)
        b = {"seq": g["seq"], "adhyaya": g["ctx"].get(1),
             "pada": g["ctx"].get(2), "adhikarana": g["ctx"].get(3)}
        if not units:
            continue
        spans = SB.split_parts(units)
        parts = []
        for k, (s, e) in enumerate(spans, 1):
            us = units[s:e]
            # An adhikaraṇa spans many entries, so a part recites several: `covers` lists
            # them and the row anchors at the first, letting the reader print each entry's
            # text once (under the player) instead of once here and once in its own row.
            covers = sorted({q for u in us for q in u.get("seqs", [])})
            parts.append({"part": k, "kind": cfg.get("part_kind", "vyakhyana"),
                          "id": SB.part_id(bid, k, len(spans)),
                          "from": s + 1, "to": e,
                          "seq": covers[0] if covers else g["seq"], "covers": covers,
                          "units": [{"n": u["n"], "type": u["type"], "clips": u["clips"],
                                     "bounds": u["bounds"], "gapafter": u["gapafter"],
                                     "lead_gap": u["lead_gap"]} for u in us],
                          "clips": [c for u in us for c in u["clips"]],
                          "est_sec": round(SB.block_seconds(us), 1),
                          "path": f"{cfg['work']}/{bid}"
                                  + (f"_p{k}" if len(spans) > 1 else "") + ".m4a"})
        out.append({"id": bid, "ref": None, "seq": b["seq"], "kind": "sutra_block",
                    "adhyaya": b["adhyaya"], "pada": b["pada"],
                    "adhikarana": b["adhikarana"],
                    "est_sec": round(SB.block_seconds(units), 1),
                    "parts": parts, "units": units})

    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    nu = sum(len(b["units"]) for b in out)
    npd = sum(len(u["padas"]) for b in out for u in b["units"])
    ngap = sum(sum(u["gapafter"]) + (1 if u["lead_gap"] else 0)
               for b in out for u in b["units"])
    det = sum(1 for b in out for u in b["units"] if u["meter_src"] == "detected")
    print(f"blocks (adhikaraṇa) : {len(out)}")
    print(f"ślokas (units)      : {nu}   metre detected {det}, fallback {nu-det}")
    print(f"padas  (clips)      : {npd}")
    print(f"lacunae (after dedupe): {ngap}")
    print(f"files               : {sum(len(b['parts']) for b in out)}")
    print(f"est audio           : {sum(b['est_sec'] for b in out)/3600:.2f} h")
    print(f"-> {a.out}")
    if SKIPPED_SVARA:
        print(f"HELD FOR RECITATION (Vedic svara, not synthesised): {len(SKIPPED_SVARA)} pādas")
        for x in SKIPPED_SVARA[:8]:
            print("   ", x[:80])


if __name__ == "__main__":
    main()
