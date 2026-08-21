# Sarvamūla — work so far (2026-07-22)

Summary of this session's work on the **Sarvamūla reader** (`/Users/prathosh/Sarvamula`) — the
multi-script web reader of Madhvācārya's complete 38 works. See `RESUME.md` for the living status
and the full build-pipeline spec.

Five things shipped, in order. Everything below is verified (node syntax + unit tests, SQLite
integrity, and in-browser screenshots on :8091).

---

## 1. Recovered the lost JSON→DB build pipeline  → `build_db.py`
The original builder that turns the 38 source `*.json` into `web/sarvamula.db` lived only in a
prior scratchpad and was gone — the DB was an orphan artifact with no way to reproduce it.

- Reverse-engineered every transform by diffing the shipped DB against the source JSONs and wrote
  **`build_db.py`**, which reproduces the DB **byte-for-content** (`--check` → "✅ EXACT MATCH",
  38 works / 26,164 entries).
- Transforms encoded: one block → one row in dict order; `seq` 0-based per work; `ord` alphabetical
  by slug; `text_dev = " ".join(text)`; `verse_end`/`needs_qc` dropped; `text_skel = fold(text_dev)`
  (mirrors app.js `fold()`, **plus** maps vocalic-ṛ `ॠ`/`ॄ`→r — the one quirk that took the diff
  from close to exact); kutra/variants/footnote = `json.dumps(…, ensure_ascii=False)`;
  `n_topics = count(Heading% ∪ {Subject, Title})`. Display `TITLES` map (not in the JSON) recovered
  and embedded.
- Commands: `build_db.py` (build), `--check` (regression vs shipped), `--raw` (original, no cleanup),
  `--diff-cleanup` (audit the cleanup delta).

## 2. Data cleanup — 8 junk `content_type` values fixed
The source JSONs carried 8 bad `content_type`s. Fixed via a `CT_FIXES` table in `build_db.py`, keyed
`(work, seq) → (expected_bad, corrected)` with the old value **asserted** (a data shift fails loudly):

| row | fix | reason |
|---|---|---|
| kanva_bhashya:61 | `Colopon_Mula` → `Colophon_Mula` | typo |
| kanva_bhashya:99 | `Colohon_Mula` → `Colophon_Mula` | typo |
| kanva_bhashya:79 | `श` → `Sarvamula` | corrupt; prose gloss in the Sarvamūla stream |
| mbtn:1042 | `` (empty) → `Colophon_Sarvamula` | stray `॥` closing a split colophon |
| sutra_bhashya:1114/1117/1194/1289 | `Yes` → `Sarvamula` | pramāṇa `Yes` flag leaked into the type cell |

- `--diff-cleanup` proves the cleanup touches **exactly these 8 rows, content_type only** (no
  `n_topics`/`n_padya`/`n_blocks` change). They now render correctly (colophons → `.colo`; the four
  `Yes` quotes are `pramana=1` → green `.v.pram` blocks).
- Source JSONs left pristine (fixes live only in the builder; `--raw` still reproduces the original).
- Rebuilt DB also **shrank 23.6 MB → 18.4 MB** — a fresh compact build vs the original's page
  fragmentation; content otherwise identical. `PRAGMA integrity_check` → `ok`.

## 3. Reader layout fix + font-size control  → `web/index.html`, `web/app.js`
The side rails were starving the reading column (root cause: `.wrap` capped at 820px while the two
rails were fixed 230+248px → reader ~265px at ~900px viewports).

- `.wrap` max-width **820 → 1360px**; rails narrowed (nav 230→210, toc 248→230); base font 18→19px.
- `.reader` `max-width:760px; margin-inline:auto` → caps the line measure on wide screens and
  **centers** the reader in leftover space (add-on: ultrawide measure cap).
- Breakpoints retuned: **≤1100px** drops the redundant right Topics rail → nav+reader two-column;
  **≤820px** collapses to single column (nav = short scroll strip on top).
- **Reading font-size control** (add-on): topbar **A− / A+** drive CSS var `--read` (base text +
  mūla `calc(var(--read)*1.07)`), clamped 15–28px, persisted `localStorage['sv_read']`.
- Result: reader ~265px → ~630px at ~900px; ~670px measure at 1440px. Verified in Chrome.

## 4. Verse (śloka) line-splitting  → `web/app.js`, `web/index.html`
Verse blocks used to render as one run-on paragraph. Now **each pāda sits on its own line** and each
**śloka gets breathing room** (traditional layout).

- `verseLines(dev)` splits the Devanāgarī `text_dev` on daṇḍa runs **before** `disp()` (so it's
  script-independent), handling every śloka-end marker in the data: `॥ १ ॥`, `॥ *॥`, `॥ १/१/१॥`,
  and **lone unnumbered `॥`**. A line ending in `॥` is flagged a śloka boundary (`.pe` → margin).
