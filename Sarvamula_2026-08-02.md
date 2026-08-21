# Sarvamūla audio — 2026-08-02

BSB (Brahmasūtra Bhāṣya) chant-TTS. This session traced every "syllables are missing"
complaint to its cause, removed gating entirely, fixed four segmentation bugs, and
generalized the pipeline to all 564 sūtras. **BSB 1.1.1 and 1.1.2 are approved by ear.**

Previous: `work_so_far_2026-07-22.md` (reader/search), `RESUME.md` (project state).

---

## 1. The clipped-syllable saga — three causes, all ours

Every instance of "the first syllables are cut" turned out to be our own post-processing
or segmentation, never the model. They were found in this order, each hiding the next.

### 1a. `gate()` assumed every onset is a stop burst

`gate()` in `render_batch.py` trimmed to speech bounds by finding the first 20 ms frame
over `voice=0.08`, back-walking while over `sil=0.012`, keeping 30 ms lead, then fading
in from **zero** over 15 ms. Right for a stop, which has a real silent closure. Wrong for
anything that **ramps in** — vowels, semivowels य/व/र/ल, nasals.

Measured on u05 `यतो` with `--dump_raw`: old gate started at 290 ms, fixed at 170 ms; the
discarded 120 ms measured RMS −27.7 dBFS, **peak −13.9 dBFS**. Two independent
confirmations — simulated start delta = shipped duration delta = exactly 120 ms.

The real boundary is **stop vs sonorant, not consonant vs vowel** (which is why य slipped
through). The `fric` branch already existed for ś/ṣ/s/h — `render_production.py:246`
documents `स्तुहि → "tuhi"` — sonorants were simply never added.

**This retired the ॐ primer**, which had been a workaround for it all along.

### 1b. The same bug again, per-pada

