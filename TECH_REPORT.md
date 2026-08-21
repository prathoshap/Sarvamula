# Sarvamūla — technical report

**As of 2026-08-16.** Live at <https://sarvamulavani.com>; iOS 1.1 (build 2) and Android 1.1
(versionCode 3) submitted for review.

This is written for whoever picks the project up next — including me, months from now. It
records **why** things are the way they are, and especially the mistakes, because most of the
design here is scar tissue. Where a decision looks arbitrary, there is usually a failure behind
it, and the failure is named.

---

## 1. What exists

| | |
|---|---|
| Corpus | 40 granthas, 29,328 entries |
| Audio | 25,733 files, **142.4 h**, every work voiced |
| — synthesised | 25,181 files, 139.2 h (Vāgdhenu / IndicF5) |
| — **recited by hand** | 552 files, 3.2 h (all Vedic-accented material) |
| Database | `web/sarvamula.db`, 49.8 MB, 10.3 MB gzipped |
| Reader | 21 static files, 2.3 MB, hash-routed, no build step |
| Hosting | Cloudflare Pages + R2, custom domain |

Audio splits into two provenances that must never be confused:

* **Synthesised** — everything without Vedic accent.
* **Recited** — every accented passage. No TTS here is trusted with svara, so `skip_svara`
  (shape A) and the `_SVARA` guard (shape B) held those passages back as they were met, and
  they were later recorded by hand and cut in. 552 files: Ṛgveda 457, Dvādaśa Stotra 24,
  Taittirīya 11, Kaṭha 18, Īśāvāsya 14, Karma Nirṇaya 22, and 2 each for Ṣaṭpraśna, Māṇḍūkya
  and Muṇḍaka.

---

## 2. Shape of the corpus

Two segmenters, because the granthas come in two shapes:

* **`segment_bsb.py` (shape A)** — mūla paired with commentary. Brahma-sūtra Bhāṣya, the Gītā
  works, the Upaniṣad bhāṣyas.
* **`segment_anu.py` (shape B)** — Sarvamūla-only verse, no pairing. Anuvyākhyāna, the
  prakaraṇas, Ṛg Bhāṣya, Dvādaśa Stotra.

Shape B splits a verse either on its printed number (`split="number"`) or on the daṇḍa
(`split="danda"`), per work. Ṛg Bhāṣya has **one** printed number against 1,475 double daṇḍas,
so the daṇḍa has to end the verse there; Anuvyākhyāna is the opposite.

### Clip ids are content-addressed

`<block>_u<NN>_<type>_p<NN>_<sha1[:6]>`, where the hash covers **the pāda text and the metre**.

This is not decoration. Unit numbers are *not* stable across re-segmentation: promoting one
unquoted verse in `bsb_1_1_1` shifted every later unit by one and left 44 of 59 clips with an
unchanged id and different text. Without the hash, `--resume-from` cheerfully reused the stale
audio and nothing complained. With it, changed text yields a new id, the stale clip simply
isn't found, and it gets re-rendered.

The corollary bites in the other direction: **any edit to pāda text renumbers nothing but
re-mints that clip's id**, so a one-character fix means re-rendering that clip. That is the
intended trade.

---

## 3. Rendering

`render_batch.py` on the lab GPUs (`ece-box`, `ece-box3/4`), model pinned at
`CHAMPION_2026-06-11`, seed 60, `no_sandhi: true`.

Hard-won specifics:

* **The model cannot voice a lone praṇava.** Measured, not assumed: `ॐ`, `ओम्`, `ओं` and `ओ३ं`
  all render as 0.267 s with **5 ms voiced** and no detectable f0 — and that is with
  `--no_gate`, so it is not our gate eating it. The praṇava is spliced from a human-recorded
  exemplar (`audio/assets/pranava_exemplar.wav`, 0.877 s).
  In context (`ओं अथातो ब्रह्मजिज्ञासा`) the model does produce a praṇava, but only ~70 ms of it.
* **`gate()` has caused more damage than the model.** The "eats the first syllable" bug was
  ours, not IndicF5's. Suspect it first when a clip is short.
* **Pāda size matters more than seed.** Keeping pādas inside the model's trained size window
  (`MIN/MAX_PADA_AKSHARA`) is cheaper and more reliable than `--onset_retry`, which can
  quadruple render time.
