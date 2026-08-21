# Grantha scope — Bhāgavata Tātparya Nirṇaya (`bhagavata_tatparya`)

The largest work in the corpus (18,483 entries, 1.89 M characters) and the only one whose
bulk is **already recited**. Scoped 2026-08-08.

## Shape: A, not B-prose

The status table bins this as B-prose because it has no `Mula` content type. That is a naming
artefact — structurally it is **exactly BSB's shape**: a mūla verse followed by Madhva's
commentary on it, verse by verse.

```
Bhagavatam  1/1/1   198 chars      <- mūla verse      (= BSB's Mula)
Tatparya    1/1/1  2985 chars      <- commentary      (= BSB's Sarvamula)
Bhagavatam  1/1/2   204 chars
Tatparya    1/1/2  1074 chars
Bhagavatam  1/1/5    80 chars      <- most verses carry no Tātparya
```

12 skandhas · 345 adhyāyas · 16,017 verses · **1,366 Tātparya notes (8.5 % of verses)**.

So it needs **no new segmenter** — only the shape-A generalisation (`segment_bsb.py` with the
Mula/Sarvamula content types parameterised). It does *not* wait on the missing B-prose
segmenter.

## The mūla is free — verified, not assumed

The Bhāgavatam project has already rendered all 16,017 verses, one `.m4a` per verse, **with
karaoke timings**. Checked exhaustively rather than sampled:

| check | result |
|---|---|
| chapters in both corpora | 345 / 345 |
| chapters with identical verse counts | 345 / 345 (100 %) |
| verses matching **exactly** by chapter rank | **16,017 / 16,017 (100.00 %)** |
| chapters with any mismatch | 0 |

The URL is a pure function of position, so nothing needs storing or re-hosting:

```
https://pub-303f7559721c4b40bf6712eb557e350c.r2.dev/Bhagavata_Audio
    /skandha_NN/adhyaya_NNN/BhP_NN.NNN.RRR.m4a
RRR = the verse's 1-based rank among its chapter's Bhagavatam entries
```

Their `timings` table (16,017 rows, `segs` per verse) transfers with it, so mūla karaoke needs
no work either. **714 K akṣaras ≈ 47.5 h of audio, at zero GPU cost.**

## What actually needs rendering

| content type | entries | akṣaras | padas | GPU-h | audio | verdict |
|---|---:|---:|---:|---:|---:|---|
| `Tatparya` | 1,366 | 150,185 | 7,702 | **19.6** | 10.0 h | **render** |
| `Colophon_Bhagavatam` | 344 | 12,484 | 640 | 1.6 | 0.8 h | render — see below |
| `Subject` | 380 | 29,870 | 1,532 | 3.9 | 2.0 h | **decide** — editorial |
| `Adhyaya_Heading` | 343 | 3,309 | 170 | 0.4 | 0.2 h | skip (structure) |
| `Mangala` | 14 | 329 | 17 | 0.04 | 0.02 h | render (invocation) |
| `Colophon_Skandha` | 6 | 110 | 6 | 0.01 | 0.01 h | render |
| **committed** | **1,730** | **163,108** | **8,365** | **21.3** | **10.8 h** | |

**Colophons are a two-way win.** All 344 of our `Colophon_Bhagavatam` texts match the
Bhāgavatam project's exactly, and it has *not* rendered them (they carry an `audio_id` but no
timings). Rendering them here for 1.6 GPU-h completes both projects at once.

**`Subject` needs your call.** 380 editorial subject lines, 29,870 akṣaras, with a verse-number
density of 33 per 1,000 akṣaras — they are reference apparatus ("verses 5–9 describe…"), not
Madhva's words. The Bhāgavatam project did not render them. Rendering costs 3.9 GPU-h; my
inclination is to skip them, as with the Adhyāya headings.

## Delivery — two buckets, one reader

Per-entry files, matching both projects' 1 entry = 1 file arrangement:

* mūla verse → the **Bhāgavatam** bucket (existing, public)
* Tātparya / colophon → **`sarvamoola`** (ours)

This means the `audio` table must carry a **per-row base** (or an absolute URL in `path`)
rather than assuming a single `AUDIO_BASE`. That is a small schema change and the only new
reader work this grantha requires.

Consequence worth stating: mūla playback then depends on the Bhāgavatam bucket staying live at
that URL. Both are yours, so the risk is coupling, not availability — but if the two apps ever
diverge, this is the seam.

## Risks

1. **Quoted verses inside the Tātparya — 1,669 of them, 1.2 per entry.** This is BSB's known
   weak spot at larger scale: a quotation that is not a complete verse fails chandas detection
   and falls back to the default metre, and ASR-QC is blind to a wrong metre (it grades the
   words, not the tune). BSB has 855 such fallbacks, still unsampled by ear.
2. **Long entries.** The longest Tātparya is 1,805 akṣaras ≈ 7 minutes — it must split into
   parts, as BSB 1.1.1 does.
3. **Prose voice at volume.** 150 K akṣaras of prose in the anuṣṭubh voice, where the evidence
   for that choice is still short-fragment only.

## Order

1. Generalise `segment_bsb.py` for the `Bhagavatam`/`Tatparya` type names → `blocks_bt.json`
2. Build the mūla URL map (345 × rank → path) and verify it against the DB a second time
3. Render 8,365 padas (21.3 GPU-h) — one grantha-sized job
4. QC (CER-only), assemble per entry, bake `audio` + `audio_timings` with per-row base
5. Smoke test a chapter with both sources interleaved before committing the rest