The fix classified the onset **once from `padas[0]`** and applied it only to segment 0
(`soft=(soft and i == 0)` — the original code's shape, preserved when renaming). But each
pada is a separate generation. So every pada *after the first* was hard-gated regardless
of its onset: **1,498 padas, 26.8% of the corpus**, plus 630 halant-final padas losing
their closing stop for the mirror reason. This is what cut `अथातो`, `अथ शब्दो`, `अतः शब्दो`
in bsb_1_1_1. Fixed to per-pada `softs[]`/`halants[]`.

### 1c. Decision: no gating at all

Rather than keep patching, gating is **off** (`--no_gate`). The cost is real and measured —
F5's own padding (0.32 s and 0.36 s, *uneven*) no longer gets normalized, so `--gap` is no
longer authoritative — but it removes the whole class of bug.

### 1d. The trim that remained

With gating off, `trim_lead()` in the assembler still ran at **−45 dB** — and on **14 of 67
clips** removed audio *above* that, worst peak **−33.5 dBFS**: the ramp-in of न/य/अ. The same
failure, relocated downstream. (Found only after auditing all 67; a single-clip check had
looked clean.)

Fixed by threshold. F5 padding measures ~−80 dB, onsets sit at −33…−38 dB, so **−65 dB**
lands in the empty band: still removes ~222 ms of padding on average, and across all 67
clips the loudest thing it removes is **−52.7 dB**. Do not raise it.

---

## 2. Segmentation rules (`segment.py`, `segment_bsb.py`)

- **R1** sūtra: strip editorial `[ॐ]`, keep the ॐ (then removed for TTS, spliced back).
- **R2** gadya: break after every visarga → the model's learned visarga echo.
- **R3** every quoted `“…”` verse is its own unit.
- **R4 (new)** hard breaks on `, ; । ॥` and the `_ _ _` lacuna:
  ```python
  _BREAK = re.compile(r"[।॥,;]|_[\s_]*")
  ```
  Commas were never split points, and `clean()` began with `re.sub(r"[_]+"," ",t)` — so the
  edition's lacuna became a space and **silently welded RV 7.99.1 to 7.99.2** across a gap the
  editor marked as elided. The split now happens before `clean()` can flatten it.
- **R5 (new) `depranava()`** — the model **cannot voice a lone ॐ** (it collapses to ~1.2 s of
  mush, heard at the head of bsb_1_1_1's maṅgala). Each of BSB's 16 pādas opens its bhāṣya
  with a bare ॐ pada; those **16 padas** are dropped before TTS. Per user decision the
  exemplar is **not** spliced back — the sūtra file already closes on a pranava, and the
  exemplar measured **+7.6 dB louder (RMS)** than the speech after it, masking the opening
  word.
- **R6 (new) unquoted-verse promotion** — R3 only marks *quoted* text as verse, so the maṅgala
  śloka opening each pāda's bhāṣya arrived as `gadya` and was split **at visargas**, cutting
  `सर्वै`/`रुदीर्णं` mid-pāda and chanting it against the prose reference. In this edition `॥`
  delimits verses, so each `॥`-span is tested separately (testing the whole chunk detects
  nothing, since it holds verse *and* the prose after it). **4 spans promoted** corpus-wide:
  the maṅgala, BSB's concluding śārdūlavikrīḍita `यस्य त्रीण्युदितानि…`, and the closing maṅgala.
  Guarded: `tts_meter` identifies anuṣṭubh by syllable count alone, so 32-syllable prose
  matches — an anuṣṭubh span is promoted only if daṇḍa-split into hemistichs. Without that
  guard it fired on 53 spans, nearly all prose.
- **R7 (new) short-pada merging** — R2 manufactures fragments the model cannot render:
  **38% of padas were ≤12 akṣaras, 46 of them a single akṣara**. A ~1 s target against a
  ~7.6 s reference is the regime that garbled `इति स्कान्दे` and swallowed
  `तच्चोक्तं स्कान्दे`. Prose padas below 12 akṣaras now merge into a neighbour
  (**38.1% → 25.0%**). **Verse padas are exempt** — a pāda is the unit of recitation.

### Meter policy

```
sutra          -> gadya_mbtn
gadya (prose)  -> gadya_mbtn
padya (quote)  -> chandas detection; fallback upajāti
```

`gadya_mbtn` **everywhere** as of 2026-08-02, judged on u02 (real bhāṣya prose, the case that
generalizes) after winning on u04 and u05. Plain `gadya` is now unused.

**Silent-failure bug found here:** `tts_meter` emits ASCII names, the bank is keyed IAST.
`render_core`'s LUT also registers each wav *stem*, covering most ASCII names — but **not
`anuṣṭubh`, whose wav is `anu_v094.wav`**. Unaliased, the commonest metre in the corpus
resolved to nothing and the renderer silently substituted the fallback. Fixed with
`METER_ALIAS` plus a `BANK_KEYS` assertion.

### Content-addressed clip ids

```
bsb_1_1_1_u02_padya_37579e        <- trailing sha1(text+meter)[:6]
```
Unit numbers are **not** stable across re-segmentation: promoting one verse in bsb_1_1_1
shifted every later unit, leaving **44 of 59 clips with an unchanged id but different text**.
`--resume-from` would have silently served stale audio across a 12-hour run. With the hash,
changed text yields a new id, so stale clips are simply absent and get re-rendered while
unchanged ones still hit the cache. (Only 3 clips actually needed re-rendering, not 69.)

Caveat learned: this broke `cid.rsplit("_",1)[-1]` type parsing — the sūtra framing silently
vanished (`BSB_1.1.2_sutra.m4a` came out 1.6 s instead of 3.2 s). Use `clip_type()`.

---

## 3. Scale

```
blocks   564      all 564 sūtra refs parse, 0 failures
units  3,257      = clips
padas  4,846      = TTS calls
files  1,135      564 sūtra + 571 bhāṣya
```

| | median | p90 | max | total |
|---|---|---|---|---|
| sūtra files | 4 s | 6 s | 13 s | 0.69 h |
| bhāṣya files | 29 s | 68 s | 162 s | 5.60 h |

**GPU: 11.0 h on one A6000 → ~1.8 h across the fleet's 6.** Audio 6.28 h; ~400 MB as AAC.

Duration model refit on 67 real clips — duration tracks **akṣaras**, not pada count:
```
speech = 0.2166*aksharas - 0.358*padas     R2 0.9969, mean |err| 0.59s
```
An earlier per-pada model (3.838 s/pada) was off by a mean 3.21 s and up to −42 % on blocks
full of short units. `assemble_bsb.py` warns when any real duration lands >25 % from estimate.

---

## 3b. ASR-in-the-loop QC (2026-08-05) — the QC mechanism

Su-shrota v12-ep9 grades every clip against its source text; anything over CER 0.15 is
re-rendered with alternate seeds **and** the alternate voice, and the lowest-CER candidate
wins. This replaced acoustic onset detection, which could not tell a dropped phoneme from
a legitimate voiceless-stop burst — it called `प्रसिद्धत्वात्` truncated when the प्र was
present and the word was mangled mid-way instead.

```
model  /home/ece/BigDisk/Prathosh/ASR/exp/ft_ctc_v12/ft_ctc_ep9.nemo   (PIN this, not
       ft_ctc_current.nemo — the symlink repoints on deploy)
env    /home/ece/BigDisk/Prathosh/ASR/envs/nemo_ai4b/bin/python
```
Decode the CTC head on the Sanskrit slice (`OFF,V,BL = 4096,256,5632`); add a **0.3 s
silence pre/post-roll** or the ASR's own onset clipping is misread as TTS truncation.

**BSB 1.1.1 result (157 clips): median CER 0.000, 103 perfect, 12 flagged, 12 rescued —
all to CER 0.00.** Rescued by `anuṣṭubh` ×8, alternate seed ×4.

The 8 voice-wins were all short prose (`इति`, `तच्च`, `उक्तं च गारुडे`). That is the
flywheel doc's §6 finding reproduced — the gadya voice drops word-initial syllables — but
it only holds for SHORT prose: measured globally, anuṣṭubh was no better (its own CER was
comparable), so a blanket `PROSE_VOICE` swap would have been wrong. Per-clip selection is
the right resolution, and it keeps the gadya_mbtn character the ear preferred.

Runs entirely on `ece-box` (both envs). Working dir is **`/home/ece/BigDisk/Prathosh/
sarvamula_audio/`** — `/home` is at 99% (7.8 GB) while BigDisk has 863 GB.

---

## 4. Delivery

Adopted from the Bhāgavatam player: R2 with **URLs derived from structure** (no manifest),
`AUDIO_BASE` + `AUDIO_REV`, persistent player bar, **gapless** dual-`<audio>`, Cache-API
offline download, and **karaoke timings baked into the bundled DB**.

**Sūtra and bhāṣya are separate files.** They are separate DB rows (`Mula` / `Sarvamula`) and
separate blocks in the reader, so one file each restores the 1 entry = 1 file mapping the
player assumes:
```
sutra_bhashya/1/1/BSB_1.1.2_sutra.m4a      sutra_bhashya/1/1/BSB_1.1.2.m4a
sutra_bhashya/1/1/BSB_1.1.1_p3.m4a         (long blocks only)
```
**AAC, not opus** — opus in `<audio>` is unreliable on iOS/Safari and the reader ships as an
iOS app.

Only **3 of 564** blocks split into parts, breaking where Madhva resumes his own prose after a
citation (the `S g P g P` rhythm). `bsb_1_1_1` is 6 parts. A tail under 20 s folds back.

**bsb_1_1_1's sūtra uses the hand-approved `sutra_1_1_1_final.wav` verbatim** (`PREBUILT`,
keyed on the content hash so it detaches if the text ever changes) — the first-sūtra rule,
two leading pranavas with the integral one running tight into `अथातो`.

### Karaoke — WORKING end-to-end on BSB 1.1.1 (2026-08-07)

I started building a character-offset aligner to map audio onto the flowing prose. That was
the wrong approach: **Bhāgavatam bakes display lines at BUILD time** (`text_dev` split on
`\n` into `<span class="ln" data-i="N">`) and its `timings.segs` reference those line
indices, so karaoke is just a class toggle. No alignment, nothing lossy. Same shape here.

`build_audio_db.py` bakes two work-scoped tables into `sarvamula.db`:
```
audio(work, block, part, path, dur, kind, ref, seq, lines)   lines = JSON [{t,k}]
audio_timings(work, block, part, segs)                        [{s,e,ln:[i]}]
```
Deviation from Bhāgavatam: lines are JSON `[{t,k}]` rather than `\n`-joined text, because
each line's KIND must travel with it — verse is set as indented pādas, prose as flowing
daṇḍa-terminated clauses. Daṇḍas are restored at build time (`।` at a hard boundary, `॥`
ending a verse) since the cleaner strips them before TTS.

**One line per PADA, not per unit.** A padya unit can be 24 padas; lighting the whole unit
was a wall of text. Since every pada is its own clip the seg boundaries are exact, not
interpolated. BSB 1.1.1 = 157 display lines, one seg each. Clicking a pāda seeks to it.

Reader: `audioHTML`/`svPlay`/`svSeek`/`svKaraoke` in `web/app.js`, styles in `index.html`.
`AUDIO_BASE` overridable via `localStorage.sv_audio` (default `audio/`), plus `AUDIO_REV`
— exactly Bhāgavatam's arrangement, so pointing at R2 is a one-line change.

**Three transport traps, all real, none in the JS** (seeking looked broken for two rounds):
1. **`-movflags +faststart` is REQUIRED.** Without it moov sits after mdat and the browser
   cannot seek — `currentTime` is ignored and playback restarts at 0. Now in `encode()`.
2. **`serve.py` ignored HTTP Range**, answering 200 with the whole file, so seeking was
   impossible locally. It now implements 206 / suffix ranges / 416. R2 does this natively,
   so this was dev-server-only.
3. **`.m4a` mapped to `audio/mp4a-latm`** by Python; corrected to `audio/mp4`.
Cached pre-faststart copies then masked the fix — hence `AUDIO_REV`.

The **tānpūrā drone is not carried over** — suits verse, may fight prose.

---

## 5. The fleet

| box | alias | GPUs | disk free | state |
|---|---|---|---|---|
| `.96` | `ece-box` | 2× A6000 | **8 GB** ⚠ | ready |
| `.180` | `ece-box3` | 2× A6000 | **322 GB** | ready — **needs `PYTHONNOUSERSITE=1`** |
| `.162` | `ece-box4` | 2× A6000 | 23 GB | ready |
| `.103` | `ece-turing` | 2× A6000 | 91 GB | **unusable** — no `indicf5` env, no IndicF5 weights |

Key auth installed on all reachable boxes; renderer md5 identical across the three usable
ones. **Renders are bit-identical across machines** (verified), so sharding is safe and
reproducible. Point bulk output at box 3 — box 1 has only 8 GB free.

Box 3 gotcha: a stray `~/.local/lib/python3.10/site-packages/wandb` with a missing `appdirs`
leaks into the conda env; `PYTHONNOUSERSITE=1` fixes it with no installs.

Other gotchas: **`--outdir` does not create its directory** (every clip fails at write —
silently, if you only grep for `DONE`); **`speed` is a no-op whenever `sps > 0`** (`speed=0.80`
produced a bit-identical render); `nohup … &` over SSH does not detach without
`< /dev/null` and `ssh -n -f`.

---

## 6. Open items

**One decision gates the corpus run:**
- **Variant A vs B** — A keeps the 0.55 s inter-pada gap; B adds nothing and lets the model's
  own padding be the pause. B was approved for content on bsb_1_1_1 p1; A vs B as a *rhythm*
  choice is still open. A totals 12.50 min on the smoke blocks, B 11.65 min.

**Largest remaining risk:**
- **1,116 short padas are whole units** (`इति`, `न`, `इति चोपरि` between quoted verses) —
  nothing to merge with, and folding prose into an adjacent verse would be wrong. This is the
  same regime that garbled `इति स्कान्दे`. `sweep_u04.py` rendered the levers
  (`sps=0.35/0.45`, `spsFREE`, short reference); **none judged**, so nothing was applied to
  1,116 clips. Decide before committing 11 GPU-hours.
- **855 quotations (74 % of padya units) fall back to upajāti** because chandas detection needs
  a complete verse; 629 are single-pada fragments. Worth sampling.

**Smaller:**
- Ṛgveda mantras render as upajāti; Vedic svara not attempted.
- `render.py:292` / `render_production.py:305` still carry the old `fric` predicate (separate
  entry points, unused by the batch path).
- `vagdhenu/src/render_core.py` is patched but **uncommitted**.
- Nothing uploaded to R2 (bucket `sarvamoola` still empty); no app integration; only BSB is
  segmented — the other 37 works are untouched.

---

## 7. Files

**New**
| path | what |
|---|---|
| `audio/segment_bsb.py` | whole-BSB segmentation; meter policy, aliases, `OVERRIDES`, verse promotion, short-pada merge, part splitting, content-addressed ids, R2 paths |
| `audio/build_shard_bsb.py` | corpus shards; `--shards N` (balanced by pada count), `--resume-from` |
| `audio/assemble_bsb.py` | corpus assembly → staged R2 tree + timings + `--sql`; `PREBUILT` |
| `audio/assemble_block.py` | single-block assembly; `assemble_units()` shared core, `--timings` |
| `audio/defade.py` | repairs `gate()`'s fade on already-rendered clips |
| `audio/sweep_u04.py` | diagnostic sweep for tiny connectives (seed / sps / reference) |
| `audio/blocks_bsb.json` | all 564 segmented blocks |

**Changed**
| path | what |
|---|---|
| `render_batch.py` (3 boxes) | `soft_onset()`, **per-pada** `softs`/`halants`, `--no_gate` |
| `audio/segment.py` | R4 breaks, `depranava()`, `raw` retained for verse promotion |
| `audio/build_shard.py` | superseded by `build_shard_bsb.py` for corpus work |

**Approved audio** — `bsb_1_1_2_smoketest/VB_BSB_1.1.1_p1.m4a` and the `VA_`/`VB_` set;
`sutra_1_1_1_final.wav`.

## 8. Running it

```bash
cd /Users/prathosh/Sarvamula/audio
.venv/bin/python segment_bsb.py --out blocks_bsb.json
.venv/bin/python build_shard_bsb.py --shards 6 --resume-from clips

# one process per GPU across the three usable boxes; box3 needs PYTHONNOUSERSITE=1
ssh -n -f ece-box3 'cd ~/Prathosh/production && mkdir -p ~/Prathosh/sarvamula_try/clips && \
  PYTHONNOUSERSITE=1 CUDA_VISIBLE_DEVICES=0 nohup python render_batch.py \
    --shard …0.json --results r0.json --outdir ~/Prathosh/sarvamula_try/clips \
    --dump_raw ~/Prathosh/sarvamula_try/raw --no_gate > l0.log 2>&1 < /dev/null &'

.venv/bin/python assemble_bsb.py --clipdir clips --outdir r2_stage --sql timings_bsb.sql
```
`--dump_raw` writes the un-gated concat **without** inter-pada gaps — that is variant B, free
from the same render. It is also what made the gate bug provable.