* **One segment per clip.** Packing N pādas into one clip is what produced all our onset
  damage; gaps belong to assembly, not to the renderer.

### QC

`asr_verify.py` / `asr_qc_loop.py` decode each clip with **Su-shrota**
(`ASR/exp/ft_ctc_v12/ft_ctc_ep9.nemo`, pinned — *not* the `ft_ctc_current.nemo` symlink, which
repoints on deploy and would silently change what "verified" means) and compare against the
text. Sanskrit vocab slice `OFF=4096, V=256, blank=5632`; the tokenizer needs `lang='sa'`;
local ids map to posterior column `id+1`.

---

## 4. The recordings — the hardest part

Four WAVs, recorded with a tap-to-mark app that writes a timestamp per block, plus an onset
offset. 552 clips came out of them. Almost nothing about this was straightforward.

### 4.1 The timestamps do not partition the timeline

A re-recorded block leaves its **discarded take** in the WAV, with the kept take starting
after it. Dvādaśa Stotra alone has 36 such gaps holding 6.7 minutes of rejected audio. Cutting
an entry as one span played every one of them.

**Cut one slice per block and concatenate.** Never one slice per entry.

### 4.2 The tap is late at both edges

This is the central fact. The recorder marks the *tap*, not the voice:

* a start lands **after** the reciter has resumed → the opening word is missing;
* an end lands **after the next mantra has begun** → its opening rides along at the tail.

Measured over 491 Ṛgveda blocks: end taps a **median 3.25 s late** (p10 −3.87 s), start taps a
median 0.37 s late. Dvādaśa: −0.81 s / −2.70 s.

### 4.3 Energy cannot fix it; forced alignment can

Snapping to a pause works only where a pause exists, and roughly one recitation in ten runs
straight through. Worse, a throat-clear is bounded by pauses exactly as speech is — one
measured **0.151 RMS**, the level of quiet recitation. No threshold separates them.

`align_ts_asr.py` does a real CTC forced alignment of each block's own text (Viterbi over the
blank-extended label sequence). Two things make it work:

* **Guard tokens.** Aligning a block's tokens alone and taking the first/last occupied frame
  fails: Viterbi must place every token somewhere, so with bleeding audio still in the window
  the last token drifts *later* — `rv_0047`'s end moved **+1131 ms the wrong way**. Aligning
  `[tail of previous mantra] + [this mantra] + [head of next]` and reading the span of *this*
  mantra's first and last tokens fixes it: the neighbouring audio has its own tokens to occupy.
* **A plausibility gate.** The tap is late, so a boundary that moves *later* by seconds is the
  path having slid, not a discovery. `--max-late` rejects those; the block keeps its tap.
  Dvādaśa's 12th stotra ends every verse with the same refrain and slid a full verse (+5.4 s)
  without this.

CTC is **peaky** — blank through most of a syllable with a spike at its centre — so non-blank
frames are token centres, not speech boundaries. A blank-probability threshold was tried first
and returned +0 ms ends. Do not repeat that.

### 4.4 The held final syllable

Forced alignment puts the boundary on the final token's *nucleus*, but Vedic chant **holds**
that syllable. Measured across 491 mantras: the voice runs a **median 810 ms** past the aligned
end (p90 1.11 s). Cutting at the alignment truncates the sustain and takes the closing visarga
or anusvāra with it.

`carry()` in `cut_recording.py` walks each edge outward while the voice is above threshold,
adds 100 ms so the cut lands *inside* the silence, and stops at a cap. Bounded by the
neighbouring edge so it can never reach the next mantra.

Re-measure this per recording — it is not a constant: Ṛgveda 810 ms, Dvādaśa 720 ms,
Karma Nirṇaya 585 ms.

**Starts and ends must be bounded against each other, not against the aligned neighbour.**
Otherwise both reach into the same gap and the overlap is emitted in *both* clips — a held
syllable heard twice.

### 4.5 The onset in the notes was wrong once

`Onset_time.rtf` gives 7.796 s for the Swara recording. It is wrong. At that anchor every
window starts ~5 s into its own text; median CER **77.8%**. The correct value is ≈4.5 s, at
which CER falls to **6.5%**.

Two lessons:

* **Diagnose with a decode, not with alignment scores.** `asr_hear_test.py` decodes a block
  and prints CER against the known text. It turned "the model can't handle śruti" into "the
  anchor is off by three seconds" in one run.
