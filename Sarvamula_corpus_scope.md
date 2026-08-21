# Sarvamūla audio — corpus scope (2026-08-08)

> **Superseded in part.** MBTN was already rendered in full for the YouTube series
> (`ece-box:/home/ece/BigDisk/mbtn_prod`, 32 adhyāyas, 10,220 hemistich clips over 5,179
> verses, 100 % text-matched) and is **reused as is** — hemistich karaoke, not pāda.
> That removes 36 GPU-h, bringing the remaining budget to **~104 GPU-h**.
> Live per-grantha state lives in `Sarvamula_grantha_status.md` (generated).

Two works are finished (BSB, Anuvyākhyāna: 9,324 padas, 12.04 h audio). This scopes the
remaining 36 against **measured** rates rather than estimates.

## Calibration — measured, not guessed

| constant | value | source |
|---|---|---|
| audio per akṣara | **0.2395 s** | BSB 0.242, Anuvyākhyāna 0.237 — stable across prose and verse |
| GPU per akṣara | **0.47 s** | 5,403 + 3,921 padas rendered; ~2× real time |
| akṣaras per pada | **19.5** | BSB 17.8 (prose-heavy), Anu 21.6 (verse) |
| ASR-QC per clip | **0.76 s** | single GPU — Su-shrota lives only on box 1 |
| flag rate | 4.4 % prose / 0.6 % verse | rescue costs ≈ 2 extra renders per flagged clip |

Akṣara count is the honest unit: it predicts audio length, GPU time and pada count at once.
Headings, titles and subject lines are excluded — they are structure, not recitation.

## The corpus, by shape

| shape | works | akṣaras | padas | GPU-h | audio |
|---|---|---|---|---|---|
| **A** — `Mula` + `Sarvamula` | 12 | 339 K | 17.4 K | 44.3 | 22.6 h |
| **B-verse** — numbered ślokas, no `Mula` | 14 | 320 K | 16.4 K | 41.8 | 21.3 h |
| **B-prose** — prose commentary, no `Mula` | 9 | 249 K | 12.8 K | 32.6 | 16.6 h |
| **C** — `bhagavata_tatparya` (Tātparya only) | 1 | 163 K | 8.3 K | 21.3 | 10.8 h |
| **remaining** | **36** | **1.07 M** | **55.0 K** | **140** | **71.3 h** |
| done (BSB + Anuvyākhyāna) | 2 | 182 K | 9.3 K | 23.8 | 12.0 h |

### Group C collapsed — 99 GPU-h recovered

`bhagavata_tatparya` was scoped at 99 GPU-h because of its 16,017 `Bhagavatam` mūla
entries. **All 16,017 are verbatim in the Bhāgavatam project's corpus**, which already has
rendered audio *and* karaoke timings (`bhagavatam.db timings`, 16,017 rows). Only Madhva's
Tātparya prose — 163 K akṣaras — needs the GPU. The work here is a **bridge**, not a
render: match verse → reuse its audio id → interleave with newly rendered Tātparya.

## Code needed — three segmenters, not one

`segment_bsb.py` (shape A) and `segment_anu.py` (B-verse) each hardcode one work.

1. **Shape A generalisation** — per-work ref parsing (`sutra_ref()` is BSB-specific) and
   per-work `Mula` semantics. In BSB the `Mula` is a sūtra; in the Upaniṣad bhāṣyas it is
   **śruti**, and in `gita_*` it is the Gītā verse. Whether śruti should be chanted with
   svara rather than run through the śloka voice is an open question — VedaVāṇī exists for
   exactly this and may be the better source for `rg_bhashya`'s 455 ṛks.
2. **B-verse generalisation** — `_VNUM` matches `॥ १५६ ॥` only. **mbtn numbers its ślokas
   `॥ १९/९६॥`** (adhyāya/verse), so the regex matches *nothing* there and the whole work
   would fall into one unsplittable śloka. mbtn is 278 K akṣaras — 26 % of the remaining
   corpus — so this one regex gates the largest single job.
3. **B-prose — does not exist yet.** No `Mula` to pair and no verse numbers to split on,
   with entries up to **23,836 akṣaras** (kanva_bhashya seq 14 is a 47 K-character prose
   blob). Blocks must be cut on headings and size, not on entries. Needs BSB's unit builder
   without the pairing, plus a block-splitting rule. ~250 K akṣaras ride on it.

**Classification caveat:** shapes were assigned by verse-number density, and `is_padya` in
the DB is unreliable — it flags kanva_bhashya's 47 K-character prose entry as verse. Two
works with no numbering are genuinely verse (`krshna_amrta_maharnava`, a stotra;
`dvadasha_stotra`) and are mis-binned as B-prose. Each work needs a one-look confirmation
before it is queued; metre detection on a sample is the cheap test.

## Wall clock on the fleet

* **Render** 140 GPU-h ÷ 6 GPUs (box 1, 3, 4 × 2) ≈ **23 h**, but box 3 is shared and
  needs `PYTHONNOUSERSITE=1`; box 5's driver is broken (NVML mismatch).
* **QC** 55 K clips × 0.76 s ≈ **11.6 h, serial on box 1** — Su-shrota is installed nowhere
  else. This is now the *second* bottleneck after rendering. Installing the ASR env on
  box 4 would halve it.
* QC of work *n* overlaps the render of work *n+1*, so grantha-by-grantha ordering matters:
  queue mbtn (36 GPU-h) first so its QC has something to overlap.

Realistic: **two nights**, not one — and only after the three segmenters land.

## Delivery

Audio is served from **Cloudflare R2** (`sarvamoola`, currently empty). Uploading from the
Mac is not viable: the VPN link runs at ~0.23 MB/s versus 11 MB/s box-to-box, so pulling
71 h of audio to the Mac would take ~9 h. Upload must originate on box 1, which needs an
R2 token there — a **write-only token scoped to the bucket**, not a copy of the Mac's
rclone credentials.

Local `web/audio/` stays a smoke-test mirror only.

## Order of work

1. **mbtn** — reuse the existing hemistich clips (0 GPU-h); render only the ~3 % colophon
   gap. Needs an alignment pass, not a render.
2. B-prose segmenter → kanva, aitareya, chāndogya (204 K akṣ)
3. Shape A generalisation → gita_bhashya, gita_tatparya, rg_bhashya (236 K akṣ)
4. Bhāgavatam bridge for `bhagavata_tatparya` (no GPU for 714 K akṣ)
5. The 20 small works (< 8 K akṣ each) — one batch, ~4 GPU-h total
