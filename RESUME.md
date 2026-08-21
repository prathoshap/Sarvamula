# Sarvamūla reader — RESUME / status

Read this first when resuming the **Sarvamūla** project (`/Users/prathosh/Sarvamula`).
Sibling of the Bhāgavata-VāNi app; this one presents **Madhvācārya's complete 38 works**
(Sarvamūla-grantha) as a multi-script web reader.

## What exists
- **Data:** 38 source `*.json` at repo root, one per work (e.g. `sutra_bhashya.json`,
  `bhagavata_tatparya.json`). Each = `{"title": <code>, "content": { <uuid>: [ <block> ] }}`;
  `content` is an ORDERED dict, uuid → single-element list of a block dict.
  Block fields: `content_type, text[lines], is_padya, heading_level, pramana,
  skandha, adhyaya, verse, verse_end, needs_qc, kutra[], variants[], footnote[]`.
- **Built DB:** `web/sarvamula.db` (SQLite, 23.6 MB) — tables `works(38)` + `entries(26164)`.
- **Web reader:** `web/{index.html,app.js,normalize.js,serve.py,sql-wasm.*}` — sql.js loads the
  DB client-side. Multi-script (Deva/IAST/kn/te/ta/ml/bn/gu via `BhagDisplay` in normalize.js),
  all-script `text_skel LIKE` search, work → chapter navigator + topic outline rail,
  mūla/tātparya/pramāṇa styling, variant readings. Run: `cd web && python3 serve.py 8080`.

## BUILD PIPELINE — RECOVERED 2026-07-21  ← this session
The original JSON→DB builder lived only in a scratchpad and was lost; `sarvamula.db` was an
orphan artifact. **`build_db.py` (repo root) reverse-engineers it and reproduces the shipped
DB byte-for-content** — verified: `python3 build_db.py --check` → "✅ EXACT MATCH".
- `python3 build_db.py`         → rebuild `web/sarvamula.db` from the 38 JSONs
- `python3 build_db.py --check` → build to a temp DB and diff every row/aggregate vs shipped

Commands:
- `python3 build_db.py`               → rebuild `web/sarvamula.db` WITH cleanup (canonical)
- `python3 build_db.py --raw`         → rebuild WITHOUT cleanup (reproduces the ORIGINAL DB)
- `python3 build_db.py --check`       → clean build == shipped DB? (regression guard) → EXACT MATCH
- `python3 build_db.py --diff-cleanup`→ audit: show the raw→clean delta (the CT_FIXES rows)

Transforms it encodes (all verified against the shipped DB):
- One block → one `entries` row, in dict-iteration order; `seq` 0-based, resets per work.
  Works ordered `ord` = alphabetical index by slug (0..37). `work` = filename stem.
- `text_dev = " ".join(block.text)`. `verse_end` and `needs_qc` are **dropped** (no columns).
- `is_padya`/`pramana` = `int(bool(...))`, absent → 0. `heading_level`/`skandha`/`adhyaya`/
  `verse` stored directly, absent → NULL. `kutra`/`variants`/`footnote` = `json.dumps(list,
  ensure_ascii=False)`, absent → NULL.
- `text_skel` = `fold(text_dev)` — Devanāgarī consonant-skeleton (aspirate-stripped ascii base,
  vowels/mātrās/virāma/avagraha/anusvāra/visarga/digits dropped, whitespace+daṇḍa → space).
  **Mirrors `fold()` in `web/app.js` EXCEPT the builder also maps `ॠ`/`ॄ` (vocalic-ṛ forms) → r**
  (app.js CONS omits them — a minor, harmless build↔runtime skew; kept for exact reproduction).
- Works aggregates: `n_blocks` = row count; `n_padya` = Σ`is_padya`;
  `n_topics` = count(`content_type LIKE 'Heading%'` OR in `{Subject, Title}`).
  (Note: `Adhyaya_Heading`/`Skandha_Heading`/`Subheading` deliberately do NOT count as topics.)
- Display `TITLES` map (slug→nice title) is **not in the JSON** (its `title` is a short code);
  it was hand-curated and is embedded in `build_db.py`, recovered from the shipped DB.

## Data cleanup — DONE 2026-07-22  ← this session
The source JSONs carried 8 junk `content_type` values; all fixed via `CT_FIXES` in `build_db.py`
(a `(work, seq) → (expected_bad, corrected)` table, asserted so a data shift fails loudly). Fixes:
- `kanva_bhashya:61` `Colopon_Mula` → `Colophon_Mula`   (typo)
- `kanva_bhashya:99` `Colohon_Mula` → `Colophon_Mula`   (typo)
- `kanva_bhashya:79` `श` → `Sarvamula`                   (corrupt; prose gloss in the Sarvamūla stream)
- `mbtn:1042` `` (empty) → `Colophon_Sarvamula`          (stray `॥` closing the split colophon at seq 1041)
- `sutra_bhashya:1114/1117/1194/1289` `Yes` → `Sarvamula` (pramāṇa `Yes` flag leaked into the type cell)

Proven (`--diff-cleanup`) to touch **exactly these 8 rows, content_type only** — no aggregate
(`n_topics`/`n_padya`/`n_blocks`) changes. They now render correctly (colophons → `.colo`; the four
`Yes` quotes are `pramana=1` → green `.v.pram` blocks). Source JSONs left pristine (fixes live in the
builder; `--raw` still reproduces the original). **Rebuilt `web/sarvamula.db` also shrank 23.6 MB →
18.4 MB** — a fresh compact build vs the original's page fragmentation; content otherwise identical.
`_backup_pre_setutila_20260721/` holds the pre-session JSONs; original DB backed up to this
session's scratchpad (`sarvamula.orig.db`).

## Reader layout + font control — 2026-07-22 (web/index.html, web/app.js)
Fixed the "side rails eat the space, reading text tiny" problem (root cause: `.wrap` capped at
820px while the two rails were fixed 230+248px → reader starved to ~265px at ~900px viewports).
- `.wrap` max-width 820 → **1360px**; rails narrowed (nav 230→210, toc 248→230); base font 18→19px.
- `.reader` now `max-width:760px; margin-inline:auto` → caps the line measure on wide screens and
  **centers** the reader in leftover space (verified in-browser: clean centering, no gap).