* **CER alone could not pin the value** — tap windows are generous, so ±1 s barely moves it.
  The *shift distribution* did: at onset 3.0 starts moved **+703 ms** (later), contradicting
  every other recording, which is what identified 4.5.

Validation that the aligner finds real boundaries: two runs anchored **1.5 s apart** agreed on
absolute start times to a **median 21 ms** (234 of 291 within 100 ms).

### 4.6 Short blocks are unreliable

| block length | n | median CER | over 30% |
|---|---|---|---|
| 0–6 s | 50 | ~15% | 12 |
| 6 s+ | 291 | ~6% | 8 |

A 3-second fragment is short relative to the search window and comparable in length to its own
guard tokens, so the boundary slides onto the neighbour. `--chunk 4` (aligning consecutive
blocks as one sequence) fixes *some* and breaks others — overall it was worse (median 7.0% vs
6.6%), so the shipped alignment is per-block with **8 blocks** taken from a chunk-4 pass where
per-block CER was ≥15 points better. CER is an independent measurement, not the objective
either aligner optimised, so choosing on it is repair rather than overfitting.

### 4.7 Final QC

| | blocks | median CER | p90 | under 30% |
|---|---|---|---|---|
| Swara (śruti) | 341 | 6.5% | 19.4% | 329 |
| Dvādaśa | 152 | 4.5% | 12.8% | 151 |

Alignment *uses* the ASR but does not verify content — it places text we assume was recited.
Only a decode pass tells you the right passage was read. Run it.

---

## 5. Text defects found along the way

* **Square brackets are delimiters, never sound.** Left in, the model reads a bare `[` aloud as
  "a" — heard at the head of Saṅgraha Bhāṣya's maṅgala. `_debracket()` in `segment_bsb.py`
  unwraps groups containing text and deletes those without (`[-]`, `[---]` lacuna marks), and
  **leaves `[ॐ]` alone** — that form is already handled by `depranava()`, and touching it
  re-texted the opening pāda of every sūtra (544 of 5,405 clips changed id).
  Fixed in Saṅgraha, Tantrasāra and Kṛṣṇāmṛta; **still present in 8 works** (§9).
* **Parens must be BLANKED, not deleted, in `segment_anu`** — deleting them shifts offsets:
  `re.sub(r"\([^)]{0,60}\)", lambda m: " " * len(m.group(0)), stream)`.
* **`map_blocks` re-matched the first occurrence of a repeated passage.** Ṣaṭpraśna, Māṇḍūkya
  and Muṇḍaka each open *and* close with the same śānti mantra; the fallback search restarted
  at the current entry with no cursor, so both takes landed on the opening entry and the
  closing one stayed silent. Fixed to start at `ei+1`.
* **`segment_bsb.load_blocks` silently discarded unknown content types** — would have lost
  2,331 akṣaras of Nyāyamālā verse. Guarded.
* **`build_shard_bsb --shards>1` never wrote `<stem>.json`** → QC died and the supervisor
  assembled unverified audio.

---

## 6. Display

### 6.1 Vedic accents — the one that cost the most

A Vedic mark missing from the text font **does not merely box**: the shaper fails on the whole
cluster and drops neighbouring letters. So a font that fails to load is a *correctness*
problem, not a cosmetic one.

Two independent bugs, chased in the wrong order:

1. **`normalize.js` swallowed the tone marks.** Offset transliteration mapped
   U+0951–U+0954 into unassigned code points (`0x0952 + 0x380` = U+0CD2, unassigned in
   Kannada). They are now passed through untouched, with IAST equivalents mapped explicitly.
2. **Cluster splitting.** Letters and marks must come from **one face**. Nine SIL OFL Noto
   subsets are shipped (260 KB total), each carrying the Vedic marks — grafted in from the
   Devanāgarī face where the script's own Noto lacks them (Bengali has no double svarita at
   all).

Also learned:

* **`unicode-range` broke everything** in the target browser — it applied the face to all
  characters. Removed. Proven with a probe page.
* An empty `.notdef` makes letters **vanish** rather than box.
* `file://` blocks `@font-face` URL loads — fonts must be served over http to test.
* `node --check` passed a file with a genuine `SyntaxError` (a regex range `[…क़-य़]`, since क़ is
  two code points). Only actual evaluation caught it. **Always `new Function(src)` as well.**

