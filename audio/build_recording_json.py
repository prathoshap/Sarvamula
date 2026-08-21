#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the by-śloka recording JSON — the file the iPad recorder reads.

The pipeline it feeds:

    <work>_by_shloka.json  --> iPad recorder --> wav + <work>_timestamps_*.json
                                                 blocks: [{id, start_ms, end_ms, take}]

so every recordable unit needs a STABLE UUID: the timestamps come back keyed by it, and
that id is the only thing tying a stretch of wav to a stretch of text.

For Ṛg Bhāṣya the split of labour is: the VEDA IS RECITED, the bhāṣya is rendered. Vedic
svara is not something the TTS can be trusted with, and the mantras are the part where
getting it wrong matters most — so --only Mula keeps the 486 mantras in the recording
script and leaves the 1,021 bhāṣya blocks to the renderer. Both halves keep their place
in one sequence, because the sidecar index numbers every block of the work, recorded or
not, so the two audio sources interleave back in reading order.

Two transformations:

  * SPLIT BY ŚLOKA. The source groups many verses into one unit (one runs to ten lines);
    a reciter needs one verse per block, and a ten-line block means re-recording ten verses
    to fix one. A unit closes at a line ending in ॥. This is a pure re-grouping — the line
    count is asserted unchanged, so no text can be lost or duplicated in the process.

  * RE-SOURCE THE MANTRAS from the deergha-svarita Ṛgveda. The bhāṣya's own quotations are
    what is being recited, and they must carry the accent notation of the Veda, not the
    commentary's. In fact all 486 already match that file svara-for-svara — re-sourcing is
    therefore a no-op that PROVES the file is faithful rather than assuming it, and would
    catch any drift on a re-run.

The bhāṣya's local reference (॥ ३४/६॥) is kept rather than the Ṛgveda's own (॥ १.०३४.०६),
because the reader and the timestamps are indexed by the work's numbering.

