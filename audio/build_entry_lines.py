#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recover the EDITION's line breaks for every entry and write them as a sidecar.

Why this exists
---------------
The source JSONs store each record's text as a LIST — one element per printed line,
which for verse is one hemistich:

    "text": ["ईरपादास्ततः प्रोक्तास्ते त्रयो विष्णुमत्यजन्।",
             "पराभूतास्ततस्ते तु तमस्यन्धे निपातिताः।", …]

The import joins that list into a single `entries.text_dev` string, so the line
structure is DESTROYED before the segmenter ever sees it. The segmenter therefore
re-derives pāda boundaries from visargas and length — and cuts inside hemistichs:
`कर्मभिः ।` / `शुद्धसत्त्वानां कर्मत्यागोऽपि नान्यथा ।` where the edition has one line.
Worse, whether that happens depends on `is_padya`, which is unreliable (it marks
entries that CONTAIN verse), so ait_seq9's ślokas are typed `gadya` and get the
prose visarga treatment.

Rather than re-import the corpus, recover the boundaries by alignment: reduce both
the source lines and `text_dev` to bare letters (dropping daṇḍas, digits, spaces and
the punctuation the import normalises) and locate each entry inside its work's
letter stream. The cumulative lengths of the source lines are the legal break
offsets; the ones interior to an entry are that entry's line structure.

Output: {"<work>|<seq>": [cut, cut, …]} — cut = letter offset into k(text_dev).
An entry with no interior cut is a single edition line.

Entries whose letters are not found verbatim in the stream are REPORTED, not
guessed at: those recite mūla from a different book (upaniṣad text, Ṛgveda
mantras) that is not in this work's JSON.
"""
import json, os, sys, bisect, collections, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# daṇḍas and digits are dropped: the edition punctuates a line end with ।, and the
# import may or may not carry it, so it cannot take part in the alignment key.
DROP = set('।॥*0123456789०१२३४५६७८९')
LETTER = lambda ch: 'ऀ' <= ch <= 'ॿ' and ch not in DROP
# what the edition prints at a real line end. '*' marks a lacuna and closes a line too.
TERMINAL = ('।', '॥', '*', '’', '”', '"', "'", ',', ';', ':', '?', '!', '-', '–', '—')


def bare(s):
    return ''.join(ch for ch in (s or '') if LETTER(ch))


def source_lines(path):
    """Every printed line of a work, in document order — as (letters, ends_a_line).

    A `text` element is NOT always an edition line. The extraction turned the original
    document's VISUAL WRAPPING into separate elements, so one hemistich can arrive in
    pieces:

        [147] 'उपासते'            [148] 'महाविष्णुं'      [149] 'परमात्मानमच्युतम्।'

    which is a single anuṣṭubh line, 'उपासते महाविष्णुं परमात्मानमच्युतम्।'. Treating each
    piece as a line end made the segmenter PRESERVE those fragments — the reader saw
    'उपासते ।' / 'महाविष्णुं ।' on their own lines and the model voiced each as a finished
    sentence. A genuine line end carries the edition's own terminal mark (।, ॥, a closing
    quote, or the lacuna *); a wrap fragment ends bare. Only the former is a legal boundary.
    """
    d = json.load(open(path, encoding='utf-8'))
    out = []
    content = d.get('content')
    if not isinstance(content, dict):
        return out
    for v in content.values():
        for rec in (v if isinstance(v, list) else [v]):
            for t in rec.get('text', []):
                b = bare(t)
                if b:
                    out.append((b, t.rstrip().endswith(TERMINAL)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(ROOT, "web", "sarvamula.db"))
    ap.add_argument("--out", default=os.path.join(ROOT, "audio", "entry_lines.json"))
    ap.add_argument("--sources", default=ROOT, help="directory holding <work>.json")
    a = ap.parse_args()

    import sqlite3
    con = sqlite3.connect(a.db)
    works = [r[0] for r in con.execute("SELECT DISTINCT work FROM entries")]

    streams = {}
    for w in works:
        p = os.path.join(a.sources, w + ".json")
        if not os.path.exists(p):
            continue
        lines = source_lines(p)
        stream = ''.join(b for b, _ in lines)
        legal, off = [], 0
        for b, ends in lines:
            off += len(b)
            if ends:                 # a wrap fragment is NOT a boundary — see source_lines
                legal.append(off)
        if not legal or legal[-1] != len(stream):
            legal.append(len(stream))
        streams[w] = (stream, legal)

    out, stat = {}, collections.Counter()
    for w, seq, txt in con.execute("SELECT work, seq, text_dev FROM entries"):
        if w not in streams:
            stat[w + ':no-source'] += 1
            continue
        key = bare(txt)
        if not key:
            continue
        stream, legal = streams[w]
        i = stream.find(key)
        if i < 0:
            stat[w + ':unmatched'] += 1      # mūla from another book — reported, not guessed
            continue
        if stream.find(key, i + 1) >= 0:
            stat[w + ':ambiguous'] += 1      # a repeated passage; first occurrence is still
                                             # a correct line structure for it
        j = i + len(key)
        lo = bisect.bisect_right(legal, i)
        hi = bisect.bisect_left(legal, j)
        out[f"{w}|{seq}"] = [legal[x] - i for x in range(lo, hi)]
        stat[w + ':ok'] += 1

    json.dump(out, open(a.out, "w"), ensure_ascii=False)
    ok = sum(v for k, v in stat.items() if k.endswith(':ok'))
    print(f"entries with recovered line structure: {ok}  ->  {a.out}")
    for suffix in (':unmatched', ':ambiguous', ':no-source'):
        rows = sorted(((k.split(':')[0], v) for k, v in stat.items() if k.endswith(suffix)),
                      key=lambda x: -x[1])
        if rows:
            print(f"\n{suffix[1:]} ({sum(v for _, v in rows)}):")
            for w, n in rows[:12]:
                print(f"   {w:28s} {n}")


if __name__ == "__main__":
    main()
