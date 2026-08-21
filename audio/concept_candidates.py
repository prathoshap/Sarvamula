#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Propose synonym candidates for a concept FROM THE CORPUS ITSELF — no model, no network.

Why not embeddings: a multilingual encoder would have to run on the reader's device (100+ MB
against an 11 MB database) or behind a server, and its notion of "similar" blurs exactly the
distinctions this corpus turns on — the nearest neighbour of भेद is अभेद, the doctrine Madhva
spends the corpus refuting. So similarity is measured distributionally instead: a term that
keeps company with the seed terms, across 29k entries, in the author's own usage.

Scoring is log-likelihood-ratio style association, not raw co-occurrence: frequent words
(च, तु, हि, एव) co-occur with everything and would otherwise dominate. A candidate scores well
only if it appears with the seed FAR more often than its own overall frequency predicts.

The output is a PROPOSAL for a scholar to accept or reject — the terms that survive become
plain synonym lists in web/analytics/concepts.json, and retrieval stays lexical: offline,
instant, and explainable ("matched चरण + महिम"), which matters when a user may cite the result.

  concept_candidates.py --seed पाद --seed चरण --with महिम
  concept_candidates.py --seed तारतम्य --top 40
"""
import argparse, collections, json, math, os, re, sqlite3, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "web", "sarvamula.db")

# NOT [ऀ-ॿ]: the daṇḍa (U+0964), double daṇḍa and Devanāgarī digits all live inside that block,
# so 'च।' came through as a single word and punctuation dominated the candidate list.
DEVA = re.compile(r'[ऀ-ॿ--[।॥०-९]]+') if False else re.compile(r'[\u0900-\u0963\u0966-\u097f]+')
# Function words and inflectional debris: they co-occur with everything, carry no topical
# signal, and would crowd out real candidates however the score is normalised.
STOP = set("""च तु हि एव न ते स सा तत् तस्य तेन इति अपि वा यत् यः या ये अथ अत अतः ततः यथा तथा
किम् कः का सः अयम् इदम् एतत् एषा असौ अस्य अस्मिन् तस्मिन् तस्मात् यस्य यस्मिन् सर्व सर्वे सर्वं
भवति भवन्ति अस्ति सन्ति उक्तम् उक्ता उक्तः इत्यादि आदि एवम् किञ्चित् नहि यदि चेत् तर्हि""".split())


def words(text):
    for w in DEVA.findall(text or ''):
        w = w.strip('ऽ')
        if len(w) >= 2 and w not in STOP:
            yield w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--seed", action="append", required=True,
                    help="a term the concept is already known by (repeatable)")
    ap.add_argument("--with", dest="also", action="append", default=[],
                    help="require this term too, i.e. the second AND-group (repeatable)")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--min-count", type=int, default=3)
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    rows = con.execute("SELECT work, seq, text_dev FROM entries").fetchall()
    N = len(rows)

    df = collections.Counter()                     # entries containing each word
    hit_df = collections.Counter()                 # entries in the seed set containing each word
    seeds, alsos, hits = a.seed, a.also, []
    for w, seq, t in rows:
        ws = set(words(t))
        for x in ws:
            df[x] += 1
        in_seed = any(any(s in x for x in ws) for s in seeds)
        if in_seed and alsos:
            in_seed = all(any(al in x for x in ws) for al in alsos)
        if in_seed:
            hits.append((w, seq))
            for x in ws:
                hit_df[x] += 1
    H = len(hits)
    if not H:
        sys.exit("no entries matched the seed terms")

    # association: how much more often does the candidate appear here than corpus-wide
    scored = []
    for x, c in hit_df.items():
        if c < a.min_count or any(s in x for s in seeds) or any(al in x for al in alsos):
            continue
        p_here, p_all = c / H, df[x] / N
        if p_here <= p_all:
            continue
        lift = p_here / p_all
        scored.append((c * math.log(lift), c, df[x], lift, x))
    scored.sort(reverse=True)

    print(f"seed={seeds} with={alsos}")
    print(f"entries in the seed set: {H} of {N}\n")
    print(f"{'candidate':22s} {'in set':>7s} {'corpus':>7s} {'lift':>6s}")
    for _, c, d, lift, x in scored[:a.top]:
        print(f"  {x:20s} {c:7d} {d:7d} {lift:6.1f}")
    print("\nSuggested concept entry (edit the lists, then paste into concepts.json):")
    top = [x for _, _, _, _, x in scored[:8]]
    print(json.dumps({"id": "TODO", "dev": seeds[0], "iast": "TODO", "gloss": "TODO",
                      "terms": seeds, "topics": alsos or seeds,
                      "all": [seeds + top[:4]] + ([alsos] if alsos else []),
                      "not": []}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
