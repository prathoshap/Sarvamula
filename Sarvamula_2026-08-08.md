# Sarvamūla audio — 2026-08-08

Continues `Sarvamula_2026-08-02.md`. This session: switched prose to the anuṣṭubh voice,
hardened the ASR-in-the-loop QC until it catches what the ear catches, got **karaoke
working end-to-end on the website for BSB 1.1.1**, fixed a data bug that hid half of
Bhāgavata skandha 10, scoped the full 38-work corpus, and provisioned a fourth box.

---

## 1. Voice + fallback changes

| | before | after |
|---|---|---|
| prose & sūtra reference | `gadya_mbtn` | **`anuṣṭubh`** |
| chandas fallback (855 units) | `upajāti` | **`vasantatilakā`** |

Measured on BSB 1.1.1 (157 clips), the switch is a clear improvement:

```
mean CER   0.051 -> 0.021      perfect 103/157 -> 109/157      flagged 12 -> 7
```

`gadya_mbtn` is now unused (2,398 units on anuṣṭubh). This matches Vāgbodhinī's production
`PROSE_VOICE` setting and the flywheel doc's §6 finding.

**Caveat still open.** All the evidence favouring anuṣṭubh comes from SHORT prose. The one
LONG prose case judged by ear (u02 of 1.1.2) preferred `gadya_mbtn`, and measured globally
anuṣṭubh was not better. `SUTRA_METER`/`PROSE_METER` in `segment_bsb.py` are two constants
to flip back. **Nobody has yet judged long running bhāṣya in anuṣṭubh by ear.**

The vasantatilakā fallback covers 855 units (18%) and is **entirely unsampled**. The ASR
loop cannot check it — a verse chanted in the wrong metre transcribes perfectly.

---

## 2. QC: ASR alone was not enough

Three separate gaps were found and closed, each because the ear caught something the
metric did not.

### 2a. CER misses a dropped first word
A 3-akṣara word missing from a 15-akṣara pada is only 0.12 CER — under the 0.15 threshold:
```
ref: अतो ब्रह्मजिज्ञासा कर्तव्या  ->  asr: ब्रह्मजिज्ञासा कर्तव्या     CER 0.120  MISSED
ref: नच प्रसिद्धार्थं विनाऽन्योऽर्थो  ->  asr: प्रसिद्धार्थं विना…      CER 0.111  MISSED
```
`asr_verify.py` already computed `head_ok`; the loop ignored it. Now flags on
**CER > 0.15 OR head mismatch**, and a head mismatch disqualifies a candidate from winning
even at CER 0.00.

### 2b. ASR verifies PRESENCE, not INTEGRITY
`इति` loses its इ and `एष मोहम्` clips its final म् — both transcribe fine. Added acoustic
edge measures to the selector (`edge_metrics` in `asr_verify.py`), applied **selectively**:

* **onset** — only for vowel/sonorant-initial clips. A voiceless stop legitimately starts
  at its burst; judging those flagged **44% of perfectly good clips**.
* **coda** — **DELIBERATELY DISABLED**, see §2d.

### 2c. `sps` as a third rescue lever
`sps` widens `fix_duration`. Tested on 8 affected clips: codas improve consistently
(tails 4–15 ms → 19–27 ms) but onsets are a **coin flip** (`नाविशेषात्` −28.5→−42.0 better,
`इत्यादि` −35.2→−21.4 worse). So it is a candidate to be SELECTED among, never a global
setting. Now tried alongside seeds and the alternate voice.

**Result:** 15 flagged, **14/15 onsets fixed** — `इति` −22.9→−27.3, `अतो ब्रह्मजिज्ञासा`
−17.3→−41.4.

### 2d. The coda problem is UNSOLVED
A clipped final `म्` is audible but I have no detector for it:
* ASR transcribes it correctly (CER 0.00), and raw hypotheses show final म् rendered fine
  elsewhere (`स्वयम्`, `नियामकम्`, `कर्मवान्`) — so `canon()` collapsing म्≡ं is not hiding it
* its tail is **10.4 ms, ABOVE the 4 ms median** for halant-final clips
* any threshold that flags it flags most healthy clips (`tail<8ms` fires on 62%)

Shipping it would burn GPU on random re-rolls. Needs a better measure (final-nasal murmur
energy?) or an ear. `CODA_CHECK = False` in `asr_qc_loop.py`.