- Breakpoints retuned: **≤1100px** drops the right Topics rail (redundant) → nav+reader two-column
  (reader cap bumps to 820); **≤820px** collapses to single column (nav = short scroll strip on top).
- **Reading font-size control** (add-on): topbar `A− / A+` buttons drive CSS var `--read`
  (`.v .body` + mūla `calc(var(--read)*1.07)`), clamped 15–28px, persisted `localStorage['sv_read']`,
  applied before first render. Verified working in Chrome.

## Verse (śloka) line-splitting — 2026-07-22 (web/app.js, web/index.html)
Verse blocks used to render as one run-on paragraph (ślokas ran into each other). Now each
**pāda sits on its own line** and each **śloka gets breathing room**. Display-only — DB/search
untouched. `verseLines(dev)` splits the Devanāgarī `text_dev` on daṇḍa runs (BEFORE `disp()`, so
it's script-independent), handling every śloka-end marker seen in the data: `॥ १ ॥`, `॥ *॥`,
`॥ १/१/१॥`, and **lone unnumbered `॥`** (appended stotras). A line ending in `॥` is flagged a
śloka boundary (`.pe` → `margin-bottom`). `verseHTML()` renders `<span class="pada">` lines; only
applied when `r.is_padya` (prose/colophons unchanged). Verified in Chrome + a node unit test on all
three marker styles. Minor known trade-off: a `‘…’` pramāṇa quote that spans multiple pādas loses
its green highlight (mk() runs per line); rare, non-breaking. NOTE for edits: the Edit tool balked
on the sentinel line — `verseLines` was patched via python and uses `String.fromCharCode`-style
`` sentinel + `।`/`॥` (।/॥) in the regex; a hash-only `#/…` nav does NOT reload
app.js (test with a full reload / cache-bust query).

## Search pagination — 2026-07-22 (web/app.js, web/index.html)
Search was a flat `LIMIT 300` dump; now paginated **25/page** with **‹ Prev / Next ›** buttons
(rendered above and below the hits, `.pager`). `renderSearch(term,page)` runs a `COUNT(*)` for the
total, then `LIMIT ? OFFSET ?`; status shows `from–to of total`. Module state `searchTerm/
searchToks/searchTotal/searchPage`; `searchGo(±1)` clamps to `[0,pages-1]` and scrolls up. Typing
in the box resets to page 0 (live, debounced). Verified in Chrome (e.g. "hari" → 4722 hits, 189
pages, Prev disabled on p1 / enabled on p2). Search is input-driven, NOT hash-routed — paging state
is in memory, so a reload restarts the search (fine; the query box is re-typed anyway).

## Search precision — vowel-preserving norm + exact-phrase toggle — 2026-07-22
Replaced the old consonant-**skeleton** fold (which dropped ALL vowels → `hari`=`hara`=`हार`, so
"hari" returned 4722 mostly-junk hits) with a **vowel-preserving `norm()`**:
- Keeps vowels (long→short); still folds the tolerance classes: aspirates (kh=k), retroflex/dental
  (ṭ=t, ḍ=d), sibilants (ś=ṣ=s); drops anusvāra/visarga/avagraha. **Vocalic-ṛ → "ri"** so
  `कृष्ण` / `kṛṣṇa` / `krishna` all still unify to `krisna`. Devanāgarī handled **syllable-aware**
  (implicit-a). Result: "hari" → 1254 precise hits, no longer conflated with हर/हार.
- `norm()` lives in BOTH `build_db.py` (Python, builds `text_skel`) and `web/app.js` (JS, normalizes
  the query). **They MUST stay byte-identical** — verified equal on 6000 corpus words (node test).
- **`text_skel` rebuilt** (26,162/26,164 rows changed; text_dev/content_type/aggregates untouched;
  integrity ok). `build_db.py --check` still ✅ EXACT MATCH vs the shipped DB. Note: the DB no longer
  reproduces the *pre-2026-07-22 original* (text_skel + the 8 content_type fixes intentionally differ).
- **Exact-phrase toggle:** wrap the query in `"quotes"` (straight or curly) → one contiguous,
  ordered `LIKE '%normphrase%'` instead of AND-of-words. Status shows `· exact phrase`. E.g.
  `"bhagavan vyasa"` → 6 contiguous vs 48 any-order. Placeholder hints it. Verified in Chrome.
- Known limits (same as before or better): query input in Kannada/Telugu/etc. still isn't
  transliterated (only Devanāgarī + Latin/IAST); anusvāra-as-`m` naive spellings (`samsara`) don't
  match the Devanāgarī (which drops it) — an accepted tolerance trade-off.

## Home grouped by prasthāna (anandamakaranda.in) — 2026-07-28 (web/app.js, web/index.html)
Home was a flat grid sorted by block count; now the 38 works are **grouped under the 9 prasthāna
categories** from anandamakaranda.in/Main_Page. `GROUPS` in app.js = `[devTitle, english, [slugs
in order]]`; `renderHome()` renders a `.grouphd` (Devanāgarī title via `disp()` so it follows the
script selector + English gloss + count) then that group's `.wcard` grid. A safety "Other" bucket
catches any uncategorised slug (currently none). Verified in Chrome; all 38 covered, no dupes/orphans.
Groups (count): Gītā 2 · Sūtra 4 · Upaniṣat 10 · Śruti 1 · Itihāsa 2 · Purāṇa 1 · Daśaprakaraṇa 10 ·
Stotra 2 · Ācāra 6. Non-obvious placements (confirmed by colophons / with the user):
- `sangraha_bhashya` = **Anubhāṣya** (Brahmasūtra-saṅgraha-bhāṣya) → Sūtra Prasthāna (4th).
- Upaniṣat mapping: `atharvana_bhashya`=Muṇḍaka (Ātharvaṇa), `kanva_bhashya`=Bṛhadāraṇyaka,
  `talavakara_bhashya`=Kena, `kathaka_bhashya`=Kaṭha, `shatprashna_bhashya`=Praśna.
- `parishishta` = the Pariśiṣṭa bundle (holds Nakhastuti + Kandukastuti + misc) → Stotra Granthāḥ.
- `nyasa_paddhati` (Nyāsapaddhati, yati-conduct) → Ācāra Granthāḥ (alongside Yatipraṇavakalpa).
- We LACK 5 works the site lists (Nakha/Kanduka as standalone, and the 3 Svatantra granthas
  Padyamālā/Pramāṇapaddhati/Vādāvali) → the Svatantra category is omitted (empty).

## Anusandhāna analytics tab — 2026-07-28 (build_analytics.py, web/anusandhana.js, +app.js/index.html)
Scholar-facing analytics, in-app, offline, gold-data + surface (NO lemmatization).
**2026-07-28: trimmed to the 2 useful views — Concept locator + Citations** (per user; the treemap/
word-cloud/co-occurrence pillars were texture, not scholarly tools). Their build funcs
(build_topics/wordfreq/cooccur) stay defined in build_analytics.py but are NOT emitted; UI loads only
citations/sources/concepts (~235 KB). To restore a dropped view: re-add to `VIEWS`/`load` in
anusandhana.js + re-enable its dump in build_analytics.main().
See `ANVESHANA_PLAN.md` for the design. **Build data:** `python3 build_analytics.py` (reuses
`build_db.norm()` + `web/analytics/avyayas.json`) → `web/analytics/*.json` (~810 KB, lazy-loaded,
bundle-able into Capacitor later): `citations`(2167) · `sources`(curated registry, ~95% canonicalised)
· `topics`(per-work heading tree) · `concepts`(25 seeded, EDITABLE) · `wordfreq`(surface+collocations)
· `cooccur`. **UI:** header link **अनुसन्धान** → `#/anu/<view>`; module `anusandhana.js` (uses app.js
globals DB/q/disp/norm/hl/view); all rendering hand-rolled inline SVG (squarified treemap, force graph,
word cloud, bars). Added `#/b/<slug>/<seq>` deep-link route in app.js (opens the chapter, scrolls +
`.flash`).
- **Concept locator** (headline, works great): concept chip or free text → cross-work distribution
  bars + editorial-topic hits + text loci, all deep-linked. Stem-substring over `text_skel` (suffixal
  inflection) + topic-heading LIKE + curated thesaurus stems. Verified: तारतम्य → 65 loci / 18 works.
- **Citations** (excellent): category-colored ranking bars (Ṛgveda 274 … from 2167), drill→instances,
  + works↔sources force network (`#/anu/cite/net`).
- **Topics**: squarified treemap per work; tiles = DIRECT section span (build_topics), largest ~180
  shown, deep-link. (2026-07-28: fixed strip-y look by switching subtree-span → direct-span.)
- **Words** (excellent): freq cloud (surface, avyaya-stripped) per work/corpus + log-likelihood
  collocations (श्रीशुक उवाच 375…).
- **Network**: word co-occurrence force graph — **PMI-sparsified** at build (positive-PMI, min-joint,
  top-260 edges → ~83 nodes) so edges are significant, not hairball; layout runs unclamped then
  **rescales to fit the viewport** (no perimeter-ring artifact). Deep-links to concept locator.
- **Registry/concepts** (2026-07-28): 55 canonical sources (variants+typos folded via CANON+EXTRA,
  ZWJ stripped, malformed multi-ref labels → "(other)"); 46 seeded concepts.
- **COMPLETE pramāṇa index (2026-07-28):** build_citations now emits EVERY pramāṇa — kutra-tagged
  sources (with ref) AND the inline “…” quotations (attributed to kutra[i] by position; the rest →
  `(unattributed)`, quote text kept). **2167 → 5067 citations** (sutra_bhashya 497→1168 — the missing
  ones the user flagged were untagged inline quotes). `(unattributed)` shown as a separate "Untagged"
  bucket, not scaled into the source ranking. Each citation now carries a quote snippet (`q`).
  citations.json ≈ 1.1 MB (lazy-loaded).
- **Inline attribution extraction (2026-07-28):** most "(unattributed)" quotes DO name their source in
  Madhva's prose (`“…” इति ब्रह्मतर्के`, `उक्तं च स्कान्दे- “…”`). build_analytics now reads these via a
  curated `INLINE_LEX` (locative form → canonical), gated so prose noise (हि/वचनात्/चेत्) is ignored;
  patterns `_AFT` (cue+Src right after quote) / `_BEF` (Src- right before). **Recovered 620 attributions,
  unattributed 2900→2280.** Surfaced sources known chiefly through Madhva's quotes — **Brahmatarka (53),
  Śabdanirṇaya (53)**, Brahmāṇḍa/Brahmavaivarta/Garuḍa/Bhaviṣya purāṇas, named śrutis (Paiṅgi, Kauṇḍinya,
  Bhāllaveya, Nārāyaṇa…) — added to CANON (new categories `tantra`,`shruti`). Bare श्रुतेः/स्मृतेः →
  `(śruti/smṛti, unnamed)` buckets. **Combined** into the one ranking (per user); inline-derived records
  carry `via:'inline'`, shown as a gold **†** in the drill (kutra-tagged have none). Verified: every
  spot-checked † is `इति <Src>` right after the quote. To extend: add forms to `INLINE_LEX` + sources to
  CANON, rerun.
- **Unattributed reduction — 3 levers (2026-07-28):** (①) **single-source block inheritance** — when a
  block's kutra sources all map to ONE canonical text, its extra untagged quotes inherit it
  (`via:'block'`, gold **‡**; 427 recovered, verified 100% consistent). (②) **grammatical filter**
  `is_grammatical()` drops dhātu-pāṭha root-glosses (`ऋ गतौ`) + single-akṣara spans — kept CONSERVATIVE
  so real short quotes/mahāvākyas survive (modest effect by design). (③) **lexicon tail** — more named
  śrutis/tantras (Kauṇṭharava, Nārāyaṇa-tantra, Brahmasāra, Sattattva…). **Net: unattributed 2900 →
  1783.** Residual ≈ 655 multi-source-block extras (ambiguous) + 479 no-cue + long-tail — honestly left.
  Provenance markers: kutra=none, inline=†, block=‡ (legend in the Citations lead).
- **Citation ranking GROUPED by category (2026-07-28):** the 95-source list was flat/count-sorted, so
  the scholarly Pāñcarātra-tantra & named-śruti sources (Caturveda-śikhā, Brahmatarka…) were buried at
  ranks 34–95. viewCite now groups sources under category headings (`.catlabel`): Veda · Śruti (named
  recensions) · Brāhmaṇa · Āraṇyaka · Upaniṣat · Sūtra · Gītā · Itihāsa · Purāṇa · **Tantra/Pāñcarātra**
  · Smṛti · Vyākaraṇa · Stotra · Other (CATNAME/CATORDER in anusandhana.js). Discoverability fix only.
- **Concept → Pramāṇa (2026-07-28):** concept locator now shows "**Pramāṇas cited here**" — attributed
  citations in/adjacent (±1 seq) to the concept's loci blocks, ranked (e.g. tāratamya → Ṛgveda 57,
  Gītā 28), deep-linked to the citation drill. Fuses the two pillars.
