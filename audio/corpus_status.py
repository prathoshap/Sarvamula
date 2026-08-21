#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Status of all 38 granthas, generated — never hand-maintained.

We do one grantha at a time, so a hand-written table goes stale the moment a work is
segmented or assembled. Everything measurable is therefore DERIVED at run time:

    aksharas, shape, padas, GPU-h, audio h   <- sarvamula.db
    segmented?                               <- blocks_<key>.json in this directory
    assembled / in the reader?               <- the `audio` table
    where the audio came from, R2 state      <- corpus_state.json (the only hand file)

Rates are measured on the two finished works (BSB, Anuvyakhyana), not assumed:
    0.2395 s audio per akshara, 0.47 GPU-s per akshara, 19.5 aksharas per pada.

    corpus_status.py --md ../Sarvamula_grantha_status.md
"""
import argparse, json, os, re, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DB = "/Users/prathosh/Sarvamula/web/sarvamula.db"
STATE = os.path.join(HERE, "corpus_state.json")

S_AUD, S_GPU, AK_PADA = 0.2395, 0.47, 19.5
AK = re.compile("[अ-हऽ]")
# Headings, titles and running subject lines are structure, not recitation.
SKIP = re.compile(r"^(Heading|Subheading|Title|Subject|Adhyaya_Heading|Skandha_Heading|Mangala)")
# A verse number, in either printed form: '॥ १५६ ॥' and mbtn's '॥ १९/९६॥'.
VNUM = re.compile(r"॥\s*[०-९\d]+(?:[/।\-][०-९\d]+)*\s*॥")

# blocks_<file>.json is named per segmenter, not per work slug
BLOCKS = {"sutra_bhashya": "blocks_bsb.json", "anu_vyakhyana": "blocks_anu.json",
          "bhagavata_tatparya": "blocks_bt.json", "gita_bhashya": "blocks_gb.json",
          "gita_tatparya": "blocks_gt.json", "mbtn": "blocks_mbtn.json",
          "tantrasara_sangraha": "blocks_tss.json", "sadachara_smriti": "blocks_sas.json",
          "krshna_amrta_maharnava": "blocks_kam.json", "vishnu_tatva_nirnaya": "blocks_vtn.json",
          "tatvodyota": "blocks_tdy.json"}

STAGES = ["scoped", "segmented", "rendered", "qc", "assembled", "in_db", "uploaded"]

# A work registered in segment_bsb.WORKS is shape A by construction — the density heuristic
# below is only for works nobody has looked at yet. bhagavata_tatparya is the case in point:
# it pairs `Bhagavatam` with `Tatparya` rather than Mula/Sarvamula, so it reads as prose to
# the heuristic while being structurally identical to BSB.
sys.path.insert(0, HERE)
try:
    from segment_bsb import WORKS as SHAPE_A
except Exception:
    SHAPE_A = {}


def measure(db):
    """Per work: recitable aksharas, shape, and the largest single entry."""
    con = sqlite3.connect(db)
    out = {}
    for (w,) in con.execute("select distinct work from entries"):
        ak = marks = biggest = 0
        mula = False
        reuse = 0
        for ct, t in con.execute("select content_type, text_dev from entries where work=?", (w,)):
            ct = ct or ""
            if SKIP.match(ct):
                continue
            n = len(AK.findall(t or ""))
            if ct == "Bhagavatam":          # already rendered by the Bhagavatam project
                reuse += n
                continue
            ak += n
            marks += len(VNUM.findall(t or ""))
            if ct == "Mula":
                mula = True
            biggest = max(biggest, n)
        if not ak:
            continue
        dens = 1000 * marks / ak
        shape = ("A" if (mula or w in SHAPE_A)
                 else ("B-verse" if dens >= 1.5 else "B-prose"))
        out[w] = {"ak": ak, "shape": shape, "dens": round(dens, 2), "big": biggest,
                  "reuse": reuse, "padas": round(ak / AK_PADA),
                  "gpu": ak * S_GPU / 3600, "aud": ak * S_AUD / 3600}
    con.close()
    return out


def observed(db):
    """What the reader can actually play right now."""
    con = sqlite3.connect(db)
    try:
        rows = list(con.execute("select work, count(*), sum(dur) from audio group by work"))
    except sqlite3.OperationalError:
        rows = []
    con.close()
    return {r[0]: {"files": r[1], "dur": (r[2] or 0) / 3600} for r in rows}


def stage_of(w, st, seg, obs):
    """Recorded stage, but never ahead of what is observable."""
    rec = (st.get(w) or {}).get("stage", "scoped")
    if w in obs:
        return "uploaded" if rec == "uploaded" else "in_db"
    if rec in ("rendered", "qc", "assembled"):
        return rec
    return "segmented" if seg.get(w) else "scoped"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--md", default=os.path.join(HERE, "..", "Sarvamula_grantha_status.md"))
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    m = measure(a.db)
    obs = observed(a.db)
    st = json.load(open(STATE, encoding="utf-8"))
    seg = {}
    for w in m:
        f = os.path.join(HERE, BLOCKS.get(w, f"blocks_{w}.json"))
        if os.path.exists(f):
            b = json.load(open(f, encoding="utf-8"))
            seg[w] = {"blocks": len(b), "files": sum(len(x["parts"]) for x in b),
                      "padas": sum(len(u["padas"]) for x in b for u in x["units"])}

    rows = []
    for w, d in m.items():
        s = st.get(w, {})
        rows.append({**d, "work": w, "stage": stage_of(w, st, seg, obs),
                     "seg": seg.get(w), "obs": obs.get(w),
                     "note": s.get("note", ""), "clips": s.get("clips", ""),
                     "granularity": s.get("granularity", "pada"), "qcnote": s.get("qc", "")})
    order = {s: i for i, s in enumerate(STAGES)}
    rows.sort(key=lambda r: (-order[r["stage"]], -r["ak"]))

    done = [r for r in rows if r["stage"] in ("in_db", "uploaded")]
    todo = [r for r in rows if r["stage"] not in ("in_db", "uploaded")]
    gpu_left = sum(r["gpu"] for r in todo if r["stage"] == "scoped" or r["stage"] == "segmented")

    L = []
    w_ = L.append
    w_("# Sarvamūla audio — status by grantha\n")
    w_("*Generated by `audio/corpus_status.py` — do not edit by hand. "
       "Hand-kept facts live in `audio/corpus_state.json`.*\n")
    w_(f"Rates measured on BSB + Anuvyākhyāna: **{S_AUD} s audio/akṣara**, "
       f"**{S_GPU} GPU-s/akṣara**, **{AK_PADA} akṣaras/pada**.\n")
    w_(f"**{len(done)} of {len(rows)} granthas playable** "
       f"({sum(r['obs']['files'] for r in done)} files, "
       f"{sum(r['obs']['dur'] for r in done):.1f} h). "
       f"Remaining GPU budget **{gpu_left:.0f} GPU-h** "
       f"for {sum(r['ak'] for r in todo):,} akṣaras.\n")
    w_(f"Staging root (upload to R2 `{st['_r2_bucket']}` from here): `{st['_stage_root']}`\n")
    w_("| grantha | shape | akṣaras | padas | audio | GPU-h | stage | files |")
    w_("|---|---|---:|---:|---:|---:|---|---:|")
    for r in rows:
        aud = f"{r['obs']['dur']:.2f} h" if r["obs"] else f"~{r['aud']:.2f} h"
        gpu = "—" if r["stage"] in ("in_db", "uploaded", "rendered") else f"{r['gpu']:.1f}"
        files = str(r["obs"]["files"]) if r["obs"] else (str(r["seg"]["files"]) if r["seg"] else "—")
        padas = r["seg"]["padas"] if r["seg"] else r["padas"]
        w_(f"| {r['work']} | {r['shape']} | {r['ak']:,} | {padas:,} | {aud} | {gpu} "
           f"| **{r['stage']}** | {files} |")
    w_("")
    w_("## Notes\n")
    for r in rows:
        if r["note"] or r["qcnote"]:
            w_(f"**{r['work']}** — {r['note']}" + (f"  \nQC: {r['qcnote']}" if r["qcnote"] else ""))
            w_("")
    w_("## Shapes\n")
    w_("* **A** — `Mula` + `Sarvamula` pairs (`segment_bsb.py`). The `Mula` is a sūtra in BSB, "
       "but **śruti** in the Upaniṣad bhāṣyas and a Gītā verse in `gita_*`.")
    w_("* **B-verse** — numbered ślokas, no `Mula` (`segment_anu.py`).")
    w_("* **B-prose** — prose commentary, no `Mula`, no numbering. **No segmenter yet**; "
       "entries run to 23,836 akṣaras and must be cut on headings and size.")
    w_("")
    w_("Shape is assigned by verse-number density, because `entries.is_padya` is unreliable "
       "(it flags kanva_bhashya's 47 K-character prose entry as verse). Confirm each work "
       "before queueing it: two unnumbered stotras (`krshna_amrta_maharnava`, "
       "`dvadasha_stotra`) are genuinely verse and are binned here as prose.\n")

    open(os.path.abspath(a.md), "w").write("\n".join(L))
    print(f"-> {os.path.abspath(a.md)}")
    print(f"   {len(done)} playable, {len(todo)} to go, {gpu_left:.0f} GPU-h remaining")
    if a.json:
        json.dump(rows, open(a.json, "w"), ensure_ascii=False, indent=1)
        print(f"-> {a.json}")


if __name__ == "__main__":
    main()
