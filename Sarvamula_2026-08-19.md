# Sarvamūla — text fidelity campaign + app 1.2

**Written 2026-08-19.** Work carried out 2026-08-17 into 2026-08-18 (the session ran past midnight,
so the shipped revisions are labelled `2026-08-17a`…`2026-08-17g` and `2026-08-18a`).

Companion to `Sarvamula_2026-08-02.md` and `Sarvamula_2026-08-08.md`. Summary lives in
`RESUME.md` § TEXT FIDELITY CAMPAIGN + APP 1.2.


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