- **See-all + CSV export (2026-07-28):** concept loci now fully listed & **paginated** (25/page, up to
  3000) with **⤓ Export CSV** (all loci: work/ref/seq/text); citation drill shows ref + quote + work,
  is capped at 400 shown with **⤓ CSV** for the full set. Helpers: `csvDownload`, `anuExportConcept`,
  `anuExportCite` in anusandhana.js (client-side Blob download; native later needs Filesystem plugin).
- **To extend:** add sources to `CANON`/`EXTRA` or concepts to `CONCEPTS` in build_analytics.py, then
  `python3 build_analytics.py`. **DB ~18 MB → first load takes seconds; full reload needed for JS
  changes (hash nav alone won't).**

## Citation de-dupe + click-to-highlight — 2026-07-28
- **De-dupe within block:** build_citations now collapses repeated `(source, ref)` tags in a block
  (ref-less rows dedupe on the quote) → 5054 → **4902** citations, 0 within-block dups. Removes the
  editorial duplicate-tagging inflation (e.g. aitareya:25 tagged महैतरेय २/२/३ ×9). Reader end-line
  also de-duped (`[...new Set(kutra)]` in app.js block()).
- **Click-to-highlight:** citation-drill rows deep-link `#/b/<work>/<seq>/<encoded-quote>`; router
  passes the quote to `renderBlock(slug,seq,quote)`, which sets `_hlSeq/_hlQuote`; `block()` calls
  `highlightQuote()` to wrap the matching “…” span in `<mark class="cithit">` (script-independent —
  splits text_dev at the span, disp()s each part). Scroll centres on the highlight. So clicking a
  citation lands on the exact quoted span, not just the block. (Concept loci links stay quote-less =
  block flash only.)

## Pramāṇa quotes on their own lines — 2026-07-28 (web/app.js, web/index.html)
Prose/commentary blocks used to render all inline (`mk(disp(text_dev))`), so the quoted pramāṇa
`“…”` spans ran continuously inside Madhva's prose. New `proseBody(dev, hlQuote)` splits the block:
Madhva's prose flows, each `“…”` (or `‘…’`) pramāṇa quotation is a **block-level `.pram-q`** —
own line, green (`#3f6b2f`), left-border/indent (de-cluttered). Replaces the old `highlightQuote()`
(the citation-deep-link highlight is now folded in: the target span gets `.cithit`). Applies to
non-padya blocks only (verse blocks keep verseHTML). Verified segmentation offline on sutra_bhashya:153.

## Concept locator: jump to occurrence + word highlight — 2026-07-28
The "Distribution across works" bars linked to `#/w/<work>` (chapter 0). Now the byWork query also
selects `MIN(seq) fs`, and both the distribution rows AND the text-loci rows deep-link
`#/b/<work>/<fs>/<encoded hlterm>` → the **first occurrence** in that work. The deep-link's 3rd segment
is now dual-purpose: `renderBlock` treats it as a citation quote if it starts with `“`/`‘`, else as a
**concept word to highlight** (`_hlTerm`); `proseBody`'s `emit()` wraps every occurrence (substring, so
inflected/compound forms match) in `<mark class="cithit">`. `hlterm` = concept.dev (or a Devanāgarī query).
- **Occurrence walk (Prev/Next):** clicking a work (or a text-locus) fires `anuWalk(work)` which queries
  the FULL per-work occurrence seq list and sets `window.occWalk={work,seqs,term}`; the href navigates to
  the first. `renderBlock` → `showOccBar()` renders a fixed bottom bar `‹ Prev · <term> · occurrence i/N ·
  Next ›· ✕`; `occGo(±1)` navigates to the adjacent locus, `occClose()`/home clears it, chapter-nav hides
  it (renderWork removes `#occbar`, renderBlock re-adds when walking). So a concept's loci step one-by-one.
