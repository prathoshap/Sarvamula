#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Put the Upaniṣad mūla back into the three bhāṣyas that lack it, by matching the BHĀṢYA.

Our editions of Aitareya / Bṛhadāraṇyaka(Kāṇva) / Chāndogya print Madhva's gloss with no
Upaniṣad text between the glosses. anandamakaranda.in prints both. The two editions cannot
be joined on structure — they disagree about khaṇḍa boundaries, and ours is far coarser
(25 khaṇḍa headings against the site's ~154 for Chāndogya) — and they cannot be joined on
the mūla, which we do not have. What they share is the bhāṣya.

So the bhāṣya is the join key. Each of the site's bhāṣya blocks is located inside our own
bhāṣya text; whatever mūla the site prints BEFORE that block belongs immediately before the
point where that block begins in ours. Reverse-fetching through the commentary this way
places the mūla by meaning rather than by counting sections.

Matching is fuzzy on purpose: the editions carry real variants (श्रुता/स्मृता,
नभोऽभिमानी/नभोभिमानी), so an exact join finds about half. Anchoring on an exact probe and
then verifying similarity locates 100% of blocks in order at 0.97–0.99.

Two safeguards, because a misplaced mūla is worse than an absent one:
  * the search is MONOTONIC — a block may not resolve behind the previous one, so a chance
    resemblance cannot throw a passage into the wrong chapter;
  * insertion points SNAP to a daṇḍa, so our bhāṣya is never cut mid-sentence.
"""
import argparse, json, re, sqlite3, sys, unicodedata, difflib

sys.path.insert(0, "/Users/prathosh/Sarvamula")
from build_db import norm          # the exact search-key function the db was built with

DB = "/Users/prathosh/Sarvamula/web/sarvamula.db"
DEVA = re.compile(r"[ऀ-ॿ]")
SHORT = 40          # below this a block cannot be anchored globally — see pass 2 in plan()


def norm_map(s):
    """Devanāgarī-only text plus, for each kept char, its index in the original."""
    out, idx = [], []
    for i, ch in enumerate(unicodedata.normalize("NFC", s)):
        if DEVA.match(ch):
            out.append(ch); idx.append(i)
    return "".join(out), idx


def anchor(needle, hay, start):
    """Locate `needle` in `hay` at or after `start`. Exact probe, then verify by similarity."""
    for L in (30, 24, 18):
        for i in range(0, max(1, len(needle) - L), 7):
            j = hay.find(needle[i:i + L], start)
            if j >= 0:
                pos = max(0, j - i)
                seg = hay[pos:pos + len(needle)]
                r = difflib.SequenceMatcher(None, needle, seg).quick_ratio()
                if r > 0.6:
                    return pos, r
    return None, 0.0


def pada_bounds(blocks_file):
    """Where every already-rendered pāda ENDS, per entry, in Devanāgarī-only coordinates.

    Splitting a bhāṣya entry anywhere else re-renders audio we already have. fit_padas packs
    prose greedily into 5-10 word pādas, so a cut in the middle of a pāda repacks everything
    downstream of it: the text of those pādas changes, their content hash changes, and clips
    that sound identical have to be synthesised again. Cutting exactly where a pāda already
    ends leaves the packing on both sides untouched — the first fragment packs the same way
    it always did, and the second starts from the same boundary the original did.

    That is the difference between re-rendering 1,209 bhāṣya clips and re-rendering none.
    """
    out = {}
    for b in json.load(open(blocks_file, encoding="utf-8")):
        seq = b.get("seq")
        if seq is None:
            continue
        acc, ends = 0, out.setdefault(seq, [])
        for u in b["units"]:
            for p in u["padas"]:
                acc += len(DEVA.findall(p))
                ends.append(acc)
    return out


def snap(text, pos, ends=None, dev_pos=None):
    """Move an insertion point to a safe boundary.

    With `ends` (pāda ends of the already-rendered segmentation) the point goes to the
    nearest pāda end, which keeps every existing bhāṣya clip byte-identical. Without it,
    fall back to the nearest daṇḍa so at least no sentence is cut mid-clause."""
    if pos <= 0 or pos >= len(text):
        return max(0, min(pos, len(text)))
    if ends and dev_pos is not None:
        near = min(ends, key=lambda e: abs(e - dev_pos))
        if abs(near - dev_pos) <= 60:
            seen, i = 0, 0                     # walk back to an original-text offset
            for i, ch in enumerate(text):
                if DEVA.match(ch):
                    seen += 1
                    if seen >= near:
                        return i + 1
            return len(text)
    best, bd = pos, 10 ** 9
    for m in re.finditer(r"[।॥]\s*", text):
        e = m.end()
        if abs(e - pos) < bd:
            best, bd = e, abs(e - pos)
    return best if bd <= 80 else pos


def plan(work, sitefile, db=DB):
    con = sqlite3.connect(db); con.row_factory = sqlite3.Row
    rows = list(con.execute("select * from entries where work=? order by seq", (work,)))
    body = [r for r in rows if r["content_type"] == "Sarvamula"]

    hay, owner, opos, dloc = "", [], [], []
    for r in body:
        n, idx = norm_map(r["text_dev"] or "")
        hay += n
        owner += [r["seq"]] * len(n)
        opos += idx
        dloc += list(range(len(n)))          # offset WITHIN this entry, Devanāgarī-only

    seq = json.load(open(sitefile, encoding="utf-8"))
    blocks = [i for i, x in enumerate(seq) if x["kind"] == "bhashya" and norm_map(x["text"])[0]]
    stats = dict(located=0, blocks=len(blocks), low=0, trailing=0, short=0, short_found=0)

    # PASS 1 — the blocks long enough to anchor on their own, in order.
    at, pos = {}, 0
    for i in blocks:
        n, _ = norm_map(seq[i]["text"])
        if len(n) < SHORT:
            continue
        p, r = anchor(n, hay, pos)
        if p is None:
            continue
        at[i] = (p, r); pos = p
        stats["located"] += 1
        if r < 0.85:
            stats["low"] += 1

    # PASS 2 — the SHORT blocks, which a global search could match anywhere by chance. Between
    # two located neighbours there is only one place they can be, so the search is confined to
    # that gap and a short probe becomes safe. Skipping them is not harmless: a short gloss that
    # gets no position of its own cannot flush the mūla standing before it, and 66 passages were
    # landing later in the work than anandamakaranda shows them.
    known = sorted(at)
    for i in blocks:
        if i in at:
            continue
        n, _ = norm_map(seq[i]["text"])
        stats["short"] += 1
        lo = max((at[k][0] for k in known if k < i), default=0)
        hi = min((at[k][0] for k in known if k > i), default=len(hay))
        if hi <= lo or len(n) < 6:
            continue
        window = hay[lo:hi]
        probe = n[:min(14, len(n))]
        j = window.find(probe)
        if j < 0 and len(n) >= 10:
            j = window.find(n[2:12])
        if j >= 0:
            at[i] = (lo + j, 1.0); stats["short_found"] += 1

    # walk the site in order, flushing the mūla before the block it precedes
    pending, ins = [], []
    for i, x in enumerate(seq):
        if x["kind"] == "mula":
            pending.append(x["text"]); continue
        if i not in at or not pending:
            continue
        p, r = at[i]
        ins.append(dict(hay=p, seq=owner[p], off=opos[p], doff=dloc[p],
                        mula=pending, sim=round(r, 3)))
        pending = []
    if pending and body:                       # mūla after the last located block
        stats["trailing"] = len(pending)
        ins.append(dict(hay=len(hay), seq=body[-1]["seq"], doff=10 ** 9,
                        off=len(body[-1]["text_dev"] or ""), mula=pending, sim=None))
    ins.sort(key=lambda d: d["hay"])
    return rows, ins, stats


COLS = ("content_type", "heading_level", "is_padya", "pramana", "skandha", "adhyaya",
        "verse", "text_dev", "text_skel", "kutra", "variants", "footnote")


def _frag(parent, text, variants):
    """A piece of a split bhāṣya entry, carrying the parent's metadata.

    Splitting an entry cannot simply copy every column: text_skel is a search key derived
    from the text and would index the whole khaṇḍa against a fragment of it, so it is
    RECOMPUTED with the same norm() the database was built by. variants are keyed by the
    reading they quote, not by offset, so each goes to the fragment that actually contains
    it — anything unlocated stays with the first fragment rather than being dropped."""
    d = {k: parent[k] for k in COLS}
    d["text_dev"] = text
    d["text_skel"] = norm(text)
    d["variants"] = json.dumps(variants, ensure_ascii=False) if variants else None
    return d


def apply(rows, ins, work, con, dry=True, bounds=None):
    """Rewrite the work's entries with the mūla spliced in, renumbering seq."""
    by_seq = {}
    for it in ins:
        by_seq.setdefault(it["seq"], []).append(it)
    out, n_mula = [], 0
    for r in rows:
        r = dict(r)
        its = sorted(by_seq.get(r["seq"], []), key=lambda x: x["off"]) \
            if r["content_type"] == "Sarvamula" else []
        if not its:
            out.append(r); continue

        text = r["text_dev"] or ""
        try:
            vars_all = json.loads(r["variants"]) if r["variants"] else []
        except Exception:
            vars_all = []
        ends = (bounds or {}).get(r["seq"])
        at_of = {id(it): snap(text, it["off"], ends, it.get("doff")) for it in its}
        cuts = sorted(set(at_of.values()))
        pieces, prev = [], 0
        for at in cuts:
            pieces.append((prev, at)); prev = at
        pieces.append((prev, len(text)))

        placed = set()
        first = True
        for k, (s, e) in enumerate(pieces):
            head = text[s:e].strip()
            if head:
                mine = []
                for vi, v in enumerate(vars_all):
                    if vi in placed:              # exactly one home per variant: a short
                        continue                  # reading can match several fragments
                    probe = re.sub(r'[^ऀ-ॿ]', '', str(v.get("trk_patha") or v.get("bg_patha") or ""))
                    if probe and probe[:14] in re.sub(r'[^ऀ-ॿ]', '', head):
                        mine.append(v); placed.add(vi)
                f = _frag(r, head, mine)
                if not first:                     # metadata that belongs to the entry, not
                    f["kutra"] = None             # to each of its pieces
                    f["footnote"] = None
                out.append(f); first = False
            if k < len(cuts):
                for m in (mu for it in its if at_of[id(it)] == cuts[k] for mu in it["mula"]):
                    t = m.strip()
                    out.append({**{c: None for c in COLS}, "content_type": "Mula",
                                "is_padya": 0, "pramana": 0,
                                "text_dev": t, "text_skel": norm(t)})
                    n_mula += 1
        # a variant whose reading spans a cut would otherwise vanish
        lost = [v for i, v in enumerate(vars_all) if i not in placed]
        if lost:
            for f in out[::-1]:
                if f["content_type"] == "Sarvamula":
                    cur = json.loads(f["variants"]) if f["variants"] else []
                    f["variants"] = json.dumps(cur + lost, ensure_ascii=False)
                    break
    if dry:
        return out, n_mula
    con.execute("DELETE FROM entries WHERE work=?", (work,))
    con.executemany(
        f"INSERT INTO entries (work,seq,{','.join(COLS)}) "
        f"VALUES (?,?,{','.join('?' * len(COLS))})",
        [(work, i, *[e[c] for c in COLS]) for i, e in enumerate(out)])
    con.commit()
    return out, n_mula


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--site", required=True)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--pada-bounds", default="",
                    help="blocks JSON of the CURRENT segmentation; cuts snap to its "
                         "pāda ends so no existing bhāṣya clip changes")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    rows, ins, st = plan(a.work, a.site, a.db)
    con = sqlite3.connect(a.db)
    bounds = pada_bounds(a.pada_bounds) if a.pada_bounds else None
    out, n_mula = apply(rows, ins, a.work, con, dry=not a.write, bounds=bounds)
    aks = sum(len(DEVA.findall(e["text_dev"] or "")) for e in out if e["content_type"] == "Mula")
    print(f"{a.work}: located {st['located']}/{st['blocks']} site blocks "
          f"({st['low']} below 0.85 similarity)")
    print(f"  {len(ins)} insertion points -> {n_mula} mūla entries, {aks:,} akṣaras")
    print(f"  entries {len(rows)} -> {len(out)}"
          + ("  [WRITTEN]" if a.write else "  [dry run — pass --write]"))


if __name__ == "__main__":
    main()