### 2e. Two calibration mistakes worth remembering
* `ONSET_MAX_DB = -30` flagged **31% of everything** — 312 variants, ~40 min of GPU. Killed.
* `-22` looked tidy at 9/157 but **missed the reported clip by 0.9 dB** (`इति` is at −22.9).

Final value **−23.0**, anchored on that clip. *Retune against a clip the ear has judged,
never against a percentile.*

### 2f. Not the gate, not the trim — the model
Rendering the affected clips ungated proved onsets are **identical gated vs ungated**
(−29.4/−29.4, −31.6/−31.6, −42.2/−42.2), and ungated codas end with **0 ms of tail**. The
model itself omits these; no post-processing setting recovers them, which is why selection
is the only lever.

---

## 3. Karaoke — working end-to-end on the site

**BSB 1.1.1 is live at `#/w/sutra_bhashya/0`** — 7 parts, 10.94 min, **157 pāda-level
karaoke lines**, click-to-seek.

Design is Bhāgavatam's, not invented: display lines are baked at BUILD time and timings
reference line indices. I had started a character-offset aligner to map audio onto flowing
prose; that was the wrong approach and was dropped.

```
audio(work, block, part, path, dur, kind, ref, seq, lines)   lines = JSON [{t,k}]
audio_timings(work, block, part, segs)                        [{s,e,ln:[i]}]
```

Three refinements over the first cut, all from listening:
1. **One line per PADA, not per unit.** A padya unit can be 24 padas — lighting the whole
   unit was a wall of text. `p1` went from 3 segs to 33.
2. **Verse and prose set differently** — verse as indented pādas with a rule, prose as
   flowing clauses. Hence lines are JSON `[{t,k}]`: the KIND must travel per line.
3. **Daṇḍas restored** at build time (`।` at a hard boundary, `॥` ending a verse), since
   the cleaner strips them before TTS.

### Three transport traps — none of them in the JS
Seeking appeared broken for two rounds and the JS was innocent every time:
1. **`-movflags +faststart` is REQUIRED.** Without it `moov` sits after `mdat` and the
   browser cannot seek — `currentTime` is ignored and playback restarts at 0. Now in
   `assemble_bsb.encode()`.
2. **`serve.py` ignored HTTP Range**, answering 200 with the whole file. Now 206 / suffix
   ranges / 416. R2 does this natively, so dev-server-only.
3. **`.m4a` → `audio/mp4a-latm`** by Python; corrected to `audio/mp4`.

Then a **cached pre-faststart copy** masked the fix — hence `AUDIO_REV`, bumped on any
audio change.

---

## 4. Data fix — Bhāgavata skandha 10 pūrvārdha was invisible

Reported as "10th skandha pūrvārdha is not on the website". **The text was never missing** —
adhyāyas 1–49 hold 245,583 chars, matching the source IDML's 236,937 (the excess is
headings the ingest adds).

The bug was four misplaced markers: both half-skandha headings AND both closing colophons
sat bunched at seq 10678–10683 **before any content**. The reader chapters on
`Skandha_Heading`, so:

```
before:  दशमस्कन्धः  3 rows   |  दशमस्कन्ध उत्तरार्धः  5261 rows
after :  दशमस्कन्धः  2384     |  दशमस्कन्ध उत्तरार्धः  2880    (2384+2880 = 5264 ✓)
```

Fixed with **`BLOCK_MOVES`** in `build_db.py`, following the existing `CT_FIXES` pattern:
each move asserts the block's `content_type` AND a text prefix, so a data shift fails loudly
rather than silently relocating the wrong block. `CT_FIXES` is now keyed on SOURCE seq so
the two do not interfere. Source JSONs untouched; `--raw` still reproduces the original.

Backup: `web/sarvamula.db.bak-preskandha10`. The rebuild drops the `audio` tables — re-run
`build_audio_db.py` after. No analytics reference this work, so no deep links broke.

---

## 5. Corpus scope — 38 works, 4.13 M chars

| group | works | chars | padas | GPU-h | audio |
|---|---|---|---|---|---|
| **A** `Mula`+`Sarvamula` — BSB shape, **pipeline works today** | 13 | 919 K | 21.8 K | **48.5** | 28.3 h |
| **B** `Sarvamula` only — needs a segmenter variant (no Mula pairing) | 24 | 1.33 M | 31.5 K | 70.0 | 40.8 h |
| **C** `bhagavata_tatparya` | 1 | 1.88 M | 44.7 K | 99.3 | 57.9 h |
| | | | | **218** | 127 h |

