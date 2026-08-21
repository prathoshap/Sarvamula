# Anveṣaṇa — Sarvamūla scholarly analytics & concept-locator — DESIGN PLAN

Design for a new in-app **Anveṣaṇa** (अन्वेषण, "inquiry") tab in the Sarvamūla reader.
Decided constraints (2026-07-28): **scholar / distant-reading audience · gold-data + surface only
(NO lemmatization) · lives in the reader app · offline, zero-CDN.** Status: PLAN (awaiting sign-off).

---

## 0. Guiding principles
- **Lead with editorial + structured gold data** (topics, `kutra` citations, refs) — zero NLP risk.
- **Surface, done honestly** — Sanskrit inflection is *suffixal*, so a **stem-substring** on our
  vowel-preserving `text_skel` already catches most inflected forms (`bheda`→bhedaḥ/bhedaṃ/bhedena…;
  validated: `beda`→509 loci, `taratamya`→65). Gaps = word-initial sandhi, compound-medial position,
  and true synonyms — handled by a **curated thesaurus**, not ML.
- **Everything deep-links** to `#/w/<work>/<chap>` and shows **exact refs + raw counts**.
- **Transparent**: label "surface form" vs "editorial topic" vs "curated"; the thesaurus is
  human-readable and editable (like `avyayas.json`).
- **Exportable**: any index → CSV/JSON (scholars want the data out).
- **Lazy**: analytics data loads only when the tab opens; the reader's initial load stays lean.

---

## 1. The five pillars (views under the Anveṣaṇa tab)

### Pillar 1 — Concept Locator (Padārtha-anveṣaṇa)  ← HEADLINE
Answers *"where all has Madhva discussed concept X across the 38 works?"* by fusing three signals:
1. **Editorial topics** (high precision) — match against the 1,741 topic-headings (भेद→96 topics,
   जीव→55…). These are Madhva's/editors' own concept tags.
2. **Surface text** (high recall) — stem-substring over `text_skel` (suffixal inflection ⇒ catches
   declensions/compounds).
3. **Pramāṇa loci** (for scripture-anchored concepts) — via the citation index (Pillar 2).

Plus a curated **Concept Thesaurus** (`concepts.json`, editable) mapping each concept →
`{ surface stems/synonyms, related topic strings, canonical pramāṇa loci, gloss }`. This is the
gold-data substitute for lemmatization: recall via hand-built synonym sets
(mokṣa≈mukti≈apavarga; bheda / pañca-bheda; tāratamya; sākṣī; bimba-pratibimba; viṣṇu-sarvottamatva;
vāyu-jīvottamatva; aparokṣa-jñāna; svarūpānanda; …). Seed ~50–100 core concepts; extensible.

Output for a concept:
- **Cross-work distribution** — a 38-work (and Bhāgavata skandha) **heatmap/bar** of loci counts
  ("discussed most in Anuvyākhyāna, then MBTN…"). This *is* the scholar's answer at a glance.
- **Grouped hit list** — by work → section, topic-hits flagged distinctly from text-hits, with
  snippets + deep-links + exact refs.
- **Free-text mode**: any query works immediately (topic+surface); the thesaurus just *boosts* recall
  when the query matches a curated concept (offered as "expand: also mukti, apavarga?").
- Export the loci table.

### Pillar 2 — Pramāṇa citation index & network (from `kutra`)
- Build: explode 632 `kutra` blocks → `citations(work, seq, source_canon, source_raw, ref)`
  (thousands of rows), each deep-linked to the citing verse.
- Views: **ranking** (which scriptures Madhva cites most, overall + per work); **network**
  (works ↔ sources force graph, edge = count); **co-citation** (sources quoted together in one block
  = argument clusters); **drill** (source → every instance w/ exact ref → jump to text).
- Crux: a curated **source registry** (`sources.json`) canonicalising ~50–100 raw labels
  (`भारतम्`=Mahābhārata, `महैतरेयोपनिषत्`=Mahā-Aitareya; strip dirty double-spaces). One-time table;
  I'll auto-draft it from the data for review.