- **2026-07-29 fixes (walk "not working"):** (a) `showOccBar` + scroll now run **synchronously** in
  renderBlock (not in a `setTimeout` — hidden/backgrounded tabs freeze timers, so the bar never showed);
  (b) verse-locus highlight — a concept locus that is a **padya** block used verseHTML (no term mark);
  added `termBody()` so `block()` highlights the concept word even in verse blocks. Verified via JS:
  bar shows "occurrence 1/19", verse block marks तारतम्य, occGo advances 1/19→2/19→block 209.
  (Debugging note: the CDP tab was `visibilityState:hidden`, which froze timers and produced spurious
  "renderer frozen"/"setTimeout never fired" — a red herring, not a page hang; the app renders in ~25ms.)

## Grantha-wise search scope — 2026-07-29 (web/app.js, web/anusandhana.js, web/index.html)
Both searches can now be restricted to ONE grantha. Shared helper `scopeSelect(id,cur,onchg)` (app.js,
global) builds an `in [all 38 granthas ▾]` dropdown (works ordered by title).
- **Plain search:** `searchScope` state + `searchSetScope(slug)`; renderSearch adds `AND work=?` and
  shows the selector above results (also in the no-matches state). Verified: "hari" 1254 → 28 in
  gita_bhashya. Also improved: search hits now deep-link to the exact block `#/b/work/seq/<matched
  Devanāgarī word>` (was work-start), highlighting the actual matched word.