- `verseHTML()` renders `<span class="pada">` lines; applied **only** when `r.is_padya` (prose,
  colophons, DB, and search untouched).
- Verified with a node unit test on all three marker styles + in Chrome (Dvādaśa Stotra).
- Known minor trade-off: a `‘…’` pramāṇa quote spanning multiple pādas loses its green highlight
  (markup runs per line); rare, non-breaking. Went with pāda-per-line (2 lines/śloka); switching to
  strictly one-line-per-śloka (break only at `॥`) is a one-line tweak.

## 5. Search pagination  → `web/app.js`, `web/index.html`
Search was a flat `LIMIT 300` dump; now **paginated 25/page** with **‹ Prev / Next ›** buttons.

- `renderSearch(term, page)` runs a `COUNT(*)` for the true total, then `LIMIT ? OFFSET ?`; status
  shows `from–to of total`. Pager (`.pager`) rendered above and below the hits with a `page / total`
  indicator; `searchGo(±1)` clamps and scrolls up; typing resets to page 1.
- Now surfaces **all** matches (previously anything past 300 was invisible).
- Verified in Chrome: "hari" → 4722 hits / 189 pages, Prev disabled on p1 & enabled on p2.

## 6. Search precision — vowel-preserving norm + exact-phrase toggle  → `build_db.py`, `web/app.js`, `web/index.html`
Search used a consonant-**skeleton** that dropped all vowels, so `hari`, `hara`, and हार collapsed to
one key ("hr") — "hari" returned 4722 mostly-irrelevant hits. Replaced it with a **vowel-preserving
`norm()`**.

- Keeps vowels (long→short); still folds tolerance classes (aspirates kh=k, retroflex/dental ṭ=t,
  sibilants ś=ṣ=s); drops anusvāra/visarga. **Vocalic-ṛ → "ri"** so `कृष्ण`/`kṛṣṇa`/`krishna` still
  unify to `krisna`. Devanāgarī handled **syllable-aware** (implicit-a). Result: "hari" **4722 → 1254**
  precise hits, no longer conflated with हर/हार.
- `norm()` lives in both `build_db.py` (builds `text_skel`) and `web/app.js` (query) — **verified
  byte-identical on 6000 corpus words**. `text_skel` rebuilt (26,162 rows changed; everything else
  identical; integrity ok; `--check` still ✅).
- **Exact-phrase toggle:** wrap in `"quotes"` → one contiguous ordered match; status shows
  `· exact phrase`. E.g. `"bhagavan vyasa"` → 6 contiguous vs 48 any-order. Verified in Chrome.
- Note: this DB no longer reproduces the pre-2026-07-22 *original* (text_skel + content_type fixes
  intentionally differ); it does reproduce the current shipped DB (`--check`).

## 7. Home grouped by prasthāna — 2026-07-28  → `web/app.js`, `web/index.html`
Home page was a flat grid sorted by block count; now the 38 works are **grouped under the 9
prasthāna categories** from anandamakaranda.in/Main_Page, with Devanāgarī group titles (transliterated
per the script selector) + English gloss + count. Verified in Chrome; all 38 covered (no dupes/orphans).
- Groups: Gītā 2 · Sūtra 4 · Upaniṣat 10 · Śruti 1 · Itihāsa 2 · Purāṇa 1 · Daśaprakaraṇa 10 ·
  Stotra 2 · Ācāra 6.
- Confirmed placements: `sangraha_bhashya`=Anubhāṣya (Sūtra); `atharvana_bhashya`=Muṇḍaka;
  `parishishta`=Pariśiṣṭa stotra-bundle (Stotra); `nyasa_paddhati`=Nyāsapaddhati (Ācāra).
- We lack 5 works the site lists (standalone Nakha/Kanduka + 3 Svatantra granthas) → Svatantra omitted.

## 8. Anusandhāna analytics tab (all 5 pillars) — 2026-07-28  → `build_analytics.py`, `web/anusandhana.js`, `web/analytics/*.json`, app.js/index.html
Scholar-facing distant-reading tab, in-app, offline, gold-data + surface (no lemmatization). Design in
`ANVESHANA_PLAN.md`. New `build_analytics.py` precomputes `web/analytics/*.json` (~810 KB, lazy-loaded,
bundle-able): citations(2167 instances, curated source registry ~95% canonicalised), per-work topic
trees, 25 seeded editable concepts, surface word freq + log-likelihood collocations, co-occurrence.
Module `anusandhana.js` renders 5 views in hand-rolled inline SVG; header link **अनुसन्धान**;
new `#/b/<slug>/<seq>` deep-link route. Verified in Chrome:
- **Concept locator** (headline): "where all does Madhva discuss X" → cross-work distribution bars +
  editorial-topic hits + text loci, deep-linked (तारतम्य → 65 loci / 18 works). Works great.
