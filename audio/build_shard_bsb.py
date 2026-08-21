#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build render_batch shards for the whole BSB from blocks_bsb.json.

Clip ids and meters come from segment_bsb.py, so the renderer and assemble_bsb.py
agree on names by construction — there is no second place to keep in sync.

NO ॐ primer: the "model eats the first syllable" behaviour was gate() in
render_batch.py mis-trimming sonorant onsets, fixed 2026-08-02 via soft_onset().

Sharding: the box has two A6000s, and render_batch loads the model per process
(~15s), so shard by GPU and run one process each. Whole corpus ≈ 5595 padas
≈ 12.7 GPU-h on one card, ≈ 6.3 h across two.

Usage:
  build_shard_bsb.py --shards 2                      # shard_bsb_all.0.json, .1.json
  build_shard_bsb.py --only bsb_1_1_2 --out s.json   # one block
  build_shard_bsb.py --resume-from outdir            # skip clips already rendered
"""
import argparse, json, os, re

ECE_DIR = "/home/ece/Prathosh/sarvamula_try"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", default="blocks_bsb.json")
    ap.add_argument("--out", default="shard_bsb_all.json")
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--only", default="")
    ap.add_argument("--seed", type=int, default=60)
    ap.add_argument("--resume-from", default="",
                    help="local dir of already-rendered <clip>.wav to skip")
    a = ap.parse_args()

    blocks = json.load(open(a.blocks, encoding="utf-8"))
    if a.only:
        want = {x.strip() for x in a.only.split(",")}
        blocks = [b for b in blocks if b["id"] in want]

    have = set()
    if a.resume_from and os.path.isdir(a.resume_from):
        have = {f[:-4] for f in os.listdir(a.resume_from) if f.endswith(".wav")}

    # ONE CLIP PER PADA — Bhāgavatam's arrangement (its shards were one hemistich per
    # clip, single-element `padas`, gating ON, and it came out clean). One segment per
    # clip means gate()'s per-segment flags apply to the only segment, so the onset bug
    # cannot arise, and no gaps come from the renderer — assembly owns all of them.
    clips, skipped = [], 0
    for b in blocks:
        for u in b["units"]:
            for cid, pada in zip(u["clips"], u["padas"]):
                if cid in have:
                    skipped += 1
                    continue
                clips.append({
                    "id": cid,
                    "meter": u["meter"],
                    # The RECITED form only. Yamaka Bhārata prints a hyphen where the pun
                    # divides a word differently the second time (व्या-सोऽभवत् = व्यासः), and
                    # Pariśiṣṭa does the same; the mark is for the eye. The display keeps it —
                    # the pun is the poem — but the model must say the word, not the seam.
                    "padas": [re.sub(r"\s*-\s*", "", pada) if "-" in pada else pada],
                    "seed": a.seed,
                    "no_sandhi": True,
                    "out": f"{ECE_DIR}/clips/{cid}.wav",
                })

    # Balance shards by PADA COUNT, not clip count — cost tracks padas, and a single
    # unit can be 24 padas (bsb_1_1_1 u03). Longest-processing-time-first: place the
    # heaviest clip on the least-loaded shard. Interleaving evens out over 3248 clips
    # but is badly lumpy on a small selection.
    outs = []
    if a.shards <= 1:
        outs = [(a.out, clips)]
    else:
        stem, ext = os.path.splitext(a.out)
        bins = [[] for _ in range(a.shards)]
        load = [0]*a.shards
        for c in sorted(clips, key=lambda x: -len(x["padas"])):
            k = load.index(min(load))
            bins[k].append(c); load[k] += len(c["padas"])
        for k in range(a.shards):
            outs.append((f"{stem}.{k}{ext}", bins[k]))

    # ALWAYS write the combined list and the manifest alongside the shards. QC reads
    # <stem>.json and <stem>_man.json, and with --shards>1 neither used to be written: the
    # works rendered twice still had theirs from the first pass, so the omission stayed
    # invisible until rg_bhashya — a work rendered for the first time — reached QC, which
    # died on FileNotFoundError while the supervisor went on to assemble unverified audio.
    stem0 = os.path.splitext(a.out)[0]
    if a.shards > 1:
        json.dump(clips, open(a.out, "w"), ensure_ascii=False, indent=1)
    json.dump({c["id"]: " । ".join(c["padas"]) for c in clips},
              open(f"{stem0}_man.json", "w"), ensure_ascii=False, indent=1)

    padas = sum(len(c["padas"]) for c in clips)
    for path, cs in outs:
        json.dump(cs, open(path, "w"), ensure_ascii=False, indent=1)
        p = sum(len(c["padas"]) for c in cs)
        print(f"{len(cs):5d} clips / {p:5d} padas -> {path}   (~{p*8.2/3600:.2f} GPU-h)")
    print(f"\ntotal {len(clips)} clips / {padas} padas"
          + (f"; skipped {skipped} already rendered" if skipped else ""))


if __name__ == "__main__":
    main()