### 6.2 Reader bugs worth remembering

* **Search highlighting never fired** because `hw` — the matched word put in the URL — kept its
  surrounding `“ ”`, and `renderBlock` treats a leading `“` as a *citation* deep-link, leaving
  `_hlTerm` empty. One stray quote mark disabled both the highlight and the scroll target.
* **Search "didn't work" inside a work** because `renderSearch` never reset the scroll. Results
  replaced a long chapter with a short list while the reader stayed scrolled 4,000 px down.
* **Enter did nothing** on a word already in the box: the input was wired to `oninput` only,
  which fires on *change*. Now `Enter` searches immediately.
* **The database was re-downloaded on every page load** — `{cache:'no-store'}` on a 50 MB
  fetch. `DB_REV` is in the URL, so there was nothing for no-store to protect.
* **Chapter labels** for heading-less works come from colophons. MBTN names its adhyāyas, but
  `nāma` sandhis three ways (`… नाम सप्तमो°`, `…पत्तिर्नाम`, `…नामाष्टमो°`) and the work's own
  name can fuse on by avagraha (`…निर्णयेऽरणीप्राप्तिः`). All handled in `adhyayaName()`.

---

## 7. Infrastructure

```
R2 bucket   sarvamula        9,716 objects, 4.75 GiB   (audio + the .db)
public URL  pub-f4f244dc7f1b4ad2ad5c4116104064ed.r2.dev
site        Cloudflare Pages project "sarvamula" → sarvamulavani.com + www
domain      sarvamulavani.com, registered at Cloudflare, expires 2027-08-15
```

* **The database is fetched, not bundled.** 50 MB inside the binaries would mean a store review
  for every content fix; fetched, a correction is one upload. It is stored **gzipped** with
  `Content-Encoding: gzip` — 10.8 MB over the wire, and R2 decompresses server-side for clients
  that don't ask.
* **CORS is required** and is not on by default. Without it the WebView's `fetch` of the
  database is refused and the reader shows "load error" on a blank page. `<audio>` is unaffected
  — media loads without a `crossorigin` attribute do not do CORS checks. Bucket-level CORS
  needs an **Admin** token; the Object Read & Write token used for uploads cannot set it.
* **`audio.base` holds a token, not a URL.** Bhāgavata Tātparya's 16,017 mūla verses stream
  from the Bhāgavata-VāNi bucket — one work, two buckets. Stored in full that URL was 1 MB of
  the database saying the same thing 16,017 times; it is now `bhv`, expanded by `BASES` in
  `app.js`.
* **Upload with `copy`, never `sync`.** `sync` would delete anything in the bucket not in the
  file list. Verified with `rclone check`: 9,716 matching, 0 differences.

### Apps

Capacitor 8, `com.sarvamula.reader`, label **Sarvamula**, 1.1 (iOS build 2 / Android
versionCode 3). `app/www` is a copy of `web/` minus the database and the probe pages.

* **Java 21 is required** by Capacitor 8; the shell had 17. Use Android Studio's JBR.
* **`DEVELOPMENT_TEAM` was missing** from `project.pbxproj` — Capacitor doesn't generate it, so
  command-line archiving failed until it was written in.
* **`limitsNavigationsToAppBoundDomains` was `true` with no `WKAppBoundDomains` declared**, i.e.
  an empty domain set, while everything now loads from `r2.dev`. Turned off.
* Android's `androidScheme: https` is the Capacitor 8 default — changing it would move the
  WebView origin and wipe every user's stored script and reading size.

---

## 8. How to do the common things