- **Concept locator (research):** `locScope` + `window.anuLocScope(slug)`; locate() adds `AND work=?`
  to the byWork/loci/topicHits queries; scope selector shown in the `.cstat` row. (Same helper/pattern
  as plain search; couldn't get a live screenshot — hidden debug tab.)

## Grantha names in the selected script — 2026-07-29 (web/app.js)
Home cards + reader left-nav showed the DB's English/IAST `works.title` regardless of the script
selector. Added `WDEV` (slug → Devanāgarī title, 38 works) + `wname(slug,fallback)=disp(WDEV[slug])`,
used in `renderHome` cards and `renderWork` `.navwork`. Now the grantha names transliterate to the
chosen script (verified deva/iast/kn/te/ta/ml — गीताभाष्यम् → gītābhāṣyam → ಗೀತಾಭಾಷ್ಯಮ್ …), updating
on script change (home re-renders via route()). Group headings already used disp(). NOT changed: the
scope-dropdown options + Anusandhāna work labels (A.titles) stay English — extend with wname() if wanted.

## Closing-quote dangle — verse blocks too — 2026-07-29 (web/app.js verseLines)
The earlier ॥”-word-joiner fix only covered PROSE blocks (proseBody). Verse blocks (is_padya → verseHTML
→ verseLines) split the verse at each daṇḍa run, so a `”` right after `॥` was pushed to its own line
(e.g. sutra_bhashya:64, a mixed prose+verse block flagged is_padya). Fixed: verseLines' daṇḍa-run split
regex now swallows a trailing `[”’]?` (keeps ॥” together), and the śloka-end test is `/॥[”’]?\s*$/`.
Verified in Chrome: pāda ends `विष्णुरेवाभिधीयते॥”`, no lone `”`.

## Topics rail on narrow screens — 2026-07-29 (web/index.html, web/app.js)
The right **Topics rail** (`.toc`, active chapter's in-page section headings) was hidden below 1100px,
so the native apps (phones + iPad portrait ~1024px) lost in-chapter topic navigation that the desktop
website shows. Two-part fix: (1) breakpoint that hides `.toc` lowered **1100 → 1000px** so iPad-portrait
keeps the right rail (3-column layout, matches website); (2) new **collapsible `<details class="toc-inline">`
"विषयाः · Topics" panel** rendered at the top of the reader, shown only ≤1000px (phones) so topics are
never lost. `renderWork` emits both; CSS shows exactly one per width. `sideTopics(ch)` links (scrollIntoView
by `#b<seq>`) work in either container. Verified: iPad = right rail restored; iPhone = collapsible panel.
Both artifacts + read screenshots rebuilt.

## NATIVE APPS — Capacitor wrap (iOS + Android) — 2026-07-29  ← this session
Wrapped the web reader as **native iPhone + iPad + Android apps**. New project dir
**`/Users/prathosh/Sarvamula/app/`** (Capacitor 8). `web/` stays the single source of truth.

**Layout & workflow**
- `app/capacitor.config.json` — appId `com.sarvamula.reader`, appName **`Sarvamula`** (display name, plain
  ASCII per user 2026-07-29 — no macron; bundle ID unaffected), webDir `www`.
- `app/package.json` scripts: `npm run sync-web` (copies `../web/.` → `www/`, strips serve.py +
  the 0-byte analytics db) and `npm run sync` (sync-web + `npx cap sync` → pushes into both native
  projects). **After any `web/` change:** `cd app && npm run sync`, then rebuild.
- `app/ios/` = Xcode project (SPM-based, NO CocoaPods). `app/android/` = Gradle project.
- The **19 MB `sarvamula.db` is bundled inside both apps** (ios/App/App/public, android app assets)
  → 100% offline, no server, no network. Verified running on iOS Simulator with ZERO reader-code
  changes (home renders live block/verse/topic counts from the bundled DB; sql.js wasm loads fine
  over Capacitor's local scheme).

**Native polish**
- Safe-area insets added to `web/index.html` (viewport-fit=cover + `env(safe-area-inset-*)` padding
  on `header` and `#occbar`). Harmless on desktop web (`env()`=0), clears the Dynamic Island / home
  indicator on device.
- **Icon (2026-07-30) = devotional painting of Śrī Madhvācārya** — user-supplied `app/assets/App_icon.jpeg`
  (362×425 portrait) → 512² square via sharp cover-crop `strategy.attention`, opaque `#2e2a20` fill.
  `app/assets/{icon-only,icon-foreground}.png` = that square (full-bleed, iOS + Android adaptive);
  `icon-background.png` = solid `#2e2a20`; `npx capacitor-assets generate` fanned out all sizes. Store
  listing icons `artifacts/{play-store-icon-512,appstore-icon-1024}.png` also this image.
  **NOTE:** the earlier aṣṭadala **lotus emblem** was replaced as the icon, but the **splash screens
  (`app/assets/splash*.png`) + the Play `feature-graphic-1024x500.png` STILL use the lotus** — align to
  the Madhva image if brand consistency is wanted. To change the icon: replace `App_icon.jpeg` (or re-crop)
  → regenerate icon-only/foreground → `capacitor-assets generate` → rebuild artifacts.

**Signing & artifacts** (all in `app/artifacts/`)
- **iOS:** `Sarvamula-1.0.ipa` (6.9 MB). Archived + exported with **automatic signing**, Apple
  **Distribution** cert, **Team P33954J97U**; passed `-validate-for-store`. Archive cmd:
  `xcodebuild -project ios/App/App.xcodeproj -scheme App -configuration Release -sdk iphoneos
  -archivePath ios/build/App.xcarchive archive DEVELOPMENT_TEAM=P33954J97U CODE_SIGN_STYLE=Automatic
  -allowProvisioningUpdates` → `-exportArchive` with `ios/ExportOptions.plist` (method
  app-store-connect). Registers the App ID in the Apple account on first run. Xcode 26.3.
- **Android:** `Sarvamula-1.0-release.aab` (9.7 MB), signed with an **upload keystore** generated this
  session: `app/android/sarvamula-upload.keystore`, creds in `app/android/keystore.properties`
  (pw `IX0PaVuf5yF/xX6uguY8TqwA` — **MUST be backed up**; loss = reset upload key via Play support).
  build.gradle wired with a `signingConfigs.release` reading keystore.properties. **Build needs JDK 21**
  (default java is 17 → "invalid source release: 21"): prefix gradle with
  `JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"`. Cmd:
  `cd android && JAVA_HOME=… ./gradlew bundleRelease`.

**Store assets** (`app/artifacts/`)
- Screenshots — 5 views each (**home, read w/ Topics, kannada multi-script, search 1094 hits, anu
  concept locator**), all flattened to **no-alpha**. Captured via the sim harness (`shot.sh`+`inject.py`).
  **CAVEAT: the first-captured `home` was blank** (cold-start, DB not loaded at 7 s sleep) — always eyeball
  home, or give the first shot ≥14 s. Four sets in `app/artifacts/screenshots/`:
  - **App Store** `ios-iphone-6.9/` (1320×2868, 2.17:1) + `ios-ipad-13/` (2064×2752).
  - **Google Play** `play-phone/` (**1613×2868 = 16:9**, iPhone shot padded with cream margins — Play
    REJECTS the 2.17:1 iPhone shots as taller than its 16:9 cap) + `play-tablet/` (2064×2752, 1.33:1 —
    **same files for BOTH 7-inch and 10-inch slots**). Regen: sharp `resize(1613,2868,{fit:'contain',
    background:'#fdfaf4'})` for phone; `flatten` for the rest.
- `feature-graphic-1024x500.png` (Play) — lotus + "Sarvamūla" wordmark + tagline.
- **How the screenshots were captured (reproducible):** the Chrome MCP screenshot path was UNUSABLE
  (hidden-tab script-injection timeouts — the recurring backgrounded-tab problem). Instead: booted the
  two exact-size simulators, installed the Debug `App.app` on both, then a harness (scratchpad
  `shot.sh` + `inject.py`) copies a route-injected `index.html` into each sim's app-bundle `public/`
  (a `<head>` script sets `localStorage.sv_script` + `location.hash` before app.js, so the app renders
  the target view on launch — no tapping), relaunches, and `xcrun simctl io … screenshot`s both.
  Search view uses a DOM-ready poller (`.wcard` present) then dispatches an `input` event (the app
  scopes/paginates itself). NOTE: the app declares `DB` as a scoped var, NOT on `window` — gate
  readiness on a rendered `.wcard`, not `window.DB`.

**Submission (paste-ready):** `app/SUBMISSION.md` has app identity, full listing copy (subtitle,
promo, description, keywords), categories (iOS Reference/Education; Play Books & Reference), age rating
(4+/Everyone), **privacy = No data collected** (privacy policy URL
https://sites.google.com/view/rigvaani-privacypolicy/policy-sarvamula), and per-store upload steps.
Remaining work is the USER's account actions (create app records, upload, submit) — I can't touch
store credentials.

**Phased plan — audio in v1.1:** v1 ships with NO audio (agreed). v1.1 adds pre-generated Sanskrit TTS
streamed on demand from Cloudflare R2 (matches the VedaVāNi/Bhāgavatam pattern) + a per-verse play
button. The Android `INTERNET` permission is already present (unused in v1) so no manifest change is
needed for the audio update. Bump version → `npm run sync` → rebuild → upload as an update.

## Next candidates (pick one)
1. **Submit to the stores** — user's account actions per `app/SUBMISSION.md` (create app records in
   App Store Connect + Play Console, upload the `.ipa`/`.aab`, paste listing, submit).
2. **v1.1 audio** — Sanskrit TTS pipeline → Cloudflare R2 → per-verse streaming play button.
3. **Feature-up the reader** — bookmarks, verse share, continue-reading (port Bhāgavata-VāNi extras).
4. **Deeper data QC** — heading levels, colophon completeness (mbtn:1041 looks split), danda-only blocks.

---

## TEXT FIDELITY CAMPAIGN + APP 1.2 — 2026-08-17 / 08-18  ← this session

Full write-up: **`Sarvamula_2026-08-19.md`**.

Nine reader-visible defects, all in how the printed edition was reproduced. Four were mine,
introduced while fixing the others; they are marked **(self-inflicted)** so the pattern is on
record rather than buried.

### The root cause behind most of it

`entries.text_dev` is built by JOINING the source JSON's `text` list into one string, so the
edition's own line breaks are destroyed before the segmenter ever sees them. The segmenter then
re-derives pāda boundaries from visargas and length, and cuts inside hemistichs:
`कर्मभिः ।` / `शुद्धसत्त्वानां कर्मत्यागोऽपि नान्यथा ।` where the book prints one line. Whether
that happens depended on `is_padya`, which is unreliable (it marks entries that CONTAIN verse), so
Aitareya's ślokas arrived typed `gadya` and got the prose treatment.

**Fix:** `audio/build_entry_lines.py` recovers the edition's line structure by aligning each entry
against its work's source JSON and writes `audio/entry_lines.json` (26,585 entries). Consumed by:

* `segment_bsb.merge_padas_to_edition()` — puts back every cut the edition does not make, AFTER
  `fit_padas`, ALL-OR-NOTHING per line and never past `MAX_PADA_AKSHARA`. Pairwise "while it fits"
  half-merged long prose and inflated one render by 367 clips.
* `build_audio_db.regroup_to_edition()` — display lines follow the edition, merging AND splitting.
  `segs.ln` is a list, so several clips may light one line; nothing about the audio has to change.

**A source line is NOT always an edition line.** The extraction turned visual wrapping into
separate array elements: `[147]'उपासते' [148]'महाविष्णुं' [149]'परमात्मानमच्युतम्।'` is one
anuṣṭubh line. Honouring those blindly PRESERVED the fragments. A real line end carries `।`, `॥`,
`*`, a closing quote or a hyphen; a wrap fragment ends bare. That test removed **5,902 of 64,425
boundaries — 9% were artifacts.** **(self-inflicted:** shipped the split pass without this and
re-broke Aitareya for ~30 minutes.)

### Prose mūla read as one breath

`mula_prose` is per-WORK and cannot describe an upaniṣad whose mūla is MIXED. Kena, Kaṭha, Praśna
and Māṇḍūkya open in verse and continue in prose, so the flag was never set and their prose khaṇḍas
stayed a single "metrical" pāda: Kena's yakṣa narrative went to the model as **533 akṣaras in one
41.3 s clip**; Praśna 1 as **1,067**. Now length-driven, and cut from the RAW mūla — `build_units`
strips daṇḍas from a sūtra, so splitting the pāda found nothing to split on.
Kena is now **120.7 s across 36 phrase clips**. Over-60-akṣara pādas: **119 → 56** (the remainder
are prose śruti quotes typed `padya`; the pipeline correctly refuses to cut verse).

### Stale rows and truncated timings

* **43 stale blocks / 142 rows** deleted (Aitareya, Kāṇva, Chāndogya). Block ids encoded pre-
  renumbering seqs, so `ait_seq5` served entry 12's OLD text under entry 5 — the reported "still the
  old junk". `build_audio_db` only deletes blocks named in its timings file, so vanished blocks
  survived forever. Now skipped-and-counted (`stale-block`/`stale-part`) instead of `IndexError`.
* **`assemble_bsb.py --only` truncates its `--timings` target** to just the blocks it assembled.
  Five works had been silently reduced — nvv **63 of 471**, tss 2/75, tsk 2/9, sgb 1/5, kam 17/30 —
  so most of their rows could never be refreshed, and any rebuild from those files would have dropped
  the karaoke timings of every untouched block. Re-assembled in full; nvv alone then gained 148 rows /
  233 merged lines.
* `--existing_only` added: a display pass refreshes tiles but never ADDS one. Without it a rebuild
  resurrected `dvadasha_stotra`'s deleted TTS tiles (24 → 39) — the "shows both TTS and chanted"
  bug returning. **(caught before shipping.)**

### Renders (5 boxes × 2 A6000 = 10 workers; box5 NVML broken but CUDA fine)

| round | clips | renamed free | result |
|---|---|---|---|
| daṇḍa/verse-split, 18 works | 1,289 | — | FAIL=0 |
| Bhāgavata + 7 corrections | 392 | 246 | FAIL=0 |
| edition lines, 22 works | 1,344 | 1,788 | FAIL=0 |
| prose mūla, 13 works | 2,582 | 731 | FAIL=0 |

**Renames are free.** A clip id is `<block>_u<NN>_<type>_p<NN>_<sha1(pada|meter)>` — the hash covers
text and metre only, so a clip whose position moved is COPIED to its new id, not re-rendered.
~2,700 clips avoided, more GPU than the renders themselves cost.

### Gītā

* Bhāṣya/Tātparya were swapped: names, `works.title`, 702 audio kinds, segmenter config.
* Pārāyaṇa Gītā printed a whole verse as one line with **no mid-verse daṇḍa** — `build_mula_works`
  joined pādas with a space and stripped daṇḍas, in the display AND in `entries.text_dev`.
  `unit_lines()` now emits one line per pāda; bg_1 47 → 100 lines.
* `श्रीभगवानुवाच-` fused to the verse in all 18 adhyāyas: 6 akṣaras ending in a HYPHEN, which is a
  SOFT boundary, so `fit_padas` absorbed it, while `अर्जुन उवाच ।` survived on its daṇḍa. In the Gītā
  source a hyphen-terminated `…वाच-` occurs 28 times and is ALWAYS a standalone tag, never inline —
  so the hyphen is a safe signal, unlike bare `उवाच`, which is usually the finite verb
  (`उवाच पार्थ पश्यैतान्`, 1/25). Regex on `उवाच` would have wrongly split 51 of 55 matches.
* **`१३/०` is NOT a numbering bug.** The source prints it, and the verse is bracketed —
  `[अर्जुन उवाच- … १३/०॥]` — outside Madhva's accepted text, numbered 0 so the canonical verses keep
  their numbers. `इदं शरीरं कौन्तेय` really is 13/1. Renumbering would break every citation.
  The real defect is that `_debracket` strips the brackets, leaving the 0 unexplained. **OPEN.**

### Roman search never matched diphthongs

`norm()` has a Devanāgarī branch and a roman branch and they disagreed: `ै`/`ौ` collapse to `e`/`o`,
so `द्वैत` keys as `dveta`, while typed `dvaita` stayed `dvaita` and matched **nothing in 37 works**
(`text_skel LIKE '%dvaita%'` → 0 rows; `'%dveta%'` → 54). Roman `ai`/`au` now fold too, in
`web/app.js` AND `build_db.py` — the comment there requires the two implementations stay identical;
verified by diffing their output over 11 inputs. Also fixed `jaimini`, `kaustubha`, `vaishnava`,
`aitareya`, `maitreyi`.

### Concept locator (Anusandhānam)

Machinery existed with 46 concepts; three gaps closed in `web/anusandhana.js`:

1. **AND-groups** — `all: [[पाद,चरण,पदाम्बुज,श्रीचरण],[महिमा,माहात्म्य]]`. Stems were only ever OR'd.
2. **Exclusions** — `not: [प्रथमः पादः,…]`, without which `पाद` returns 3,375 rows of section headings.
3. **Multi-word free text ANDs**, as the main search box already did.

`pada mahima`: **1 → 35 → 39** loci. Seeded `pada_mahima` as the worked example; the other 46 use
`stems` and fall back to the old flat OR.

**Distributional synonym expansion FAILED.** `audio/concept_candidates.py` proposes candidates from
corpus co-occurrence with no model. Top hits for `तारतम्य` were `स्यात्`, `नैव`, `कथञ्चन`, `भवेत्`,
`नच` — Madhva's argumentative idiom, not synonyms: invariant particles beat inflected content words
on frequency. One useful hit (`मुक्तानां`, already seeded). Needs lemmatisation to be worth using.
**Concept vocabulary remains scholarly work.**

### Content now flows without a store release

The apps shipped `DB_REV`/`AUDIO_REV` as constants, so every correction stopped at the web — the
reader kept requesting the revision it was built with and its own cache answered. Seven revisions in
one day reached nobody on a phone.

`version.json` on R2 (`{"db":…,"audio":…}`, `Cache-Control: no-store`) is fetched at launch;
fallback order is last-seen (`localStorage`) → bundled constants, so offline still works.
`audio/publish_revs.py` reads the values straight out of `web/app.js` so the manifest cannot drift,
and is run LAST in a release — **which makes it a release gate**: bake and upload freely, publish
revisions once per batch. Each bump costs every user an 11 MB database download.

**Reader CODE does not flow this way** — search, PDF, UI are bundled. A user's search-navigation
complaint had been fixed on the web for a day; only 1.2 delivers it. OTA assets
(`@capgo/capacitor-updater`) would close that gap; scoped, not built.

### PDF export in the apps

Both buttons called `window.print()`, which Mobile Safari and desktop browsers implement but
**Android WebView and iOS WKWebView do not** — a silent no-op, working on the web only. Native
bridges added: `SvPrint.java` (`PrintManager` + `createPrintDocumentAdapter`) and `SvPrint.swift`
(`UIPrintInteractionController` + `WKWebView.viewPrintFormatter()`). Registered in
`MainActivity.onCreate` BEFORE `super` (the bridge is built there). Method named `printDoc`, not
`print`, which would shadow Swift's global. Cleanup fires on the promise, since `onafterprint` never
fires natively.

`viewPrintFormatter()` deliberately, not `UIMarkupTextPrintFormatter`: the markup formatter drops the
bundled woff2 faces and breaks Devanagari shaping — the same failure a JS PDF library causes, and the
reason printing goes through the platform at all.

**Both PDF buttons produced identical output** because the rules that reveal `#printroot` and hide
the reader lived inside `@media print`, and the native path captures the WebView AS LAID OUT, where
print media never applies. The swap now applies at all media; `@media print` keeps only page margins
and print typography. **(self-inflicted:** shipped the bridge with this bug.)

### Traps that bit more than once — read before editing

* **`[ऀ-ॿ]` INCLUDES the daṇḍa** (U+0964), double daṇḍa and Devanāgarī digits. Bit twice today:
  once making `bare()` treat a fragmented and a merged line as different (so an audit missed 313
  cases), once filling the synonym candidate list with `च।` and `तु।`. Use
  `[ऀ-ॣ०-ॿ]` or exclude explicitly.
* **Replacing an m4a at the same path requires bumping `AUDIO_REV`.** Objects carry
  `immutable, max-age=1y`; 231 corrected blocks could not reach anyone who had already played them.
* **Every `<script>` tag needs its own version bump.** `app.js` was bumped to v=28 and
  `anusandhana.js` left at v=2, so the new concept locator looked broken while being correct on the
  server — JS is `max-age=14400, must-revalidate`, i.e. FRESH for four hours, and `must-revalidate`
  does nothing until it goes stale. Bump `anusandhana.js`/`anukramanika.js` when they change.
* **`pgrep -f <pattern>` matches its own command line.** Reported 4 boxes rendering when 1 was, and
  killed a remote shell via `pkill -f retry26`. Use `ps -eo args | awk '… && !/awk/'`.
* **rclone `copy` does not log already-identical files at INFO**, so "809 of 1,256 copied" was
  complete. Verify by sampling object sizes against local, not by counting log lines.
* **`node --check` passes files with real SyntaxErrors** — also run `new Function(src)`.

### State at close

* Live: `DB_REV='2026-08-18a'`, `AUDIO_REV='8'`, `app.js?v=28`, `anusandhana.js?v=3`,
  `version.json {"db":"2026-08-18a","audio":"8"}`
* 25,603 audio rows · 0 orphans · 0 out-of-range karaoke indices · 0 segs past clip end · 0 dark rows
* Audio uploaded this session: 231 + 1,453 + 722 + 590 + 1,256 files, 0 errors
* Android **`Sarvamula-1.2-release.aab`, versionCode 5**, signed, verified, ready to upload
* iOS **`Sarvamula-1.2.ipa` is STALE** — exported before the search fix and the concept locator

### Open

1. **iOS re-archive** so both stores carry identical code.
2. **PDF untested on a device** on either platform — compiles and the CSS cause is fixed, but no print
   sheet has been observed. `Sarvamula-1.2-debug.apk` is the same code.
3. **Gītā `१३/०`** — restore the brackets (recommended) vs renumber (breaks citations).
4. **Coverage limits, by instruction:** 1,433 entries have no recovered line structure (Kāṇva 696,
   Chāndogya 594, Aitareya 143) — they recite mūla from books absent from their own JSON. Bhāgavata's
   display fix is render-free and available (6,397 lines / 1,132 tiles) but its audio scope was
   narrower than the display (284 clips vs 6,144 lines) because its source stores commentary as
   paragraphs with verse quoted inside.
5. **56 over-long pādas** remain — prose śruti quotes typed `padya`; needs a trustworthy metre check.
6. **Concept vocabulary** — 47 concepts; expansion is scholarly work, machinery is ready.
7. **R2 access key pasted in chat on 2026-08-17 still wants rotating.** Android keystore password is
   plaintext in `android/keystore.properties`, `RESUME.md` and `app/SUBMISSION.md` — redact before any
   GitHub push; losing that keystore means losing the ability to update the Play listing.