**218 GPU-h — 36 h on 6 GPUs, 54 h on 4. Not one night.**

Three things to decide before committing:
* **Group C is 46% of the corpus and probably redundant** — its 16,017 `Bhagavatam` entries
  are the Bhāgavata mūla verses the Bhāgavatam project already renders. Check whether that
  audio can be reused before spending 99 GPU-h.
* **Group B needs code** — no `Mula`, so block-pairing does not apply. Test on `mbtn` (the
  largest) before committing 70 GPU-h.
* **QC is serial and single-GPU.** ASR ran 0.76 s/clip → **~4.6 h for Group A alone**, on
  box 1 only (that is where Su-shrota lives). It follows rendering; it does not overlap.

Layout: `/home/ece/BigDisk/Prathosh/sarvamula_audio/works/<slug>/{clips,stage,qc}/`
(862 GB free). Grantha-by-grantha, independently resumable — content-addressed clip ids
mean a re-run skips completed work.

---

## 6. Fleet

| box | GPUs | state |
|---|---|---|
| box 1 `ece-box` `.96` | 2 | ready — ASR lives here; `/home` 99% full, work on `BigDisk` |
| box 4 `ece-box4` `.162` | 2 | ready |
| box 2 `ece-turing` `.103` | 2 | **provisioned today**, GPUs busy (another user) |
| box 3 `ece-box3` `.180` | 2 | **offline** — no ping, no ARP entry |

**Turing provisioning (new).** Copied box 1's environment over the **LAN**, not the VPN:
8.3 GB conda env + 1.4 GB IndicF5 + 3.6 GB BigVGAN + `production/` + `CHAMPION_2026-06-11/`.
The env sits at the **same absolute path** as on box 1 so its hardcoded shebangs resolve,
and the layout mirrors box 1 so `PROD_ROOT` defaults work with no per-box env vars.
Verified: torch 2.4.1+cu121, CUDA sees 2 devices, `prep_text`/`bigvgan`/`f5_tts` import,
`vocab.txt` resolves.

Snags: turing's `known_hosts` had a **stale host key for box 1** which silently killed the
first transfer; and `/home/ece/hdd/Prathosh_prod` is owned by user `prathosh` and read-only
to `ece`, hence the parallel tree under `ece`'s home. Turing is **shared** — a long run can
be crowded out mid-flight; `--resume-from` covers that.

Box 3's password is not the issue: SSH fails at *connect* (`Operation timed out`), never
reaching auth, and there is no ARP entry. It needs a physical check.

---

## 7. Open items

**Needs an ear (blocking a corpus run):**
1. **Long prose in anuṣṭubh** — the whole prose-voice decision rests on short-fragment
   evidence. `VA_BSB_1.1.1_p2` is the test.
2. **Quoted verse in vasantatilakā** — 855 units, unsampled, and the ASR loop is blind to it.
3. **A vs B** (0.55 s inter-pada gap) — still undecided; both come from the same clips, so
   deferring costs nothing.

**Known unsolved:**
4. **Clipped final म्** — no detector (§2d).
5. `head_ok` false-positives on anusvāra-before-velar (`यं क` → `यङ्क` is normal ASR sandhi),
   so a few clips get retried for nothing.

**Not started:** nothing on R2 (bucket `sarvamoola` still empty); Group B segmenter; any
work beyond BSB.

---

## 8. Files changed today

| path | what |
|---|---|
| `audio/segment_bsb.py` | `SUTRA_METER`/`PROSE_METER` → anuṣṭubh; `FALLBACK_METER` → vasantatilakā |
| `audio/asr_verify.py` | `edge_metrics()` (onset/coda, text-gated); `head_ok` equal-length fix |
| `audio/asr_qc_loop.py` | flag on CER **or** head/edge; acoustic `penalty()`/`score()`; `sps` lever; alternate voice follows `PROSE_METER` |
| `audio/assemble_block.py` | one seg per **pada**; `PADA_GAP_SOFT` |
| `audio/assemble_bsb.py` | `+faststart` in `encode()`; `--pada_gap` |
| `audio/build_audio_db.py` | **new** — bakes `audio`/`audio_timings`; per-pada lines with daṇḍas + kind |
| `web/app.js` | `audioHTML`/`svLoad`/`svAt`/`svSeek`/`svKaraoke`; `AUDIO_BASE`+`AUDIO_REV` |
| `web/index.html` | verse/prose karaoke styles (light + dark) |
| `web/serve.py` | HTTP Range (206/suffix/416); `.m4a` → `audio/mp4` |
| `build_db.py` | **`BLOCK_MOVES`** + `CT_FIXES` keyed on source seq |