- **Citations**: category-colored ranking (Ṛgveda 274, Chāndogya 255…) + drill + works↔sources network.
- **Topics**: squarified treemap per work. **Words**: freq cloud + collocations (श्रीशुक उवाच 375…).
- **Network**: co-occurrence force graph — **PMI-sparsified** (significant edges only) + fit-to-viewport
  layout (clean organic graph, no wall-clumping).

**Polish pass (2026-07-28):** PMI-sparsified the network + rescale-to-fit layout (fixed the perimeter
ring); treemap switched to direct-span weighting (fixed strip-y tiles); source registry 99→55
(variants/typos folded, other-bucket 5.6%→3.9%); concept seed 25→46. All re-verified in Chrome.

---

## Files touched
- `build_db.py` — **new**, the recovered + cleanup-aware builder.
- `web/sarvamula.db` — rebuilt (cleaned, 18.4 MB).
- `web/app.js` — verse splitter, search pagination, font-size control.
- `web/index.html` — responsive layout, font control UI, verse + pager CSS.
- `RESUME.md` — updated with all of the above.

## Testing / how to run
- Rebuild DB: `python3 build_db.py` · verify: `python3 build_db.py --check`
- Run web app: `cd web && python3 serve.py 8080` (sends `no-store`; **full reload** to pick up JS
  changes — a `#/…` hash change alone does NOT reload `app.js`).

## Not done yet (candidates)
1. Feature-up the reader (port Bhāgavata-VāNi extras: bookmarks, deep-links, verse share, etc.).
2. Ship as an app (Capacitor → Android/iOS), mirroring Bhāgavata-VāNi.
3. Deeper data QC (e.g. the split/incomplete `mbtn:1041` colophon; heading levels; danda-only blocks).

## 9. Anusandhāna — trimmed to Concept + Citations, then deepened — 2026-07-28
Per user feedback, trimmed the analytics tab to the two scholarly-useful views (Concept locator +
Citations); dropped the treemap/word-cloud/network from the UI (payload 810→235 KB, then grew with #3).
Then built the three requested enhancements:
1. **Complete pramāṇa index** — the citation index only read `kutra`, so untagged inline “…” quotations
   (e.g. all through Brahmasūtra Bhāṣya) were invisible. build_citations now emits kutra sources AND
   inline quotes (attributed by position; rest `(unattributed)`, quote text kept). **2167 → 5067**
   citations; sutra_bhashya 497 → 1168. Drill now shows ref + quote text + work.
2. **Concept → Pramāṇa** — concept locator shows "Pramāṇas cited here": scriptures Madhva cites in/near
   a concept's loci (tāratamya → Ṛgveda 57, Gītā 28), deep-linked.
3. **See-all + CSV export** — concept loci fully paginated (25/page) + Export CSV; citation drill CSV.
All verified in Chrome.

## 10. Inline pramāṇa-attribution extraction — 2026-07-28
The big "(unattributed)" bucket existed because Madhva names many sources in his OWN prose
(`“…” इति ब्रह्मतर्के`) rather than in the `kutra` tag. build_analytics now reads these via a curated,
gated `INLINE_LEX` (locative→canonical; prose noise like हि/वचनात्/चेत् ignored). **620 attributions
recovered; unattributed 2900→2280.** Surfaced sources known chiefly through Madhva's citations —
**Brahmatarka (53), Śabdanirṇaya (53)**, several purāṇas, and named śrutis (Paiṅgi/Kauṇḍinya/Bhāllaveya/
Nārāyaṇa). New categories tantra/shruti; bare श्रुतेः/स्मृतेः → "(unnamed)" buckets. Combined into the
single ranking (per user); inline-derived rows carry `via:'inline'`, shown as a gold † in the drill.
Spot-checked accurate (every † is `इति <Src>` right after its quote). Verified in Chrome.

## 11. Unattributed reduction — 3 levers — 2026-07-28
Diagnosed the 2280 unattributed: ~65% "extra" quotes in kutra-tagged blocks (many = more verses from
the SAME source, or non-scriptural dhātu spans over-captured), ~20% genuinely no source cue, ~14% a
named source not yet in the lexicon. Applied all three fixes in build_analytics:
① **single-source block inheritance** — extra quotes in a block whose kutra all maps to ONE canonical
text inherit it (`via:'block'`, ‡; 427 recovered, 100% consistent). ② **grammatical filter** (drops
dhātu-pāṭha root-glosses / single akṣaras; conservative so mahāvākyas survive). ③ **lexicon tail**
(Kauṇṭharava-śruti, Nārāyaṇa-tantra, Brahmasāra, Sattattva…). **Unattributed 2900 → 1783.** Provenance
markers in the drill: † inline (from prose), ‡ block-inherited. Residual is honest (multi-source
ambiguity + genuinely uncued). Verified in Chrome.