```bash
# segment a work (shape B / shape A)
python3 audio/segment_anu.py --work <slug> --out audio/blocks_<pfx>.json --db web/sarvamula.db
python3 audio/segment_bsb.py --work <slug> --out audio/blocks_<pfx>.json --db web/sarvamula.db

# render a shard (on a lab box)
$INDICF5 render_batch.py --shard <shard>.json --results <shard>_results.json

# QC, assemble, bake
$ASR_PY asr_verify.py --clipdir <dir> --manifest <man>.json --out qc.json
$PY assemble_bsb.py --blocks blocks_X.json --clipdir <dir> --outdir r2 --timings timings_<work>.json
python3 audio/build_audio_db.py --blocks blocks_X.json --timings timings_<work>.json \
        --db web/sarvamula.db --work <slug> [--only <block ids>]

# cut a recording (alignment first, on a box; then cut locally)
$ASR_PY align_ts_asr.py --wav X.wav --ts TS_X.json --src X_by_shloka.json --onset N --out TS_X.aligned.json
python3 audio/cut_recording.py --work <slug> --wav X.wav --ts TS_X.aligned.json --src X_by_shloka.json \
        --onset N --outdir web/audio/<slug> --prefix <p> --kind <k> --append \
        --startsil 0.35 --endsil 1.5 --joingap 0.35 --tailgap 0.30 --write

# deploy
rclone copy <dir> r2:sarvamula --files-from <list>          # audio
gzip -9 -c web/sarvamula.db > db.gz && rclone copyto db.gz r2:sarvamula/sarvamula.db \
  --header-upload 'Content-Encoding: gzip'                  # database — then bump DB_REV
npx wrangler pages deploy /tmp/sarvamula_pages --project-name=sarvamula --branch=main
cd app && ./node_modules/.bin/cap copy                      # apps
```

**Always bump `DB_REV` in `app.js` after re-baking the database**, or every cached reader keeps
the old one and the work looks unvoiced.

### The test harness

`/tmp/dom2.js` loads the shipped `normalize.js` + `app.js` + `anusandhana.js` +
`anukramanika.js` in **one scope** (matching the browser's shared global lexical environment)
against a stub DOM, with the real database. It has caught several bugs that header checks could
not. Recreate it rather than guess at reader behaviour — but remember it proves the data layer
only, never rendering.

---

## 9. Known-imperfect

1. **Brackets still voiced in 8 works** — `sutra_bhashya` 8 clips, `gita_tatparya` 5,
   `gita_bhashya` 3, one each in `ath`/`knr`/`isa`/`ait`/`cha`. `_debracket()` is written and
   proven; these need the same in-place treatment (edit the blocks file, recompute those
   hashes, re-render) — **not** a re-segmentation, see below.
2. **Re-segmenting requires chandas detection.** It is optional in `segment_bsb.py` and falls
   back with a warning to stderr. Without `indic_transliteration` installed, 64 correct
   `vasantatilaka`/`upajati` verses silently became `anuṣṭubh`. If you re-segment, verify the
   metre distribution is unchanged.
3. **12 śruti blocks above 30% CER**, 4 above 60% — short blocks whose window caught a
   neighbour's audio.
4. **Trailing throat-clears** survive where they are contiguous with the voice. Energy provably
   cannot detect them; only text can.
5. **The praṇava splice is a single flat exemplar.** Its pitch is dead flat (p10 171.4, p90
   173.9 Hz) where the voice moves ±10 Hz, and the same waveform is spliced at both ends of all
   564 sūtras. Four alternatives sit in `audio/om_preview2/`. The honest fix is three or four
   fresh takes in a human voice.
6. **263 stale files** in the box1 staging dir (never uploaded — the bucket holds only
   referenced objects).
7. **Five probe pages** still in `web/` (`markprobe.html`, `fontformat.html`, `readercheck.html`,
   `stackprobe.html`, `verseprobe.html`), not deployed.
8. **`normalize.js`'s tone-mark fix is not ported** to the Bhāgavatam copies. Dormant there —
   that corpus has no Vedic accents.

---

## 10. Principles that earned their place

* **Measure before fixing.** Nearly every wrong turn here came from acting on a plausible story
  instead of a number. The onset error, the held syllable, the metre regression and the search
  bugs were all found by measuring, and three of them contradicted the obvious explanation.
* **Verify the artefact, not the source.** Read the built APK, the served file, the uploaded
  object. `rclone check`, `unzip -p`, `curl -D -`. Builds and deploys are where the copy you
  reasoned about stops being the copy that ships.
* **A silent fallback is worse than a crash.** Chandas detection warning to stderr, `gate()`
  trimming to 57 ms, `--resume-from` reusing stale clips, `load_blocks` dropping unknown
  content types — every one produced confident, wrong output.
* **Content-address anything derived from text.** It converts a silent staleness bug into a
  cache miss.
* **The recorded material is not reproducible.** Renders can be re-run; a recitation cannot.
  Cut non-destructively, keep the WAVs, and keep the tap timestamps beside the aligned ones —
  `Extra_Recodings/ts_index_rgveda.json` carries all three stages per block for exactly this
  reason.