The emitted parts carry ONLY the keys the recorder already understands (content_type, text,
is_padya, is_pramana). Anything I want for later wiring goes in a sidecar index instead, so
an unknown key can never confuse the recorder mid-session.
"""
import argparse, json, os, re, unicodedata, uuid

SVARA = re.compile(r"[॒॑॓॔᳐-᳿꣠-ꣿ̀-ͯ]")
# a verse closes on ॥ … optionally followed by its number, a * , or an editorial (४)
CLOSE = re.compile(r"॥\s*(?:[०-९\d]+\s*[/\.।]?\s*[०-९\d]*|\*)?\s*॥?\s*(?:\([०-९\d]+\))?\s*$")


def norm(s, keep_svara=False):
    s = unicodedata.normalize("NFC", s)
    if not keep_svara:
        s = SVARA.sub("", s)
    s = re.sub(r"[।॥\|\.]+", " ", s)
    s = re.sub(r"[०-९0-9/*()]+", "", s)
    return re.sub(r"\s+", "", s)


def rv_index(path):
    """Every Ṛgveda mantra, keyed by its svara-stripped text -> (ref, deergha text)."""
    d = json.load(open(path, encoding="utf-8"))
    idx = {}
    for m in d["mandalams"]:
        for a in m["aadhayaa"]:
            for e in a["sukta"]:
                full = e["a"] + " " + e["c"]
                ref = re.search(r"[०-९]+\.[०-९]+\.[०-९]+", e["c"])
                idx.setdefault(norm(full), []).append(
                    (ref.group(0) if ref else None, e["a"], e["c"]))
    return idx


def line_stream(content):
    """Every line of the work in reading order, tagged with the part it came from.

    The source's own units are PAGE-SIZED, not verse-sized: 33 of anuvyākhyāna's 74 end
    mid-verse, with the second hemistich opening the next unit. So the split cannot work
    inside a unit — the document has to be read as one stream of lines and re-cut at verse
    boundaries, which is why this yields lines rather than groups."""
    for parts in content.values():
        for p in parts:
            flags = {k: p[k] for k in ("is_padya", "is_pramana") if k in p}
            for ln in p["text"]:
                yield ln, p["content_type"], flags


def regroup(stream):
    """Cut the stream into verses. A verse closes on a line ending in ॥; a change of
    content_type also closes it, so prose never joins a verse. Flags are taken from the
    line that OPENS the verse — when a verse straddles two source units it belongs to the
    one it started in."""
    out, cur, ct, flags = [], [], None, {}
    for ln, c, f in stream:
        if cur and c != ct:
            out.append((cur, ct, flags)); cur = []
        if not cur:
            ct, flags = c, f
        cur.append(ln)
        if c != "Subheading" and CLOSE.search(ln.strip()):
            out.append((cur, ct, flags)); cur = []
    if cur:
        out.append((cur, ct, flags))
    return out


def build(src, rvpath=None, title=None, only=None):
    content = json.load(open(src, encoding="utf-8"))["content"]
    idx = rv_index(rvpath) if rvpath else {}
    units, sidecar = {}, []
    stats = dict(units_in=0, units_out=0, lines_in=0, lines_out=0,
                 mula=0, resourced=0, drift=0, skipped=0, dropped=0, unmatched=[])

    stats["units_in"] = sum(len(v) for v in content.values())
    stats["lines_in"] = sum(len(p["text"]) for v in content.values() for p in v)

    for pos, (g, ct, flags) in enumerate(regroup(line_stream(content))):
        if only and ct not in only:
            # NOT recorded — but still indexed, so the rendered bhāṣya and the recited
            # mantras can be interleaved back into one sequence afterwards
            stats["skipped"] += 1
            stats["lines_out"] += len(g)
            sidecar.append({"id": None, "pos": pos, "content_type": ct, "recorded": False,
                            "rigveda_ref": None, "n_lines": len(g),
                            "aksharas": sum(len(re.findall(r"[ऀ-ॿ]", l)) for l in g)})
            continue
        ref = None
        if ct == "Mula" and idx:
            stats["mula"] += 1
            hit = idx.get(norm(" ".join(g)))
            if hit:
                ref, a, c = hit[0]
                # keep the bhāṣya's own reference / annotation tail (॥ ३४/६॥ (४))
                tail = re.search(r"॥\s*[०-९\d]+\s*/\s*[०-९\d]+\s*॥.*$", g[-1])
                body = [a, re.sub(r"॥\s*[०-९\d\.]+\s*$", "", c).strip()]
                body[-1] = (body[-1] + " " + tail.group(0).strip()).strip() if tail else body[-1]
                if norm(" ".join(g), True) != norm(" ".join(body), True):
                    stats["drift"] += 1
                g = body
                stats["resourced"] += 1
            else:
                stats["unmatched"].append(" ".join(g)[:70])
        if len(re.findall(r"[अ-हऽ]", " ".join(g))) < 2:
            stats["dropped"] += len(g)     # a stray daṇḍa or lacuna mark: nothing to record
            stats["lines_out"] += len(g)   # still accounted for, so the audit below balances
            continue
        part = {"content_type": ct, "text": g, **flags}
        uid = str(uuid.uuid4())
        units[uid] = [part]
        sidecar.append({"id": uid, "pos": pos, "content_type": ct, "recorded": True,
                        "rigveda_ref": ref, "n_lines": len(g),
                        "aksharas": sum(len(re.findall(r"[ऀ-ॿ]", l)) for l in g)})
        stats["units_out"] += 1
        stats["lines_out"] += len(g)
    return {"title": title or "rgbhashya", "content": units}, sidecar, stats



def from_db(work, db="/Users/prathosh/Sarvamula/web/sarvamula.db"):
    """The work's recitable entries, in the shape build() expects.

    Some works have no by_shloka source file to start from — Dvādaśa Stotra lives only in
    the database, as twelve adhyāya-sized slabs. Headings are dropped (they are apparatus,
    not recitation); the colophon of each adhyāya is kept, because it is recited."""
    import sqlite3
    con = sqlite3.connect(db); con.row_factory = sqlite3.Row
    rows = con.execute("select seq, content_type, is_padya, text_dev from entries "
                       "where work=? order by seq", (work,)).fetchall()
    con.close()
    content = {}
    for r in rows:
        ct = r["content_type"] or ""
        if ct.startswith("Heading") or not (r["text_dev"] or "").strip():
            continue
        part = {"content_type": "Sarvamula" if ct == "Sarvamula" else ct,
                # break after a single daṇḍa always, and after a DOUBLE daṇḍa only when a
                # verse number does not follow — "॥ १ ॥" must stay with the line it closes,
                # or the line never ends in ॥ and the śloka regrouping below finds no verse
                # boundary at all (24 adhyāya-sized blocks instead of 90 verses).
                "text": [x.strip() for x in re.split(r"(?<=।)\s+|(?<=॥)\s+(?![०-९\d])",
                                                     re.sub(r"^\s*[।॥]+\s*", "", r["text_dev"]))
                         if x.strip()]}
        if r["is_padya"]:
            part["is_padya"] = True
        content[str(r["seq"])] = [part]
    return {"content": content}

ALL_TYPES = {"Mula", "Sarvamula", "Subheading", "Colophon_Sarvamula"}
_DEVA = str.maketrans("0123456789", "०१२३४५६७८९")
_ASCII = str.maketrans("०१२३४५६७८९", "0123456789")


def from_rigveda(path, mandala, lo, hi, title, ctype="Sarvamula"):
    """Emit the mantras of a sukta range straight from the Ṛgveda, in canonical order.

    Taking the Veda from the bhāṣya's own file turned out to be unsafe: rgbhashya.json is
    missing 1.2.6, 1.2.7 and 1.28.8 outright (they survive in the db copy, so the work does
    contain them — that file simply lost them). A recitation script that quietly skips three
    mantras is worse than one that is slightly over-inclusive, and the Veda's own numbering
    is the authority for what belongs in a sukta, so the range is enumerated from the Veda
    and nothing can go missing.
    """
    d = json.load(open(path, encoding="utf-8"))
    rows = []
    for m in d["mandalams"]:
        for a in m["aadhayaa"]:
            for e in a["sukta"]:
                r = re.search(r"([०-९]+)\.([०-९]+)\.([०-९]+)", e["c"])
                if not r:
                    continue
                mn, sk, mt = (int(x.translate(_ASCII)) for x in r.groups())
                if mn == mandala and lo <= sk <= hi:
                    rows.append((sk, mt, e))
    rows.sort(key=lambda x: (x[0], x[1]))

    units, sidecar = {}, []
    for pos, (sk, mt, e) in enumerate(rows):
        body = re.sub(r"॥\s*[०-९\d\.]+\s*$", "", e["c"]).strip()
        text = [e["a"].strip(),
                f"{body}॥ {str(sk).translate(_DEVA)}/{str(mt).translate(_DEVA)}॥"]
        uid = str(uuid.uuid4())
        # Key order and content_type mirror the files the recorder already eats
        # (adhyaya_02.json, anuvyakhyana_part1_by_shloka.json): every one of them uses
        # "Sarvamula" and puts is_padya before text. "Mula" is the truthful label for a
        # Ṛgveda mantra, but the recorder is the consumer here and it has only ever been
        # fed Sarvamula — the mantra's real identity is carried by the sidecar index.
        units[uid] = [{"content_type": ctype, "is_padya": True, "text": text}]
        sidecar.append({"id": uid, "pos": pos, "content_type": "Mula", "recorded": True,
                        "rigveda_ref": f"{mandala}.{sk:03d}.{mt:02d}", "sukta": sk,
                        "mantra": mt, "n_lines": len(text),
                        "aksharas": sum(len(re.findall(r"[ऀ-ॿ]", l)) for l in text)})
    return {"title": title, "content": units}, sidecar, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None)
    ap.add_argument("--db-work", default=None,
                    help="read the work straight from sarvamula.db instead of a source file")
    ap.add_argument("--content-type", default="Sarvamula",
                    help="content_type the recorder expects (default Sarvamula)")
    ap.add_argument("--rigveda-range", default=None,
                    help="M:LO-HI, e.g. 1:1-40 — emit the Veda directly, ignoring --src")
    ap.add_argument("--rigveda", default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--only", default="",
                    help="comma-separated content_types to KEEP (e.g. Mula) — the rest are "
                         "left to TTS and never reach the recording script")
    ap.add_argument("--out", required=True)
    ap.add_argument("--index", default=None)
    ap.add_argument("--verify-against", default=None,
                    help="a known-good by_shloka file; assert the grouping matches")
    a = ap.parse_args()

    if a.rigveda_range:
        m, rng = a.rigveda_range.split(":"); lo, hi = rng.split("-")
        doc, sidecar, rows = from_rigveda(a.rigveda, int(m), int(lo), int(hi),
                                          a.title or "rgveda", a.content_type)
        seen = {(r[0], r[1]) for r in rows}
        json.dump(doc, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if a.index:
            json.dump(sidecar, open(a.index, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        aks = sum(x["aksharas"] for x in sidecar)
        print(f"maṇḍala {m}, suktas {lo}-{hi}: {len(doc['content'])} mantras "
              f"({len(seen)} distinct refs, {aks:,} akṣaras)")
        print(f"-> {a.out}   (~{aks*0.2395/60:.0f} min at chant pace)")
        return

    only = set(x.strip() for x in a.only.split(",") if x.strip()) or None
    if a.db_work:
        import tempfile
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(from_db(a.db_work), tmp, ensure_ascii=False); tmp.close()
        a.src = tmp.name
    doc, sidecar, st = build(a.src, a.rigveda, a.title, only)

    assert st["lines_in"] == st["lines_out"], \
        f"LINE COUNT CHANGED {st['lines_in']} -> {st['lines_out']} — refusing to write"

    if a.verify_against:
        want = json.load(open(a.verify_against, encoding="utf-8"))["content"]
        got = [p["text"] for v in doc["content"].values() for p in v]
        exp = [p["text"] for v in want.values() for p in v]
        same = got == exp
        print(f"VERIFY against {os.path.basename(a.verify_against)}: "
              f"{len(got)} vs {len(exp)} units — {'IDENTICAL' if same else 'DIFFERS'}")
        if not same:
            for i, (x, y) in enumerate(zip(got, exp)):
                if x != y:
                    print(f"  first divergence at unit {i}:\n    got {x}\n    exp {y}"); break
        return

    json.dump(doc, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if a.index:
        json.dump(sidecar, open(a.index, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{st['units_in']} source units -> {st['units_out']} recording blocks "
          f"({st['lines_in']} lines preserved exactly)")
    if st["dropped"]:
        print(f"dropped {st['dropped']} line(s) with nothing recitable (stray daṇḍa / lacuna mark)")
    if st["skipped"]:
        print(f"left to TTS: {st['skipped']} blocks ({', '.join(sorted(ALL_TYPES - (only or set())))})")
    if st["mula"]:
        print(f"mantras: {st['resourced']}/{st['mula']} re-sourced from the Ṛgveda, "
              f"{st['drift']} differed in svara, {len(st['unmatched'])} unmatched")
        for u in st["unmatched"][:5]:
            print("   UNMATCHED:", u)
    est = sum(s["aksharas"] for s in sidecar if s["recorded"]) * 0.2395 / 60
    print(f"-> {a.out}   (~{est:.0f} min at chant pace)")


if __name__ == "__main__":
    main()