### Pillar 3 — Topic treemap
- Zoomable hierarchy `work → section → heading levels → topic`; tiles deep-link. Uses existing
  headings only. Doubles as a visual entry into Pillar 1.

### Pillar 4 — Word & collocation clouds (surface)
- Build-time surface frequencies over ~408K tokens, avyaya-stripped (reuse `avyayas.json`), per-work
  + corpus; **n-gram collocations** scored by log-likelihood/PMI (surfaces epithets + pramāṇa
  formulae like *iti śruteḥ*). Each word deep-links to the concordance/search. Labeled "surface forms".

### Pillar 5 — Word co-occurrence network (surface)
- Words co-occurring within a verse/block → thresholded force graph ("dependency shower"). Surface
  caveat shown. Optional/last.

---

## 2. Data model & build pipeline
New **`build_analytics.py`** (beside `build_db.py`, reuses its `norm()` + `avyayas.json`) →
emits small JSON to **`web/analytics/`**, loaded on demand. Reader `sarvamula.db` stays unchanged.

| file | contents | source |
|---|---|---|
| `analytics/citations.json` | exploded `{work,seq,source,ref}` + deep-link | `kutra` |
| `analytics/sources.json` | curated canonical source registry | hand-curated (auto-drafted) |
| `analytics/topics.json` | heading hierarchy tree per work | headings |
| `analytics/concepts.json` | curated concept thesaurus (editable) | hand-curated (seeded) |
| `analytics/wordfreq.json` | per-work + corpus surface freq + collocations | `text_dev` tokens |
| `analytics/cooccur.json` | thresholded co-occurrence edges | tokens |

Concept-locator queries run **live in-app** against `sarvamula.db` (`text_skel` LIKE for surface,
topics table for editorial) — only the thesaurus/registry are precomputed. Citation/topic/word
data are precomputed (heavier). Total added payload target: a few MB, gzip-friendly, lazy-loaded.

---

## 3. UI / information architecture
- New **main tab "अन्वेषण / Anveṣaṇa"** (alongside the works home + search). Sub-nav:
  **Concept · Citations · Topics · Words · Network**. Concept Locator is the default.
- Shared chrome: per-work scope filter, exact refs, raw counts, **CSV/JSON export** button, deep-links.
- Rendering: **hand-rolled inline SVG**, offline, no libs — treemap (squarified ~40 lines), force
  graph (small sim), word cloud (spiral placement), distribution **heatmap** (grid). Matches the
  reader's zero-CDN ethos; theme-consistent with the existing palette.

---

## 4. Scholarly integrity
- Distinguish **editorial topic-hit** vs **surface text-hit** vs **curated-thesaurus expansion** in
  every result (different styling + a legend). Never present surface counts as lemma counts.
- Thesaurus & source registry are **visible and editable** (JSON), so a scholar can audit/extend the
  controlled vocabulary — the recall/precision knobs are in their hands.
- Known limits stated in-UI: sandhi-initial & compound-medial misses; synonyms only as curated.

---

## 5. Phasing
- **Phase A (headline value):** Concept Locator (topics + surface + seed thesaurus, cross-work
  heatmap, grouped hits, export) **+** Citation index (explode `kutra`, source registry, ranking +
  drill). These two answer the real scholar questions and need zero NLP.
- **Phase B:** Topic treemap + Word/collocation clouds.
- **Phase C:** Co-occurrence network + polish (co-citation network, heatmap refinements, exports).

Build the Anveṣaṇa tab shell once; add pillars into it phase by phase.

---

## 6. Open decisions to confirm before coding
1. **Tab name** — Anveṣaṇa (अन्वेषण) · Anusandhāna · Vimarśa · plain "Explore"? (headings transliterate per script)
2. **Storage** — JSON files in `web/analytics/` (proposed) vs extra tables in the DB.
3. **Thesaurus seeding** — how many core concepts should I pre-seed, and from what source
   (I can draft from the topic-headings + standard Madhva concept lists for your correction)?
4. **Source registry** — OK for me to auto-draft the canonical map from `kutra` for your review?
5. **First slice** — start with Concept Locator, or Citation index, or the tab shell + both together?