---

## 9. The corpus run — BSB and Anuvyākhyāna both finished

Both works are rendered, QC'd, assembled, and baked into the reader's DB.

| | BSB | Anuvyākhyāna |
|---|---|---|
| blocks | 564 adhikaraṇa+sūtra | 124 adhikaraṇa |
| units (ślokas / clauses) | 3 257 | 1 892 |
| padas rendered | **5 403 / 5 403** | **3 921 / 3 921** |
| playable files | 1 135 | 203 |
| audio | 6.46 h | 5.58 h |
| ASR perfect (CER 0) | 3 671 (68 %) | 2 593 (66 %) |
| flagged | 236 | 23 |
| rescued by re-roll | 154 | 16 |
| left as rendered | 82 (69 still > 0.15) | 7 |

**QC ran CER-only** (`--no-edge`). The acoustic onset penalty stays in the code but is off:
it flagged 793 BSB clips, and every one inspected was a voiceless-stop burst, not a
truncation. Rescue is round-based with early exit — try one alternate seed for everything
still failing, re-ASR, drop whoever passed, and only then move to the next seed. That cut
the BSB rescue from ~5 958 renders to 277.

Anuvyākhyāna needed **an order of magnitude less rescuing than BSB** (0.6 % vs 4.4 %
flagged). It is almost entirely anuṣṭubh verse; BSB's flag rate is carried by prose.

### The 24 clips that should never have existed

Rendering stalled at "24 left". They were not slow — they were **unrenderable**: padas
consisting of a bare closing quote (`”`, `’`) stranded by a daṇḍa split, with zero
akṣaras. `clean()` now strips curly quotes and `split_sloka()` drops any pada with no
akṣara. Re-segmenting dropped those and, because pada indices shift, changed 420 clip ids;
those 420 were rendered on six GPUs in about ten minutes.

### Two sūtras numbered 2/4/10

The edition gives **two different sūtras the same ref 2/4/10**, so both blocks minted the
id `bsb_2_4_10` and the second's `.m4a` silently overwrote the first's — 1 135 timing rows
but only 1 133 files on disk, with two sūtras sharing one recording. A ref is not a unique
key. `segment_bsb.py` now tags repeats before ids are minted: the printed ref stays
`2/4/10` (the reader shows it) while the id and file stem take a letter —
`bsb_2_4_10b` / `BSB_2.4.10b.m4a`. Only 10 clips changed id; the wavs were copied to the
new names rather than re-rendered, since the content hash proves the text is identical.

### Anuvyākhyāna in the reader

The reader hung the player off `Mula` rows. Anuvyākhyāna **has no Mula** — every entry is
Sarvamula — so nothing rendered. `block()` now asks the `audio` table instead of assuming
Mula, and the part label is driven by `audio.kind` (`सूत्र` / `भाष्य n` / `अनुव्याख्यान n`).
An Anuvyākhyāna block keys on the seq of the **first entry of its adhikaraṇa**.

### Box 3 came back, with a shadowed environment

`.180` is reachable again. Its renders died twice on `~/.local` shadowing the conda env:
`appdirs` missing for `wandb`, then `huggingface_hub` **1.24** (vs the env's 0.36.2)
breaking `BigVGAN.from_pretrained` with a `_from_pretrained() missing … 'proxies'` error.
Fix is `export PYTHONNOUSERSITE=1` in `render_node.sh`. Its shards were moved to box 4
rather than waiting on the diagnosis.

## 10. Files changed since §8

| path | what |
|---|---|
| `audio/segment_anu.py` | curly-quote strip in `clean()`; akṣara guard in `split_sloka()`; part `kind` → `vyakhyana` |
| `audio/segment_bsb.py` | duplicate-ref disambiguation (`dup` tag → `bsb_2_4_10b`, `BSB_2.4.10b.m4a`) |
| `audio/build_audio_db.py` | `--work` flag — no longer hardcoded to `sutra_bhashya` |
| `web/app.js` | audio attaches to any row with an `audio` row, not just `Mula`; kind-driven part label |
| `<box>/render_node.sh` (box 3) | `PYTHONNOUSERSITE=1` |
