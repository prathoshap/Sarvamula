#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
One recording file for every accented passage still unvoiced across the corpus.

These are the passages the renderers deliberately refused: Vedic svara is the one thing no
TTS here is trusted with, so `skip_svara` (shape A) and the `_SVARA` guard (shape B) held
them back as they were met — the Taittirīya Upaniṣad, the śānti mantras that open the other
Upaniṣad bhāṣyas, and the mantras inside Karma Nirṇaya. They are gathered here so they can
be recited in one sitting instead of hunted work by work.

EXCLUDES Ṛg Bhāṣya's 455 ṛks: those are RV 1.1–1.40 and are already being recorded from
rgveda_1_1-40_by_shloka.json, which carries the deergha-svarita text from the Ṛgveda itself.

Disambiguation, since one file now holds several granthas:
  * a LABEL BLOCK precedes each grantha's passages, so the reciter can see where they are;
  * the sidecar index carries work slug + entry seq + akṣara count for every block, which is
    what actually maps a take back — the label is for the eye, the index for the pipeline.
"""
import argparse, json, re, sqlite3, sys, uuid

sys.path.insert(0, "/Users/prathosh/Sarvamula/audio")
DB = "/Users/prathosh/Sarvamula/web/sarvamula.db"
SVARA = re.compile(r"[॒॑॓॔᳐-᳿꣠-ꣿ]")
AK = re.compile(r"[अ-हऽ]")
EXCLUDE = {"rg_bhashya"}          # recorded separately, from the Ṛgveda's own text

NAMES = {
    "taittiriya_bhashya": "तैत्तिरीयोपनिषत्",
    "kathaka_bhashya": "काठकोपनिषत्",
    "ishavasya_bhashya": "ईशावास्योपनिषत्",
    "karma_nirnaya": "कर्मनिर्णयः",
    "atharvana_bhashya": "आथर्वणोपनिषत् (मुण्डक)",
    "manduka_bhashya": "माण्डूक्योपनिषत्",
    "shatprashna_bhashya": "षट्प्रश्नोपनिषत्",
    "chandogya_bhashya": "छान्दोग्योपनिषत्",
    "kanva_bhashya": "बृहदारण्यकोपनिषत् (काण्व)",
    "aitareya_bhashya": "ऐतरेयोपनिषत्",
    "talavakara_bhashya": "तलवकारोपनिषत्",
}
ORDER = ["taittiriya_bhashya", "ishavasya_bhashya", "kathaka_bhashya", "shatprashna_bhashya",
         "manduka_bhashya", "atharvana_bhashya", "aitareya_bhashya", "talavakara_bhashya",
         "chandogya_bhashya", "kanva_bhashya", "karma_nirnaya"]


def held(db):
    """Accented entries with no audio against them — exactly what the renderers held back."""
    con = sqlite3.connect(db); con.row_factory = sqlite3.Row
    covered = {}
    for w, v in con.execute("select work, covers from audio"):
        covered.setdefault(w, set()).update(json.loads(v or "[]"))
    out = {}
    for r in con.execute("select work, seq, content_type, text_dev from entries order by work, seq"):
        t = r["text_dev"] or ""
        if r["work"] in EXCLUDE or not SVARA.search(t):
            continue
        if r["seq"] in covered.get(r["work"], set()):
            continue                       # already voiced: a stray mark in rendered prose
        out.setdefault(r["work"], []).append((r["seq"], r["content_type"], t))
    con.close()
    return out


def split_lines(t):
    """Break a passage at daṇḍas so a re-take costs a line, not the whole passage."""
    t = re.sub(r"^\s*[।॥]+\s*", "", t)
    parts = [x.strip() for x in re.split(r"(?<=।)\s+|(?<=॥)\s+(?![०-९\d])", t) if x.strip()]
    # A citation can run on with no daṇḍa at all — Karma Nirṇaya quotes one Brāhmaṇa passage
    # of 392 akṣaras in a single line, over two minutes in one breath. Cut those on word
    # boundaries into 8-word phrases, the same 5-10 word rule used for oversized units.
    cut = []
    for x in parts:
        if len(AK.findall(x)) <= 70:
            cut.append(x); continue
        w = x.split()
        cut += [" ".join(w[i:i+8]) for i in range(0, len(w), 8)]
    parts = cut
    out, cur = [], []
    for p in parts:                        # keep blocks recitable in one breath-group
        cur.append(p)
        if len(AK.findall(" ".join(cur))) >= 40 or p.rstrip().endswith("॥"):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return [g for g in out if len(AK.findall(" ".join(g))) >= 2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--out", required=True)
    ap.add_argument("--index", required=True)
    a = ap.parse_args()

    src = held(a.db)
    content, sidecar = {}, []
    for w in ORDER + sorted(set(src) - set(ORDER)):
        if w not in src:
            continue
        name = NAMES.get(w, w)
        uid = str(uuid.uuid4())
        content[uid] = [{"content_type": "Colophon_Sarvamula", "text": [f"॥ {name} ॥"]}]
        sidecar.append({"id": uid, "work": w, "seq": None, "kind": "label",
                        "grantha": name, "aksharas": 0})
        for seq, ct, t in src[w]:
            for g in split_lines(t):
                uid = str(uuid.uuid4())
                content[uid] = [{"content_type": "Sarvamula", "is_padya": True, "text": g}]
                sidecar.append({"id": uid, "work": w, "seq": seq, "kind": "shruti",
                                "grantha": name,
                                "aksharas": sum(len(AK.findall(x)) for x in g)})

    doc = {"title": "॥ सर्वमूलान्तर्गताः सस्वराः श्रुतिभागाः ॥", "content": content}
    json.dump(doc, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(sidecar, open(a.index, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    aks = sum(x["aksharas"] for x in sidecar)
    print(f"{len(content)} blocks over {len(src)} granthas, {aks:,} akṣaras")
    for w in ORDER:
        if w in src:
            n = sum(1 for x in sidecar if x["work"] == w and x["kind"] == "shruti")
            k = sum(x["aksharas"] for x in sidecar if x["work"] == w)
            print(f"   {NAMES.get(w,w):28s} {len(src[w]):3d} passages -> {n:4d} blocks, {k:6,d} akṣ")
    print(f"-> {a.out}\n-> {a.index}")
    print(f"recitation ≈ {aks*0.38/3600:.1f}–{aks*0.50/3600:.1f} h")


if __name__ == "__main__":
    main()
