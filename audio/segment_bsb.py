#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Whole-BSB segmentation: apply the BSB 1.1.2 rules to every sutra in the
Brahmasūtra Bhāṣya, straight from the reader DB.

The DB already has exactly the shape the pipeline needs (work='sutra_bhashya'):
    Mula                the sutra          '॥ [ॐ] जन्माद्यस्य यतः [ॐ]॥ १/१/२॥'
    Sarvamula           its bhāṣya         prose + embedded “…” quotations
    Heading1/2/3        adhyāya / pāda / adhikaraṇa context
    Colophon_Sarvamula  end-of-section colophons (rendered as their own blocks)

A BLOCK is one (Mula, Sarvamula) pair -> the unit list that segment.py produces.
Every UNIT becomes one clip; every PADA inside a unit is one TTS call.

Meter assignment (baked from the 1.1.2 findings):
    sutra          -> SUTRA_METER
    gadya (prose)  -> PROSE_METER
    padya (quote)  -> auto chandas detection; falls back to FALLBACK_METER when the
                      quotation is a fragment (the detector needs a COMPLETE verse,
                      so partial Ṛgveda citations legitimately return nothing)

Usage:
    segment_bsb.py --stats                  # counts only, no files written
    segment_bsb.py --out blocks_bsb.json    # full segmentation
    segment_bsb.py --sutra 1/1/2            # one block, printed (sanity check)
"""
import argparse, hashlib, json, os, re, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from segment import build_units, clean as seg_clean, gadya_segments  # R1-R4 live there; single source of truth

DB = "/Users/prathosh/Sarvamula/web/sarvamula.db"
WORK = "sutra_bhashya"
VAGDHENU_SRC = "/Users/prathosh/sarvamoola/vagdhenu/src"

# ── meter policy ──────────────────────────────────────────────────────────────
# 2026-08-02: gadya_mbtn everywhere prose is spoken, judged on u02 (real bhāṣya prose,
# the case that generalizes — prose is 1521 of 3248 units) after it had already won on
# u04 and u05. Plain `gadya` is now unused; keep the constants separate so the sutra can
# be reverted on its own if the aphorism wants a different voice from the commentary.
# 2026-08-07: prose (and the sutra, which is also prose) render with the **anuṣṭubh**
# reference. Vāgbodhinī reached the same setting in production (`PROSE_VOICE` env,
# "gadya drops onsets -> use anuṣṭubh for prose"), and our ASR QC agreed on every short
# prose clip it had to rescue (anuṣṭubh won 8 of 12).
# CAVEAT worth re-testing by ear: that evidence is all from SHORT prose. On the one LONG
# prose case judged by ear (u02 of 1.1.2) gadya_mbtn was preferred, and measured globally
# anuṣṭubh was not better. Flip these two constants back to "gadya_mbtn" to revert.
SUTRA_METER   = "anuṣṭubh"
PROSE_METER   = "anuṣṭubh"
# Fallback for a quotation whose metre chandas detection cannot identify (855 units, 18%
# — mostly single-pada fragments, where the detector needs a complete verse). 2026-08-07:
# vasantatilakā rather than upajāti, per user. NOTE this class is still unsampled, and the
# ASR loop cannot catch a wrong choice here — a verse chanted in the wrong metre still
# transcribes perfectly, so only the ear can judge it.
FALLBACK_METER = "vasantatilakā"
# Units whose prose reads better on the mbtn reference. 1.1.2 established this for the
# short connectives and the Taittirīya prose mantra; the u02-length prose case is still
# undecided, so the switch is explicit rather than global.
PROSE_MBTN_MAX_AKSHARA = 0     # 0 = off; set >0 to route SHORT prose to gadya_mbtn
PROSE_MBTN = "gadya_mbtn"

# ── per-block exceptions (block id -> unit number -> override) ────────────────
# The rules above are right for the common case; these are the judged exceptions.
#   meter   force a reference the rules would not pick
#   groups  regroup padas: list of groups of source-pada indices (0-based).
#           segment.py splits at every visarga/comma/daṇḍa, which is sometimes finer
#           than the reading wants — each pada is a separate TTS call with a gap.
# Everything here was approved by ear; keep the reason with the entry.
OVERRIDES = {
    "bsb_1_1_2": {
        # Taittirīya "यतो वा इमानि…" is a PROSE mantra that happens to sit inside “…”,
        # so R3 types it padya and chandas detection correctly finds no metre. It wants
        # the prose reference, and reads better with the last three clauses run together.
        5: {"meter": PROSE_METER, "groups": [[0], [1], [2, 3, 4]]},
    },
    # (u04 "इति स्कान्दे" no longer needs an override — PROSE_METER is gadya_mbtn now,
    #  which is exactly what fixed it.)
    "tsk_seq16": {
        # Tatva Saṅkhyāna's closing verse 10 is a single anuṣṭubh half-line,
        # "सृष्टिः स्थितिः संहृतिश्च नियमोऽज्ञानबोधने॥ १०॥". With no internal daṇḍa it types
        # as prose, and the prose splitter cuts at every visarga — giving "सृष्टिः ।",
        # "स्थितिः ।" as separate clips, each with its own pause. (Before the source text was
        # corrected it was worse still: a stray ॥ mid-verse split दुःखम् into "दुः" and "खम्".)
        # One group = one pāda = one clip, recited straight through, as the edition prints it.
        1: {"groups": [[0, 1, 2]]},
    },
}

# Entries the SOURCE prints as verse but whose text carries only single daṇḍas, so the
# ॥-span test in split_unquoted_verses never fires and the PROSE splitter cuts them at
# visargas — '…पृथिवीस्थितः । प्रथितः ।' out of a line the edition prints whole, and in 25
# cases straight through a word (दुःखम् -> 'दुः' + 'खम्').
#
# Scoped to the 105 entries an audit actually found (audio/verse_split_defects.json)
# rather than driven off entries.is_padya: that flag is set on 20,389 of 29,328 entries and
# marks an entry that CONTAINS verse, not one that is wholly verse. Trusting it re-typed
# 11,777 clips across 21 works — 46 GPU-hours, and prose split at daṇḍas as if metrical.
VERSE_ENTRIES = {
    "shatprashna_bhashya": [9],
    "aitareya_bhashya": [12, 16, 18, 20, 24, 71, 73, 75, 187],
    "bhagavata_tatparya": [4638, 18151],
    "gita_bhashya": [33, 41, 73, 147, 278, 284, 355, 359, 418, 420],
    "gita_tatparya": [124, 220, 361, 734, 794, 836, 844, 871],
    "kanva_bhashya": [289],
    "karma_nirnaya": [36],
    "kathaka_bhashya": [12],
    "manduka_bhashya": [2],
    "nyaya_vivarana": [138, 144, 158, 194, 196, 204, 249, 263, 283, 289, 291, 299, 305, 317, 321, 331, 337, 343, 359, 383, 389, 412, 418, 428, 432, 440, 450, 458, 460],
    "sutra_bhashya": [10, 18, 64, 75, 127, 165, 353, 375, 379, 381, 386, 392, 421, 573, 643, 650, 713, 773, 815, 838, 896, 991, 1034, 1039, 1042, 1070, 1127, 1157, 1182, 1190, 1197, 1203, 1228, 1371],
    "tatva_sankhyana": [12],
    "tatva_viveka": [10, 14, 18],
    "tatvodyota": [72],
    "upadhi_khandana": [5, 11],
    "vishnu_tatva_nirnaya": [40, 73, 76, 78, 80, 127, 174, 186, 222, 250],
}


# ── detector-name -> bank-key aliasing ────────────────────────────────────────
# tts_meter emits ASCII names; the bank is keyed in IAST. render_core's LUT also
# registers each entry's wav STEM, which happens to cover most ASCII names
# (upajati, vasantatilaka, indravajra…) — but NOT anuṣṭubh, whose wav is
# anu_v094.wav. Unaliased, the commonest metre in the corpus resolves to nothing
# and is silently swapped for FALLBACK_METER by the renderer.
METER_ALIAS = {"anushtubh": "anuṣṭubh", "anushtubh_half": "anuṣṭubh"}

# Metres tts_meter can identify that the reference bank has no recording for.
# These must fall back — but visibly, so the count is known rather than assumed.
NO_REFERENCE = {"shikharini", "mandakranta", "harini", "prithvi"}

# Bank keys as of 2026-08-02 (reference_bank/bank.json on ece-box). Used only to
# assert that every meter we emit can actually be resolved; refresh if the bank grows.
BANK_KEYS = {
    "anuṣṭubh", "pramāṇikā", "indravajrā", "upendravajrā", "upajāti", "vaṃśastha",
    "indravaṃśā", "śālinī", "vasantatilakā", "bhujaṅgaprayāta", "vrutta-1", "mālinī",
    "gadya", "drutavilambita", "gadya_mbtn", "śārdūlavikrīḍita", "sragdharā", "rathoddhatā",
    # wav-stem aliases the LUT also accepts
    "anu_v094", "pramanika", "indravajra", "upendravajra", "upajati", "vamshastha",
    "indravamsha", "shalini", "vasantatilaka", "bhujangaprayata", "vrutta1", "malini",
    "drutavilambita", "shardulavikridita", "sragdhara", "rathoddhata",
}

# ── part splitting ────────────────────────────────────────────────────────────
# One file per sutra is right for almost the whole corpus (median ~38s, 83% under a
# minute). A few blocks are long-form though — bsb_1_1_1 is the maṅgala plus the
# introduction to the entire work, 57 units / ~12 min — and nobody wants to seek
# inside a 12-minute file to reach one clause.
#
# Duration model, least-squares fit on 67 REAL rendered clips (bsb_1_1_1 + 1_1_2,
# akṣara range 2-512):  speech = 0.2166*aksharas - 0.358*padas   R2 0.9969,
# mean |err| 0.59s. Duration tracks AKṢARAS, not pada count: an earlier per-pada-only
# model (3.838 s/pada, fitted on 1.1.2 alone) was off by a mean 3.21s and up to -42% on
# blocks full of short units ("इति", "नाविशेषात्"), which is most of bsb_1_1_1's tail.
SEC_PER_AKSHARA = 0.2166
SEC_PER_PADA    = -0.358  # negative: fit artifact absorbing sub-linearity; see MIN_UNIT_SEC
MIN_UNIT_SEC    = 0.30    # floor, so a many-pada/few-akṣara unit cannot go negative
PADA_GAP        = 0.55    # render_batch --gap, between padas INSIDE a unit
UNIT_GAP_AVG    = 0.817   # assemble_block unit gap, averaged over the quote-lead cases
SUTRA_FRAME     = 1.613   # exemplar ॐ framing: 2 x 0.557s + 2 x 0.25s gap
CALIB           = 1.0     # kept as a hook; recalibrate from real durations, do not fudge

# Must match the regex the model was fitted with: consonants + independent vowels,
# NOT matras (counting matras double-counts a syllable).
_AK = re.compile(r"[अ-हऽ]")

PART_TARGET_SEC = 90.0   # close a part once past this, at a natural boundary
PART_HARD_SEC   = 150.0  # push past a natural boundary only until here
PART_MIN_SEC    = 20.0
# A citation typed padya with no identified metre is prose; cap it at this many words per
# breath (user call 2026-08-10: "take 5-10 words and then put a pause").
LONG_PADYA_WORDS = 8
# Cap a fallback-metre pāda by SYLLABLES as well as words, for works whose config asks for
# it. Sanskrit compounding defeats a word count on its own — Karma Nirṇaya has a 112-akṣara
# "pāda" of only eight words, some 27 seconds in one breath. Off by default: switching it on
# shifts pāda indices and therefore clip ids, which would invalidate every rendered clip of
# an already-shipped work (it changed 4,807 of Chāndogya's when applied globally).
_OM = "ॐ"
# A bracketed group is a DELIMITER, never sound, and three kinds are printed:
#   [अर्जुन उवाच / [खण्डार्थनिर्णयापरनामा] / ते[ऽ]निन्दया   text in an editorial wrapper -> unwrap
#   [-] / [---]                                          a lacuna, nothing to say -> delete whole
#   [ॐ]                                                  LEAVE ALONE. This one is already handled:
#     depranava() lifts a lone ॐ pada out of the render and assembly splices the recorded
#     exemplar in its place. Touching it re-texts the opening pada of every sutra — 544 of
#     sutra_bhashya's 5,405 clips changed id when this rule first ran over it — and would put
#     the pranava framing at risk for no gain.
# Left unhandled, the model reads a bare bracket aloud as "a", which is what was heard at the
# head of Saṅgraha Bhāṣya's maṅgala.
def _debracket(t):
    if not t or ("[" not in t and "]" not in t):
        return t
    PH = ""                                  # private-use stand-in, put back at the end
    t = re.sub(r"\[\s*ॐ\s*\]", PH, t)              # protect the pranava form FIRST
    t = re.sub(r"\[[^\[\]]{0,60}\]",
               lambda m: m.group(0)[1:-1] if _AK.search(m.group(0)) else " ", t)
    t = re.sub(r"[\[\]]", "", t)                   # unpaired leftovers: ']] [त्वयोपभुक्त…'
    return t.replace(PH, "[" + _OM + "]")


LONG_PADYA_AKSHARA = 40

# Vedic accent marks: udātta, anudātta, the Vedic Extensions block, Devanagari Extended.
# A mūla passage carrying these is svara-marked śruti — the chant model cannot reproduce
# svara, so it is held back for hand recitation (Sarvamula_shruti_to_record.md). Mūla
# WITHOUT accents is recited normally: this edition prints most Upaniṣad text unaccented,
# and excluding all of it would have silently dropped 92 passages / 14,978 akṣaras.
SVARA = re.compile("[॒॑᳐-᳿꣠-ꣿꣀ-꣏॓॔]")   # a tail shorter than this is folded back into the previous part

# Minimum akṣaras in a rendered pada. R2 splits prose at EVERY visarga, which is right
# for the visarga echo but manufactures fragments the model cannot render: 38% of corpus
# padas are <=12 akṣaras and 46 are a single akṣara. A ~1s target against a ~7.6s
# reference is the regime that garbled "इति स्कान्दे" and swallowed "तच्चोक्तं स्कान्दे".
# Merging a runt into its neighbour costs one visarga echo and buys a stable render.
# Target the window the model was actually trained on. Bhāgavatam's synthesis input is
# `lines[]` with n_lines=2 per śloka — two hemistichs of ~16 akṣaras (~4-5s) — uniform and
# in-distribution, which is why raw TTS with no guards worked there. BSB prose split at
# every visarga is not: 35% of padas fall under 16 akṣaras and 3.2% run past 45, and every
# failure so far (इति स्कान्दे, तच्चोक्तं स्कान्दे, truncated onsets) came from those tails.
# So bound BOTH ends rather than bolting guards onto the renderer.
MIN_PADA_AKSHARA = 16    # ~= Bhāgavatam hemistich; below this the model destabilizes
MAX_PADA_AKSHARA = 45    # above this generation quality falls off


def fit_padas(padas, bounds=None, lo=MIN_PADA_AKSHARA, hi=MAX_PADA_AKSHARA):
    """Bring every pada into [lo, hi] akṣaras: merge runts, split overlong ones on word
    boundaries. Returns (padas, bounds).

    Merges ONLY across a SOFT (visarga) boundary. A HARD boundary — daṇḍa, comma, lacuna —
    is a sentence break that has to be heard as a pause, and merging across one silently
    deletes that pause (it swallowed the daṇḍa in
    'ब्रह्मसूत्राणि चकार । तच्चोक्तं स्कान्दे'). So a runt that ends on a daṇḍa stays a
    runt; render stability for those comes from the ASR-QC loop instead."""
    bounds = list(bounds or ["hard"]*len(padas))
    merged, mb, buf = [], [], ""
    for p, b in zip(padas, bounds):
        buf = (buf + " " + p).strip() if buf else p
        if len(_AK.findall(buf)) >= lo or b == "hard":
            merged.append(buf); mb.append(b); buf = ""
    if buf:
        if merged: merged[-1] = merged[-1] + " " + buf
        else: merged.append(buf); mb.append("hard")

    out, ob = [], []
    for p, b in zip(merged, mb):
        if len(_AK.findall(p)) <= hi:
            out.append(p); ob.append(b); continue
        # split on whitespace, closing a chunk once it reaches the midpoint of the window
        # so the pieces land inside it rather than alternating long/short
        target = (lo + hi) // 2
        cur = ""
        for wd in p.split():
            cand = (cur + " " + wd).strip()
            if cur and len(_AK.findall(cand)) > target:
                out.append(cur); ob.append("soft"); cur = wd   # a mid-sentence cut is SOFT
            else:
                cur = cand
        if cur:
            if out and len(_AK.findall(cur)) < lo and ob[-1] == "soft":
                out[-1] = out[-1] + " " + cur
            else:
                out.append(cur); ob.append(b)
        else:
            ob[-1] = b                                          # last piece keeps the real boundary
    return out, ob


_EDROP = set('।॥*0123456789०१२३४५६७८९')
_EBARE = lambda s: ''.join(c for c in (s or '') if 'ऀ' <= c <= 'ॿ' and c not in _EDROP)
_ELINES = None      # {"work|seq": [cut, …]} — see build_entry_lines.py


def edition_lines(path=None):
    """Lazy-load the recovered edition line structure. Absent file = feature off."""
    global _ELINES
    if _ELINES is None:
        p = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "entry_lines.json")
        try:
            _ELINES = json.load(open(p, encoding="utf-8"))
        except Exception:
            _ELINES = {}
    return _ELINES


def merge_padas_to_edition(u, work, seq, entry_text, hi=MAX_PADA_AKSHARA):
    """Join a unit's pādas back together wherever the EDITION prints one line.

    fit_padas() cuts prose at visargas, which is right for the visarga echo but wrong
    whenever the passage is actually verse — and `is_padya` cannot be trusted to tell them
    apart (it marks entries that CONTAIN verse, so Aitareya's ślokas arrive typed `gadya`).
    The edition's own line list is the authority instead: a pāda may end where the book ends
    a line and nowhere else. That is what stops 'कर्मभिः ।' from being handed to the model as
    a complete utterance, which is why it came back with a falling contour and a pause.

    A join is REFUSED past `hi` akṣaras: generation quality falls off there, and a 300-akṣara
    śruti quote printed as one line is not one breath. Those stay split — the display already
    shows the edition line, and several clips may light it.
    """
    EL = edition_lines()
    key = f"{work}|{seq}"
    if not EL or key not in EL or not u.get("padas") or len(u["padas"]) < 2:
        return False
    ent = _EBARE(entry_text)
    mine = _EBARE(" ".join(u["padas"]))
    at = ent.find(mine)
    if at < 0:
        return False                          # unit text not in this entry — leave alone
    legal = {c - at for c in EL[key]}
    legal.add(len(mine))
    # A daṇḍa the SOURCE prints is also a boundary, even mid-line. Bhāgavata Tātparya stores
    # commentary as whole paragraphs with verse quoted inside them —
    #   '…अहङ्कारस्त्रिविधोऽपि। ‘वैकारिको महांश्चैव तथाऽहङ्कार एव च। तथैव सात्विकश्चांशो…'
    # is ONE text element — so line-ends alone would fuse two hemistichs of a quoted śloka
    # into a single 32-akṣara clip. A pāda is the unit of recitation and must never be merged;
    # honouring only the line-end would have done exactly that to 567 clips.
    keep, seen = set(), 0
    for ch in entry_text:
        if 'ऀ' <= ch <= 'ॿ' and ch not in _EDROP:
            seen += 1
        elif ch in '।॥':
            keep.add(seen - at)               # letters SEEN so far = offset of this break
    legal |= {o for o in keep if 0 < o < len(mine)}
    bounds = list(u.get("bounds") or ["hard"] * len(u["padas"]))
    # Group the pādas by the edition line each falls in, then join a group ALL-OR-NOTHING.
    # Joining pairwise "while it still fits" would half-merge a long line — a 60-akṣara prose
    # sentence printed as one line would go from three clips to two, re-rendering audio and
    # moving a pause for no visible gain, since the display already shows the whole line.
    # Either the line can be one utterance or its existing clips are left exactly as they are.
    groups, cur, off = [], [], 0
    for p, b in zip(u["padas"], bounds):
        cur.append((p, b))
        off += len(_EBARE(p))
        if off in legal:
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)
    out, ob = [], []
    for g in groups:
        joined = " ".join(p for p, _ in g)
        if len(g) > 1 and len(_AK.findall(joined)) <= hi:
            out.append(joined); ob.append(g[-1][1])
        else:
            out.extend(p for p, _ in g); ob.extend(b for _, b in g)
    if len(out) == len(u["padas"]):
        return False
    u["padas"], u["bounds"] = out, ob
    u["text"] = " ".join(out)
    return True


def unit_seconds(u, is_sutra=False):
    p = len(u["padas"])
    ak = sum(len(_AK.findall(x)) for x in u["padas"])
    speech = max(MIN_UNIT_SEC, SEC_PER_AKSHARA*ak + SEC_PER_PADA*p)
    return CALIB * (speech + PADA_GAP*max(0, p-1) + (SUTRA_FRAME if is_sutra else 0.0))


def block_seconds(units):
    tot = sum(unit_seconds(u, u["type"] == "sutra") for u in units)
    return tot + CALIB * UNIT_GAP_AVG * max(0, len(units)-1)


def split_parts(units):
    """Group units into parts. Returns a list of (start, end) index pairs, end exclusive.

    Prefers to break where Madhva RESUMES HIS OWN PROSE after a citation (next unit is
    gadya, previous was padya) — the bhāṣya's natural paragraph rhythm — rather than
    cutting between a citation and the prose that introduces it."""
    if block_seconds(units) <= PART_HARD_SEC:
        return [(0, len(units))]
    parts, start, run = [], 0, 0.0
    for i, u in enumerate(units):
        run += unit_seconds(u, u["type"] == "sutra") + CALIB*UNIT_GAP_AVG
        nxt = units[i+1] if i+1 < len(units) else None
        if nxt is None:
            break
        natural = nxt["type"] == "gadya" and u["type"] == "padya"
        if (run >= PART_TARGET_SEC and natural) or run >= PART_HARD_SEC:
            parts.append((start, i+1)); start = i+1; run = 0.0
    parts.append((start, len(units)))
    # A single oversized unit (bsb_1_1_1 unit 3 is 24 padas, ~104s) cannot be divided,
    # so a part may still exceed PART_HARD_SEC; that is preferable to cutting mid-unit.
    # Fold a runt tail back rather than shipping a 4-second file.
    if len(parts) > 1 and block_seconds(units[parts[-1][0]:parts[-1][1]]) < PART_MIN_SEC:
        (s0, _), (_, e1) = parts[-2], parts[-1]
        parts[-2:] = [(s0, e1)]
    return parts


_DEVA_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_REF = re.compile(r"([०-९]+)\s*/\s*([०-९]+)\s*/\s*([०-९]+)")



# ── shape-A registry ──────────────────────────────────────────────────────────
# Shape A is "a mūla text followed by Madhva's commentary on it". BSB was the first, so
# this file grew around its vocabulary — but the shape is general and the content types
# are just names: bhagavata_tatparya pairs `Bhagavatam` with `Tatparya` and is structurally
# identical. Everything work-specific lives here; the code below reads it.
#
#   mula/comm   the paired content types
#   render_mula False when the mūla is ALREADY recited elsewhere and is reused rather than
#               rendered (bhagavata_tatparya: all 16,017 verses are verbatim in the
#               Bhāgavata-VāNi corpus, which has audio AND timings for them)
#   ref         "text"    the ref is printed inside the mūla (BSB's '॥ १/१/२॥')
#               "columns" the ref is in entries.skandha/adhyaya/verse
#   orphans     render commentary blocks that follow no mūla (colophons). Off for BSB
#               because it is finished — turning it on adds 19 blocks to a shipped work.
WORKS = {
    "sutra_bhashya": dict(
        mula="Mula", comm="Sarvamula", colophons=("Colophon_Sarvamula",),
        render_mula=True, mula_kind="sutra", ref="text",
        # orphans ON as of 2026-08-17: 4 Sarvamula entries (436 akṣ of quoted pramāṇa at
        # seq 1114/1117/1194/1289) follow no mūla and were therefore never rendered. It was
        # switched off when BSB was declared finished; the text being silent outweighs the
        # 19 blocks it adds.
        prefix="bsb", stem="BSB", orphans=True, drop_empty_padas=False,
        strip_parens=False, split_long_padya=False),
    # The two Gītā works: mūla = a Bhagavad-Gītā verse (rendered — nobody else has it),
    # commentary = Madhva's. No ref columns and no printed refs, and Madhva comments on a
    # SELECTION of verses, so positional numbering would invent wrong Gītā references —
    # blocks are keyed by source seq instead (decision 2026-08-09, see corpus_state.json).
    "gita_bhashya": dict(
        mula="Mula", comm="Sarvamula",
        colophons=("Colophon_Sarvamula", "Colophon_Mula"),
        render_mula=True, mula_kind="padya", mula_meter="detect",
        ref="mula_verse", mula_verses=True,
        # this slug holds the TĀTPARYA (see its colophons) — label the part accordingly
        prefix="gb", stem="GB", orphans=True, fallback="length", inherit_ref=True,
        part_kind="tatparya"),
    "gita_tatparya": dict(
        mula="Mula", comm="Sarvamula",
        colophons=("Colophon_Sarvamula", "Colophon_Mula"),
        render_mula=True, mula_kind="padya", mula_meter="detect",
        ref="mula_verse", mula_verses=True,
        # this slug holds the BHĀṢYA — part_kind was "tatparya", which mislabelled 419 tiles
        prefix="gt", stem="GTN", orphans=True, fallback="length", inherit_ref=True,
        part_kind="bhashya"),
    # Commentary with NO mūla to pair — Madhva writing in his own voice throughout. Declaring
    # a mūla type that never occurs makes every entry fall through as an "orphan", which
    # orphans=True then segments as prose. These two need no block-splitting: their entries
    # run to 1,187 akṣaras at most (unlike kanva_bhashya's 23,836, which still needs the
    # heading/size cutting that does not exist yet).
    # Nyāya Vivaraṇa: each section is headed by the SŪTRA itself (typed Title, framed ॐ…ॐ and
    # followed by the pūrvapakṣa/siddhānta pair), then Madhva's prose. So it pairs like the
    # Sūtra Bhāṣya rather than segmenting as free prose. The Nyāyamālā verses it quotes are
    # typed Mula, hence the two commentary types.
    # Karma Nirṇaya: Vedic mantras (Mula, prose Brāhmaṇa passages) with Madhva's gloss.
    # skip_svara holds the accented ones — those are in the user's śruti recording — while
    # the unaccented mūla renders. mula_prose because a mūla is otherwise one pāda, and these
    # run to hundreds of akṣaras.
    "karma_nirnaya": dict(
        mula="Mula", comm="Sarvamula", colophons=("Colophon_Sarvamula",),
        render_mula=True, skip_svara=True, mula_kind="gadya", mula_prose=True,
        long_padya_aksara=True,
        ref="columns", prefix="knr", stem="KNR", orphans=True, fallback="length",
        part_kind="bhashya"),
    "nyaya_vivarana": dict(
        mula="Title", comm=("Sarvamula", "Mula"), colophons=("Colophon_Sarvamula",),
        render_mula=True, mula_kind="sutra", mula_prose=True, ref="columns",
        prefix="nvv", stem="NVV", orphans=True, fallback="length",
        part_kind="bhashya"),
    "vishnu_tatva_nirnaya": dict(
        mula="__none__", comm="Sarvamula", colophons=("Colophon_Sarvamula",),
        render_mula=False, mula_kind="padya", ref="columns",
        prefix="vtn", stem="VTN", orphans=True, fallback="length",
        part_kind="mula"),
    "tatvodyota": dict(
        mula="__none__", comm="Sarvamula", colophons=("Colophon_Sarvamula",),
        render_mula=False, mula_kind="padya", ref="columns",
        prefix="tdy", stem="TDY", orphans=True, fallback="length",
        part_kind="mula"),
    # The seven smaller Upaniṣad bhāṣyas. render_mula stays TRUE — this edition prints most
    # of the śruti unaccented and the voice can recite that — but skip_svara drops the
    # individual passages that carry accent marks, which are listed for hand recitation in
    # Sarvamula_shruti_to_record.md. Their absence leaves a gap those recordings will fill.
    "taittiriya_bhashya": dict(
        mula="Mula", comm="Sarvamula",
        colophons=("Colophon_Sarvamula", "Colophon_Mula"),
        render_mula=True, skip_svara=True, mula_kind="padya", mula_meter="detect",
        ref="columns", prefix="tai", stem="TAI", orphans=True, fallback="length",
        part_kind="bhashya"),
    "kathaka_bhashya": dict(
        mula="Mula", comm="Sarvamula",
        colophons=("Colophon_Sarvamula", "Colophon_Mula"),
        render_mula=True, skip_svara=True, mula_kind="padya", mula_meter="detect",
        ref="columns", prefix="kat", stem="KAT", orphans=True, fallback="length",
        part_kind="bhashya"),
    "atharvana_bhashya": dict(
        mula="Mula", comm="Sarvamula",
        colophons=("Colophon_Sarvamula", "Colophon_Mula"),
        render_mula=True, skip_svara=True, mula_kind="padya", mula_meter="detect",
        ref="columns", prefix="ath", stem="ATH", orphans=True, fallback="length",
        part_kind="bhashya"),
    "manduka_bhashya": dict(
        mula="Mula", comm="Sarvamula",
        colophons=("Colophon_Sarvamula", "Colophon_Mula"),
        render_mula=True, skip_svara=True, mula_kind="padya", mula_meter="detect",
        ref="columns", prefix="man", stem="MAN", orphans=True, fallback="length",
        part_kind="bhashya"),
    "shatprashna_bhashya": dict(
        mula="Mula", comm="Sarvamula",
        colophons=("Colophon_Sarvamula", "Colophon_Mula"),
        render_mula=True, skip_svara=True, mula_kind="padya", mula_meter="detect",
        ref="columns", prefix="spr", stem="SPR", orphans=True, fallback="length",
        part_kind="bhashya"),
    "talavakara_bhashya": dict(
        mula="Mula", comm="Sarvamula",
        colophons=("Colophon_Sarvamula", "Colophon_Mula"),
        render_mula=True, skip_svara=True, mula_kind="padya", mula_meter="detect",
        ref="columns", prefix="tal", stem="TAL", orphans=True, fallback="length",
        part_kind="bhashya"),
    "ishavasya_bhashya": dict(
        mula="Mula", comm="Sarvamula",
        colophons=("Colophon_Sarvamula", "Colophon_Mula"),
        render_mula=True, skip_svara=True, mula_kind="padya", mula_meter="detect",
        ref="columns", prefix="isa", stem="ISA", orphans=True, fallback="length",
        part_kind="bhashya"),
    # The Upaniṣad bhāṣyas. These three printed the gloss with NO Upaniṣad text between
    # the glosses; the mūla was reverse-fetched from anandamakaranda.in by matching the
    # bhāṣya (insert_upanishad_mula.py) and now sits in `entries` as Mula, so they pair
    # like any other work. The sourced text carries no Vedic accent, so unlike the other
    # Upaniṣads nothing is held back for hand recitation — skip_svara is a no-op here but
    # is left on, so an accented text substituted later is held rather than mispronounced.
    # Prose with no verse numbers, and entries far larger
    # than anything else in the corpus — kanva_bhashya seq 14 alone is 23,836 akṣaras (~95
    # min of audio). They need no bespoke segmenter after all: split_parts already divides a
    # block by DURATION, preferring the point where Madhva resumes his own prose after a
    # citation, so an entry becomes as many parts as its length requires.
    "kanva_bhashya": dict(
        mula="Mula", comm="Sarvamula", colophons=("Colophon_Sarvamula", "Colophon_Mula"),
        render_mula=True, skip_svara=True, mula_kind="gadya", mula_prose=True, mula_label="upanishad", ref="columns",
        prefix="kan", stem="KAN", orphans=True, fallback="length"),
    "aitareya_bhashya": dict(
        mula="Mula", comm="Sarvamula", colophons=("Colophon_Sarvamula",),
        render_mula=True, skip_svara=True, mula_kind="gadya", mula_prose=True, mula_label="upanishad", ref="columns",
        prefix="ait", stem="AIT", orphans=True, fallback="length"),
    "chandogya_bhashya": dict(
        mula="Mula", comm="Sarvamula", colophons=("Colophon_Sarvamula",),
        render_mula=True, skip_svara=True, mula_kind="gadya", mula_prose=True, mula_label="upanishad", ref="columns",
        prefix="cha", stem="CHA", orphans=True, fallback="length"),
    # The remaining Daśa Prakaraṇas — Madhva's short independent treatises, each a few
    # hundred akṣaras of mixed prose and verse. Same treatment as Viṣṇutattvanirṇaya: no mūla
    # to pair, so every entry falls through as an orphan and is segmented as prose, with the
    # unquoted-verse promotion picking the ślokas out of it. Karma Nirṇaya is deliberately
    # NOT here — it quotes Vedic hymns, which need svara and a different voice.
    "pramana_lakshana": dict(
        mula="__none__", comm="Sarvamula", colophons=("Colophon_Sarvamula",),
        render_mula=False, mula_kind="padya", ref="columns",
        prefix="pl", stem="PL", orphans=True, fallback="length", part_kind="mula"),
    "katha_lakshana": dict(
        mula="__none__", comm="Sarvamula", colophons=("Colophon_Sarvamula",),
        render_mula=False, mula_kind="padya", ref="columns",
        prefix="kl", stem="KL", orphans=True, fallback="length", part_kind="mula"),
    "upadhi_khandana": dict(
        mula="__none__", comm="Sarvamula", colophons=("Colophon_Sarvamula",),
        render_mula=False, mula_kind="padya", ref="columns",
        prefix="uk", stem="UK", orphans=True, fallback="length", part_kind="mula"),
    "mayavada_khandana": dict(
        mula="__none__", comm="Sarvamula", colophons=("Colophon_Sarvamula",),
        render_mula=False, mula_kind="padya", ref="columns",
        prefix="mk", stem="MK", orphans=True, fallback="length", part_kind="mula"),
    "prapancha_mithyatva_khandana": dict(
        mula="__none__", comm="Sarvamula", colophons=("Colophon_Sarvamula",),
        render_mula=False, mula_kind="padya", ref="columns",
        prefix="pmk", stem="PMK", orphans=True, fallback="length", part_kind="mula"),
    "tatva_sankhyana": dict(
        mula="__none__", comm="Sarvamula", colophons=("Colophon_Sarvamula",),
        render_mula=False, mula_kind="padya", ref="columns",
        prefix="tsk", stem="TSK", orphans=True, fallback="length", part_kind="mula"),
    "tatva_viveka": dict(
        mula="__none__", comm="Sarvamula", colophons=("Colophon_Sarvamula",),
        render_mula=False, mula_kind="padya", ref="columns",
        prefix="tvk", stem="TVK", orphans=True, fallback="length", part_kind="mula"),
    "bhagavata_tatparya": dict(
        mula="Bhagavatam", comm="Tatparya",
        colophons=("Colophon_Bhagavatam", "Colophon_Skandha", "Mangala"),
        render_mula=False, mula_kind="padya", ref="columns",
        prefix="bt", stem="BhTN", orphans=True, fallback="length", part_kind="tatparya"),
}


def cfg_for(work):
    if work not in WORKS:
        sys.exit(f"{work}: not a registered shape-A work. Add it to WORKS "
                 f"(known: {', '.join(sorted(WORKS))})")
    return dict(WORKS[work], work=work)      # the slug IS the R2 directory


def sutra_ref(text):
    """'॥ [ॐ] जन्माद्यस्य यतः [ॐ]॥ १/१/२॥' -> '1/1/2' (None if absent)."""
    m = _REF.search(text or "")
    if not m:
        return None
    return "/".join(g.translate(_DEVA_DIGITS) for g in m.groups())


# ── chandas detection (imported without dragging in torch) ────────────────────
def _make_detector():
    sys.path.insert(0, VAGDHENU_SRC)
    try:
        from indic_transliteration import sanscript
        from tts_syllabify import syllabify
        from tts_weight import tag_weights
        from tts_meter import detect_meter
        import prep_text as PT
    except Exception as e:                      # detection is optional
        print(f"[warn] chandas detection unavailable ({e}); using {FALLBACK_METER}",
              file=sys.stderr)
        return lambda text: ""

    def detect(text):
        try:
            d = PT.to_deva(text).replace("॥", "|").replace("।", "|").replace("\n", " | ")
            d = "".join(c for c in d
                        if not (c.isdigit() or ("०" <= c <= "९")) and c not in "\"'“”‘’()")
            slp = re.sub(r"\s+", " ",
                         sanscript.transliterate(d, sanscript.DEVANAGARI, sanscript.SLP1)).strip()
            s = syllabify(slp); tag_weights(s)
            n = detect_meter(s).get("name", "unknown")
        except Exception:
            return ""
        if n in ("unknown", None, ""):
            return ""
        return "anushtubh" if str(n).startswith("anushtubh") else n

    return detect


# ── identity (renderer and assembler MUST agree on these) ─────────────────────
# Two digits is enough: the largest block is 57 units. Kept at two so the clips
# already rendered for 1.1.2 (bsb_1_1_2_u01_sutra …) stay valid.
def pada_clip_id(block_id, n, utype, k, pada, meter):
    """ONE CLIP PER PADA — the Bhāgavatam arrangement.

    Bhāgavatam's shards were one hemistich per clip (`BhP_01.001.002_h1`, a single-element
    `padas`), gating ON, and it worked cleanly. That is why: with one segment per clip,
    `gate(soft=(soft and i==0))` applies to the only segment, so the per-pada onset bug
    cannot arise, there are no renderer-inserted internal gaps, and every segment sits in
    the model's trained size range. Packing N padas into one clip is what produced all of
    our onset damage. Gaps become purely an assembly concern, which is where we want them.
    """
    h = hashlib.sha1((pada + "|" + (meter or "")).encode("utf-8")).hexdigest()[:6]
    return f"{block_id}_u{n:02d}_{utype}_p{k:02d}_{h}"


def clip_id(block_id, n, utype, padas=None, meter=None):
    """CONTENT-ADDRESSED: the trailing hash covers the rendered text and the meter.

    Unit numbers are NOT stable across re-segmentation — promoting one unquoted verse
    in bsb_1_1_1 shifted every later unit by one, leaving 44 of 59 clips with an
    unchanged id but different text. Without the hash, --resume-from happily reuses
    that stale audio and the error is silent. With it, changed text yields a new id,
    so a stale clip simply is not found and gets re-rendered, while genuinely unchanged
    units still hit the cache."""
    base = f"{block_id}_u{n:02d}_{utype}"
    if padas is None:
        return base
    h = hashlib.sha1(("␟".join(padas) + "|" + (meter or "")).encode("utf-8")).hexdigest()[:6]
    return f"{base}_{h}"


def part_id(block_id, k, n_parts):
    """Single-part blocks keep the bare block id, so the common case has no _p1 suffix."""
    return block_id if n_parts == 1 else f"{block_id}_p{k}"


def audio_path(block_id, ref, part, n_parts, kind="bhashya", ext="m4a", cfg=None):
    """Deterministic R2 path — mirrors Bhāgavatam: derived from structure, no manifest.
       sutra_bhashya/1/1/BSB_1.1.2_sutra.m4a   the Mula entry
       sutra_bhashya/1/1/BSB_1.1.2.m4a         the Sarvamula entry (_p2… if split)

    The sutra is a SEPARATE file from the bhāṣya: they are separate DB rows (Mula vs
    Sarvamula) and the reader shows them as separate blocks, so one file each restores
    the 1 entry = 1 file mapping the Bhāgavatam player assumes."""
    cfg = cfg or cfg_for(WORK)
    if ref:
        # Refs are not uniformly three-deep: BSB is adhyāya/pāda/sūtra and the Bhāgavata is
        # skandha/adhyāya/verse, but the Gītā works are adhyāya/verse. Directory depth
        # follows the ref minus its last element, so a two-part ref nests one level.
        bits = ref.split("/")
        stem = f"{cfg['stem']}_" + ".".join(bits)
        dirs = "/".join(bits[:-1]) or "misc"
        m = re.search(r"([a-z])$", block_id)      # dup-disambiguated id (see segment_block)
        if m:
            stem += m.group(1)
    else:
        stem, dirs = block_id, "misc"
    if kind == "sutra":
        stem += "_sutra"
    elif kind == "mula":
        stem += "_mula" + (f"_p{part}" if n_parts > 1 else "")
    elif n_parts > 1:
        stem += f"_p{part}"
    return f"{cfg['work']}/{dirs}/{stem}.{ext}"


def n_aksharas(s):
    return len(re.findall(r"[अ-हा-ौ]", s or "")) or len(s or "")


def split_unquoted_verses(unit, detect):
    """R3 types text as padya only when it sits inside “…”. The maṅgala śloka opening
    each pāda's bhāṣya is NOT quoted, so it arrives typed gadya — and gadya splits at
    visargas, which cuts mid-pāda (नारायणं गुणैः | सर्वैरुदीर्णं… instead of
    …गुणैः सर्वै | रुदीर्णं…) and chants it against the prose reference.

    In this edition ॥ delimits verses, so test each ॥-span rather than the whole chunk:
    the chunk usually holds the verse AND the prose that follows it, so testing the
    whole thing detects nothing, while testing the span isolates the verse exactly.

    Returns a LIST of units (a gadya chunk may become gadya/padya/gadya).

    Guard: tts_meter identifies anuṣṭubh by syllable count alone (4x8), so 32-syllable
    PROSE matches it. Only promote an anuṣṭubh span when it is daṇḍa-split into even
    hemistichs; strict vṛttas have exact weight patterns that prose cannot hit by
    accident and are promoted on detection alone."""
    from segment import padya_padas, gadya_padas, depranava
    if unit["type"] != "gadya" or not unit.get("raw"):
        return [unit]
    # An entry on the VERSE_ENTRIES list is printed as verse but punctuated with single
    # daṇḍas only, so the ॥-span test below can never fire. Split it on the daṇḍa and let
    # assign_meter read the metre, exactly as for any other padya unit.
    if unit.get("src_padya"):
        pad, _ = depranava(padya_padas(unit["raw"]))
        if len(pad) >= 2:
            return [{"type": "padya", "padas": pad, "text": " ".join(pad),
                     "opens_pranava": False, "raw": unit["raw"]}]
        return [unit]
    if "॥" not in unit["raw"]:
        return [unit]
    outs = []
    for span in unit["raw"].split("॥"):
        span = span.strip(" ।")
        if not span:
            continue
        # Two independent ways to recognise a verse, because each fails where the other
        # works: tts_meter reads the weight pattern but needs four daṇḍa-separated pādas,
        # while syllable arithmetic settles the case it abstains on — a maṅgala printed as
        # two hemistichs (the Bhāgavata Tātparya's opening is 84 syllables = 4x21,
        # sragdharā, split 42+42). anuṣṭubh is excluded from the arithmetic route: 32
        # syllables of prose hits it by accident, which is what the daṇḍa guard below
        # exists for.
        def classify(t):
            d = detect(t)
            k = METER_ALIAS.get(d, d) if d else ""
            if k and k in BANK_KEYS and d not in NO_REFERENCE:
                return d, k
            parts = [x for x in re.split(r"[।]", t) if x.strip()]
            if len(parts) in (2, 4):
                lens = [syllables(x) for x in parts]
                if len(set(lens)) == 1 and lens[0]:
                    per = lens[0] // (2 if len(parts) == 2 else 1)
                    for kk, nn in BANK_SYLLABLES.items():
                        if nn == per and kk in BANK_KEYS and kk != "anuṣṭubh":
                            return kk, kk
            return None, ""

        det, key = classify(span)
        verse = bool(key)
        lead = ""
        if not verse:
            # A maṅgala verse can carry the WORK'S TITLE in front of it with no daṇḍa
            # between — "…विरचितं श्रीमद्भागवततात्पर्यम् सृष्टिस्थित्यप्यये…" — so the span
            # is title+verse and neither route fires on the whole of it. Drop up to six
            # leading words; if the remainder classifies, the prefix was the title.
            words = span.split()
            for n in range(1, min(7, len(words))):
                tail = " ".join(words[n:])
                d2, k2 = classify(tail)
                if k2 and k2 != "anuṣṭubh":
                    lead, span, det, key, verse = " ".join(words[:n]), tail, d2, k2, True
                    break
        if verse and key == "anuṣṭubh":
            halves = padya_padas(span)
            verse = len(halves) >= 2          # real ślokas break on daṇḍas; prose does not
        if verse:
            if lead:                          # the title stays prose, ahead of the verse
                lp, lopens = depranava(gadya_padas(lead))
                if lp:
                    outs.append({"type": "gadya", "padas": lp, "text": " ".join(lp),
                                 "opens_pranava": lopens, "raw": lead})
            pad, _ = depranava(padya_padas(span))
            if pad:
                outs.append({"type": "padya", "padas": pad, "text": " ".join(pad),
                             "opens_pranava": False, "raw": span, "_meter": key})
                continue
        pad, opens = depranava(gadya_padas(span))
        if pad:
            outs.append({"type": "gadya", "padas": pad, "text": " ".join(pad),
                         "opens_pranava": opens, "raw": span})
    return outs or [unit]


# ── mūla entries that hold MANY numbered verses ───────────────────────────────
# BSB's Mula is one aphorism per entry. The Gītā works print the mūla in slabs — one entry
# can carry thirty verses and 4,262 characters — so treating an entry as a unit produced a
# single 1,541-syllable "pāda" that no TTS call could render. Split on the printed verse
# number, which also supplies the ref (॥ १/१॥ -> 1/1) that the columns lack.
_GVNUM = re.compile(r"॥\s*([०-९\d]+)\s*/\s*([०-९\d]+)\s*॥")


def _devnum(x):
    return x.translate(_DEVA_DIGITS)


def mula_verse_units(text):
    """A mūla slab -> one unit per printed verse, pādas split on the daṇḍa."""
    out, pos = [], 0
    pieces = []
    for m in _GVNUM.finditer(text):
        pieces.append((text[pos:m.start()], f"{_devnum(m.group(1))}/{_devnum(m.group(2))}"))
        pos = m.end()
    if text[pos:].strip():
        pieces.append((text[pos:], None))
    for body, ref in pieces:
        padas = [seg_clean(x) for x in re.split(r"[।॥]", body)]
        # The speaker attribution is not part of the verse. The edition prints it inline —
        # "धृतराष्ट्र उवाच– धर्मक्षेत्रे…" — with no daṇḍa, so it landed inside the first pāda
        # and was SYNTHESISED IN ONE BREATH with the opening line, giving the Gītā's 33
        # uvāca verses no pause where a reciter always takes one. Split into its own pāda so
        # assembly can put a boundary there; it cannot be fixed later, the clip is one sound.
        padas = [y for x in padas for y in re.split(r"(?<=उवाच)\s*[–—-]?\s*", x, maxsplit=1)]
        padas = [x.strip() for x in padas]
        padas = [x for x in padas if x and _AK.search(x)]
        if not padas:
            continue
        # type is padya, not sutra: these are verses, and the sūtra type would splice the
        # pranava exemplar around every one of them (a BSB convention, wrong here).
        # is_mula rather than a distinct type: the type drives the pranava framing (sutra)
        # and the display/gap rules (padya), all of which are right for a Gītā verse. The
        # flag only decides which TILE it belongs to.
        out.append({"type": "padya", "is_mula": True, "padas": padas, "verse": ref,
                    "bounds": ["hard"]*len(padas), "text": " ".join(padas)})
    return out


def assign_meter(unit, detect, fb="fixed", mula_meter="rule"):
    if unit["type"] == "sutra":
        # BSB's mūla is an aphorism — prose, so a fixed reference is right. The Gītā works'
        # mūla is a VERSE, and the Gītā is not uniformly anuṣṭubh (ch. 11 and 15 carry
        # triṣṭubh/upajāti), so forcing the sūtra voice there would chant a third of the
        # mūla to the wrong metre. Detect it like any other verse in that case.
        if mula_meter != "detect":
            return SUTRA_METER, "rule:sutra"
        det = detect(" । ".join(unit["padas"]))
        key = METER_ALIAS.get(det, det) if det else ""
        if key and key in BANK_KEYS and det not in NO_REFERENCE:
            return key, "detected:mula"
        m, tag = fallback_meter(unit["padas"], SUTRA_METER)
        return m, f"{tag}:mula"
    if unit["type"] == "gadya":
        if PROSE_MBTN_MAX_AKSHARA and n_aksharas(unit["text"]) <= PROSE_MBTN_MAX_AKSHARA:
            return PROSE_MBTN, "rule:short-prose"
        return PROSE_METER, "rule:prose"
    # `fb` is the work's fallback policy: "fixed" keeps FALLBACK_METER (BSB and
    # Anuvyākhyāna are shipped and stay byte-identical — user call 2026-08-08: a quotation
    # in the wrong vṛtta is acceptable, not worth re-rendering), "length" picks the
    # nearest-length reference (see fallback_meter). New works use "length".
    def fb_for(why):
        if fb == "length":
            m, tag = fallback_meter(unit["padas"])
            return m, f"{tag}:{why}"
        return FALLBACK_METER, f"fallback:{why}"
    det = detect(" । ".join(unit["padas"]))
    if not det:
        return fb_for("undetected")
    if det in NO_REFERENCE:
        return fb_for(f"no-ref({det})")
    key = METER_ALIAS.get(det, det)
    if key not in BANK_KEYS:
        return fb_for(f"unresolved({det})")
    return key, "detected"


# ── fallback by SYLLABLE COUNT, not a fixed metre ─────────────────────────────
# A quotation that chandas detection cannot name still has a MEASURABLE pāda length, and
# the reference bank is organised by metre — i.e. by pāda length. Falling back to one fixed
# metre ignored that: 87% of bhagavata_tatparya's undetected pādas are 16 syllables (an
# anuṣṭubh hemistich) and only 0.5% are vasantatilakā-shaped, so a fixed vasantatilakā
# fallback would have chanted 3,044 pādas to the wrong rhythm — and ASR-QC cannot see it,
# because a verse in the wrong metre still transcribes perfectly. The same flaw is in the
# shipped works: BSB 698/1490 fallback pādas and Anuvyākhyāna 197/399 are anuṣṭubh-shaped.
# Pick the bank reference whose pāda length is nearest the observed one instead.
_VIRAMA = "्"

def syllables(s):
    """Devanagari syllable count: independent vowels + consonants not carrying virāma."""
    n = 0
    for i, ch in enumerate(s):
        if "अ" <= ch <= "औ":
            n += 1
        elif "क" <= ch <= "ह":
            if i + 1 >= len(s) or s[i + 1] != _VIRAMA:
                n += 1
    return n

# syllables per pāda for the references we actually have wavs for
BANK_SYLLABLES = {
    "anuṣṭubh": 8, "pramāṇikā": 8, "indravajrā": 11, "upendravajrā": 11, "upajāti": 11,
    "rathoddhatā": 11, "drutavilambita": 12, "bhujaṅgaprayāta": 12, "indravaṃśā": 12,
    "vaṃśastha": 12, "vasantatilakā": 14, "mālinī": 15, "śālinī": 11,
    "śārdūlavikrīḍita": 19, "sragdharā": 21,
}


def fallback_meter(padas, default=FALLBACK_METER):
    """Nearest-length reference for an unidentified quotation.

    A hemistich counts as two pādas, so 16 syllables reads as anuṣṭubh — that is the single
    commonest shape in every work here, since most citations are printed half-verse by
    half-verse."""
    lens = [syllables(p) for p in padas if p.strip()]
    if not lens:
        return default, "fallback:empty"
    n = sorted(lens)[len(lens) // 2]                 # median pāda, robust to one odd line
    best, err = default, None
    for k, per in BANK_SYLLABLES.items():
        if k not in BANK_KEYS:
            continue
        e = min(abs(n - per), abs(n - 2 * per))      # printed as a pāda or as a hemistich
        if err is None or e < err:
            best, err = k, e
    # Nothing close enough to be a claim — keep the work's declared default.
    return (best, f"fallback:len{n}") if err is not None and err <= 2 else (default, f"fallback:len{n}-nomatch")


def load_blocks(db=DB, work=WORK, cfg=None):
    """Walk the work in seq order, pairing each mūla with the commentary that follows."""
    cfg = cfg or cfg_for(work)
    MULA, COMM = cfg["mula"], cfg["comm"]
    # `comm` may name SEVERAL types. Nyāya Vivaraṇa heads each section with the sūtra (typed
    # Title) and quotes 15 Nyāyamālā verses from the Anuvyākhyāna (typed Mula); with only one
    # commentary type those 2,331 akṣaras matched no branch below and were dropped without a word.
    COMMS = (tuple(COMM) if isinstance(COMM, (tuple, list)) else (COMM,)) + tuple(cfg["colophons"])
    con = sqlite3.connect(db); con.row_factory = sqlite3.Row
    rows = list(con.execute(
        "select seq, content_type, heading_level, text_dev, skandha, adhyaya, verse "
        "from entries where work=? order by seq", (work,)))
    con.close()

    blocks, h = [], {1: None, 2: None, 3: None}
    held = []                     # svara-marked mūla, excluded from rendering
    pending = None          # a Mula awaiting its bhāṣya
    orphans = []
    # Parenthetical spans are editorial apparatus, never recitation: scripture references
    # ("(ब्र.सू. २.२.२९)"), avagraha marks "(ऽ)", variant readings "(एनं)", section names.
    # Read aloud they are noise. Off for the shipped works, which they would re-index.
    strip = cfg.get("strip_parens", True)
    for r in rows:
        ct, txt = r["content_type"], r["text_dev"] or ""
        if strip and txt:
            txt = re.sub(r"\s*\([^)]{0,60}\)", " ", txt)
        # Square brackets are DELIMITERS, never sound. Two kinds are printed here and they
        # need opposite treatment: a group with text inside it — "[अर्जुन उवाच",
        # "[खण्डार्थनिर्णयापरनामा]", "ते[ऽ]निन्दया" — is real recitation wearing an editorial
        # wrapper, so unwrap it; a group with nothing recitable — "[-]", "[---]" marking a
        # lacuna — is apparatus entire, so delete it. Left alone the model voices a bare
        # bracket as "a", which is what was heard at the head of Saṅgraha Bhāṣya's maṅgala.
        if txt:
            txt = _debracket(txt)
        if ct and ct.startswith("Heading"):
            lvl = r["heading_level"] or int(ct[-1])
            h[lvl] = txt
            for deeper in range(lvl + 1, 4):
                h[deeper] = None
            continue
        if ct == MULA:
            if pending is not None:                    # mūla with no commentary after it
                blocks.append(dict(pending, bhashya=""))
            # per-ENTRY exclusion, not per-work: render_mula is all-or-nothing, but an
            # Upaniṣad bhāṣya mixes accented and unaccented mūla in the same work
            svara = cfg.get("skip_svara") and bool(SVARA.search(txt))
            if svara:
                held.append({"seq": r["seq"], "aksharas": len(_AK.findall(txt))})
            # The ref is printed inside the aphorism in BSB, but lives in columns for a
            # verse-numbered work — a Bhāgavatam verse carries skandha/adhyaya/verse.
            if cfg["ref"] == "text":
                ref = sutra_ref(txt)
            elif cfg["ref"] == "mula_verse":
                m0 = _GVNUM.search(txt)
                ref = f"{_devnum(m0.group(1))}/{_devnum(m0.group(2))}" if m0 else None
            else:
                ref = ("/".join(str(r[k]) for k in ("skandha", "adhyaya", "verse"))
                       if r["verse"] is not None else None)
            pending = {"seq": r["seq"], "sutra": "" if svara else txt, "ref": ref,
                       "svara_held": svara,
                       "adhyaya": h[1], "pada": h[2], "adhikarana": h[3]}
            continue
        if ct in COMMS:
            if pending is not None:
                # bseq is the Sarvamula entry's OWN seq. A block spans two entries (Mula +
                # Sarvamula) and each part belongs to exactly one of them, so the reader can
                # show each entry's text once — under its own player — instead of printing
                # the bhāṣya twice (once as the Mula row's audio lines, once as its own row).
                blocks.append(dict(pending, bhashya=txt, bseq=r["seq"], kind="sutra_block"))
                pending = None
            else:
                orphans.append({"seq": r["seq"], "bseq": r["seq"], "sutra": "", "ref": None, "bhashya": txt,
                                "adhyaya": h[1], "pada": h[2], "adhikarana": h[3],
                                "kind": "colophon" if ct in cfg["colophons"] else "prose_only"})
            continue
    if pending is not None:
        blocks.append(dict(pending, bhashya="", kind="sutra_block"))
    # A content type that is neither mūla nor commentary matches no branch above and is
    # silently discarded. Say so — this is how Nyāya Vivaraṇa nearly lost its Nyāyamālā verses.
    seen_ct = {r["content_type"] for r in rows if not (r["content_type"] or "").startswith("Heading")}
    unknown = seen_ct - {MULA} - set(COMMS) - {"Subheading", "Subject"}
    if unknown:
        drop = sum(len(_AK.findall(r["text_dev"] or "")) for r in rows
                   if r["content_type"] in unknown)
        print(f"  !! {work}: content types NOT segmented: {sorted(unknown)} "
              f"({drop:,} akṣaras dropped)")
    if held:
        print(f"  svara-marked mūla held back: {len(held)} passages, "
              f"{sum(x['aksharas'] for x in held)} akṣaras")
    return blocks, orphans


def segment_block(b, detect, cfg=None):
    cfg = cfg or cfg_for(WORK)
    # When the mūla is reused rather than rendered, it must not become a unit at all —
    # otherwise the sutra part would re-record audio that already exists elsewhere.
    mula = b["sutra"] if cfg["render_mula"] else ""
    if mula and cfg.get("mula_verses"):
        units = mula_verse_units(mula) + build_units("", b["bhashya"])
    else:
        units = build_units(mula, b["bhashya"]) if mula else build_units("", b["bhashya"])
    # Drop pādas with no akṣara. Punctuation left stranded by a daṇḍa or bracket split
    # ("–", "()", ".") is not recitable: three such pādas were queued for bhagavata_tatparya
    # and the renderer simply failed on them, leaving the work permanently 3 clips short of
    # complete. Same class as Anuvyākhyāna's quote-only pādas.
    # Off for the shipped works (sutra_bhashya, anu_vyakhyana): it shifts pāda indices and
    # so clip ids, and a re-render there is not worth it (user call 2026-08-08).
    if cfg.get("drop_empty_padas", True):
        for u in units:
            keep = [i for i, x in enumerate(u["padas"]) if _AK.search(x or "")]
            if len(keep) != len(u["padas"]):
                bounds = u.get("bounds")
                u["padas"] = [u["padas"][i] for i in keep]
                if bounds:
                    u["bounds"] = [bounds[i] for i in keep if i < len(bounds)]
    units = [u for u in units if u["padas"]]
    bid = cfg["prefix"] + "_" + (b["ref"].replace("/", "_") if b["ref"] else f"seq{b['seq']}")
    # The edition numbers two DIFFERENT sutras 2/4/10, so a ref alone is not a unique key:
    # both blocks produced bsb_2_4_10 and the second's m4a silently overwrote the first's.
    # The ref stays as printed (the reader displays it); only the id and file stem get a
    # letter, so 2/4/10 (second) -> bsb_2_4_10b / BSB_2.4.10b.m4a.
    if b.get("dup"):
        bid += chr(ord("a") + b["dup"])
    ov_block = OVERRIDES.get(bid, {})
    if b.get("bseq") in set(VERSE_ENTRIES.get(cfg["work"], ())):
        for u in units:
            if u.get("type") == "gadya" and not u.get("is_mula"):
                u["src_padya"] = True
    units = [x for u in units for x in split_unquoted_verses(u, detect)]
    # Verse padas are metrical lines and must NOT be merged — a pāda is the unit of
    # recitation. Only prose, whose pada boundaries are visarga artifacts, is merged.
    # A PROSE mūla is one pāda only because build_units treats every mūla as an aphorism —
    # right for a Brahmasūtra, wrong for the Upaniṣads, whose mūla is continuous prose: it
    # produced single clips of 499, 888 and even 12,113 akṣaras (~48 minutes in one breath).
    # These are cut exactly like the bhāṣya's prose, into 5-10 word phrases with soft
    # boundaries, so the pauses read as phrasing. The unit stays typed "sutra" because the
    # part/tile logic keys the mūla tile off that type.
    # `mula_prose` is a per-WORK flag, which cannot describe an upaniṣad whose mūla is MIXED.
    # Kena, Kaṭha, Praśna and Māṇḍūkya open in verse and continue in prose, so the flag was
    # never set for them and their prose khaṇḍas stayed one "metrical" pāda: Kena's yakṣa
    # narrative went to the model as a single 533-akṣara utterance (41 s of rushed speech), and
    # Praśna 1 as 1,067. So do not ask the config whether a mūla is prose — ask its LENGTH. Any
    # aphorism past the window is prose by construction; a real sūtra is short and untouched.
    prose_mula = cfg.get("mula_prose")
    for u in units:
        if u["type"] == "sutra" and len(u["padas"]) == 1 and \
           (prose_mula or len(_AK.findall(u["padas"][0])) > MAX_PADA_AKSHARA):
            # Cut from the RAW mūla, not from the pāda. build_units strips daṇḍas out of a
            # sūtra — correct for an aphorism, which is recited without them — but that also
            # removes the only marks a prose passage can be phrased on, so splitting the pāda
            # yields one piece and the paragraph stays a single utterance. The raw text still
            # carries them, exactly as the bhāṣya path keeps a `raw` copy for the same reason.
            pad, bnd = [], []
            for c, bd in gadya_segments(seg_clean(mula)):
                piece = re.sub(r"\s+", " ",
                               c.replace("।", "").replace("॥", "").replace(_OM, "")).strip()
                if piece:
                    pad.append(piece); bnd.append(bd)
            # accept only if the pieces say EXACTLY what the single pāda said: a mismatch means
            # the raw and cleaned forms diverge and the cut would change what is recited
            if len(pad) > 1 and \
               "".join(_AK.findall(" ".join(pad))) == "".join(_AK.findall(u["padas"][0])):
                u["padas"], u["bounds"] = pad, bnd
                u["_cut_prose"] = True
    for u in units:
        if u["type"] == "gadya" or u.get("_cut_prose") or \
           (cfg.get("mula_prose") and u["type"] == "sutra"):
            u["padas"], u["bounds"] = fit_padas(u["padas"], u.get("bounds"))
            u["text"] = " ".join(u["padas"])
        elif not u.get("bounds"):
            u["bounds"] = ["hard"]*len(u["padas"])
    # …then put back every cut the EDITION does not make. fit_padas() bounds pādas for render
    # stability by splitting at visargas; where the book prints one line that split is a
    # fabrication, and the model voices the fragment as a finished sentence. Runs AFTER
    # fit_padas so it also undoes the splits fit_padas itself introduced, and it never
    # exceeds MAX_PADA_AKSHARA — see merge_padas_to_edition.
    for u in units:
        # `bseq` is PRESENT-BUT-NONE on the 82 rows that have no commentary, so a
        # .get("bseq", seq) default would hand None to the lookup and silently do nothing.
        seq = b["seq"] if u.get("is_mula") else (b.get("bseq") or b["seq"])
        txt = b.get("sutra") if u.get("is_mula") else b.get("bhashya")
        if txt:
            merge_padas_to_edition(u, cfg["work"], seq, txt)
    # A quoted passage typed padya but with NO identified metre is prose in a citation, not a
    # metrical line — chāndogya has one such "pāda" of 195 akṣaras / 40 words, which the model
    # would have to say in a single breath. Verse padas are never touched: a pāda is the unit
    # of recitation and cutting one would break the metre. Only fallback-metre padyas get cut,
    # on word boundaries, into 5-10 word phrases with SOFT boundaries so the pauses read as
    # phrasing rather than sentence breaks.
    # Guard AGAIN, after every split. The first pass runs before split_unquoted_verses and
    # fit_padas, so pādas those produce were never checked — which is how a bare "*" reached
    # the renderer and killed two shards with "list index out of range" (no phonemes to
    # synthesise). A pāda with no akṣara is not recitable wherever it comes from.
    if cfg.get("drop_empty_padas", True):
        for u in units:
            keep = [i for i, x in enumerate(u["padas"]) if _AK.search(x or "")]
            if len(keep) != len(u["padas"]):
                bounds = u.get("bounds") or []
                u["padas"] = [u["padas"][i] for i in keep]
                u["bounds"] = [bounds[i] for i in keep if i < len(bounds)] or ["hard"]*len(keep)
                u["text"] = " ".join(u["padas"])
        units = [u for u in units if u["padas"]]
    out = []
    for i, u in enumerate(units, 1):
        promoted = u.pop("_meter", "")
        meter, why = ((promoted, "promoted:unquoted-verse") if promoted
                      else assign_meter(u, detect, cfg.get("fallback", "fixed"),
                                        cfg.get("mula_meter", "rule")))
        ov = ov_block.get(i)
        if ov:
            if "groups" in ov:
                src = u["padas"]
                # A `groups` override regroups pādas BY INDEX, so it is only meaningful against
                # the pāda list it was written for. merge_padas_to_edition now joins fragments
                # from the edition itself, which is what tsk_seq16's override was hand-written
                # to do — leaving its indices past the end of a now-shorter list. When the
                # indices no longer fit, the systematic fix has already superseded the manual
                # one and the override stands down instead of raising IndexError.
                if all(k < len(src) for g in ov["groups"] for k in g):
                    u = {**u, "padas": [" ".join(src[k] for k in g) for g in ov["groups"]]}
            if "meter" in ov:
                meter, why = ov["meter"], "override"
        # A citation typed padya whose metre could NOT be identified is prose inside a
        # quotation, not a metrical line — chāndogya has one such "pāda" of 195 akṣaras /
        # 40 words, a single unbroken breath. Cut those on word boundaries into short
        # phrases with SOFT boundaries, so the pauses read as phrasing. Verse with a
        # detected metre is never touched: a pāda is the unit of recitation.
        # Judged on AKṢARAS as well as words. A word count alone is defeated by Sanskrit
        # compounding: Karma Nirṇaya has a 112-akṣara "pāda" — some 27 seconds in one breath —
        # made of only eight words, so the word test passed it through untouched.
        if (cfg.get("split_long_padya", True) and u["type"] == "padya"
                and str(why).startswith("fallback")
                and (max(len(x.split()) for x in u["padas"]) > LONG_PADYA_WORDS
                     or (cfg.get("long_padya_aksara")
                         and max(len(_AK.findall(x)) for x in u["padas"]) > LONG_PADYA_AKSHARA))):
            newp, newb = [], []
            bnds = u.get("bounds") or ["hard"]*len(u["padas"])
            for pi, x in enumerate(u["padas"]):
                w = x.split()
                if len(w) <= LONG_PADYA_WORDS and not (cfg.get("long_padya_aksara")
                        and len(_AK.findall(x)) > LONG_PADYA_AKSHARA):
                    newp.append(x); newb.append(bnds[pi] if pi < len(bnds) else "hard"); continue
                # accumulate words up to an akṣara budget, so one long compound does not
                # ride along in a chunk that is already full
                ch, cur = [], []
                lim = LONG_PADYA_AKSHARA if cfg.get("long_padya_aksara") else 10 ** 9
                for word in w:
                    cur.append(word)
                    if (len(cur) >= LONG_PADYA_WORDS
                            or len(_AK.findall(" ".join(cur))) >= lim):
                        ch.append(" ".join(cur)); cur = []
                if cur:
                    ch.append(" ".join(cur))
                if len(ch) > 1 and len(ch[-1].split()) < 3:
                    ch[-2:] = [" ".join(ch[-2:])]
                for j, part in enumerate(ch):
                    newp.append(part)
                    newb.append((bnds[pi] if pi < len(bnds) else "hard")
                                if j == len(ch)-1 else "soft")
            u = {**u, "padas": newp, "bounds": newb, "text": " ".join(newp)}
        out.append({**u, "n": i, "meter": meter, "meter_src": why,
                    "clip": clip_id(bid, i, u["type"], u["padas"], meter),
                    "clips": [pada_clip_id(bid, i, u["type"], k, p, meter)
                              for k, p in enumerate(u["padas"], 1)]})
    # The mūla is its own file; parts are computed over the COMMENTARY units only. In BSB
    # the mūla is the sūtra; in the Gītā works it is the verses, which must not appear in the
    # bhāṣya/tātparya tiles — the reader shows them in a separate मूल tile.
    sut = [u for u in out if u["type"] == "sutra"]
    mula = [u for u in out if u.get("is_mula")]
    bha = [u for u in out if u["type"] != "sutra" and not u.get("is_mula")]
    parts = []
    def unit_ref(u):
        return {"n": u["n"], "type": u["type"], "clips": u["clips"],
                "bounds": u.get("bounds") or ["hard"]*len(u["clips"])}

    # What the mūla tile is CALLED. It is a sūtra only in the Brahmasūtra works; in the
    # Upaniṣad bhāṣyas the same tile holds śruti, and labelling it सूत्र told the reader
    # something false about the text it was about to recite.
    mk = cfg.get("mula_label", "sutra")
    if sut:
        parts.append({"part": 0, "kind": mk, "id": f"{bid}_sutra",
                      "from": 1, "to": 1, "units": [unit_ref(sut[0])],
                      "clips": list(sut[0]["clips"]),
                      "est_sec": round(block_seconds(sut), 1),
                      "seq": b["seq"], "covers": [b["seq"]],
                      "path": audio_path(bid, b["ref"], 0, 1, kind="sutra", cfg=cfg)})   # file stem stays _sutra: renaming it would re-key every clip
    # The verses this block comments on are split by duration like anything else: Madhva
    # quotes 47 of them at the head of Gītā 1, which as one tile is 8 minutes and useless
    # to navigate.
    mspans = split_parts(mula) if mula else []
    for k, (s0, e0) in enumerate(mspans):
        us = [mula[j] for j in range(s0, e0)]
        parts.append({"part": k, "kind": "mula",
                      "id": f"{bid}_mula" + (f"_p{k+1}" if len(mspans) > 1 else ""),
                      "from": us[0]["n"], "to": us[-1]["n"],
                      "units": [unit_ref(u) for u in us],
                      "clips": [c for u in us for c in u["clips"]],
                      "est_sec": round(block_seconds(us), 1),
                      "seq": b["seq"], "covers": [b["seq"]],
                      "path": audio_path(bid, b["ref"], k + 1, len(mspans), kind="mula", cfg=cfg)})
    spans = split_parts(bha) if bha else []
    off = len(sut) + len(mula)
    # commentary tiles are numbered after whatever already went in front of them — the
    # sūtra tile in BSB (part 0), or however many mūla tiles the Gītā works produced
    base = len(parts)
    for k, (s, e) in enumerate(spans, 1):
        us = [bha[j] for j in range(s, e)]
        parts.append({"part": base + k - 1 if base else k, "kind": cfg.get("part_kind", "bhashya"),
                      "id": part_id(bid, k, len(spans)),
                      "from": off + s + 1, "to": off + e,
                      "seq": b.get("bseq", b["seq"]), "covers": [b.get("bseq", b["seq"])],
                      "units": [unit_ref(u) for u in us],
                      "clips": [c for u in us for c in u["clips"]],
                      "est_sec": round(block_seconds(us), 1),
                      "path": audio_path(bid, b["ref"], k, len(spans), cfg=cfg)})
    return {"id": bid, "ref": b["ref"], "seq": b["seq"], "kind": b.get("kind"),
            "adhyaya": b["adhyaya"], "pada": b["pada"], "adhikarana": b["adhikarana"],
            "est_sec": round(block_seconds(out), 1), "parts": parts, "units": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--out", default="")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--sutra", default="", help="print one block, e.g. 1/1/2")
    ap.add_argument("--work", default=WORK, help="shape-A work slug (see WORKS)")
    a = ap.parse_args()

    cfg = cfg_for(a.work)
    globals()["WORK"] = a.work
    detect = _make_detector()
    blocks, orphans = load_blocks(a.db, a.work, cfg)
    if cfg["orphans"]:
        # A colophon follows no mūla, so the pairing walk files it as an orphan — but it is
        # recited text and belongs in the corpus. BSB leaves these out only because it is
        # already shipped.
        blocks = sorted(blocks + orphans, key=lambda x: x["seq"])

    if a.sutra:
        b = next((x for x in blocks if x["ref"] == a.sutra), None)
        if not b:
            sys.exit(f"no block with ref {a.sutra}")
        s = segment_block(b, detect, cfg)
        print(f"{s['id']}  {s['adhikarana']}")
        for u in s["units"]:
            print(f"  [{u['n']:02d}] {u['type']:5s} meter={u['meter']:12s} "
                  f"({u['meter_src']}) {len(u['padas'])} pada(s)")
            for p in u["padas"]:
                print(f"        · {p}")
        return

    # A block with no printed ref inherits the PRECEDING verse's. The Gītā works print a
    # ref only on the mūla slabs, so ~450 blocks of upodghāta and inter-verse prose would
    # otherwise key on source seq and land in a flat misc/ directory, unfindable by
    # reference. Inheriting puts them with the verse they comment on; the dup counter below
    # then distinguishes them (1/1, 1/1b, 1/1c…). Blocks BEFORE the first verse have
    # nothing to inherit and keep their seq id.
    if cfg.get("inherit_ref"):
        last = None
        for b in blocks:
            if b.get("ref"):
                last = b["ref"]
            elif last:
                b["ref"] = last
    seen = {}
    for b in blocks:                       # tag repeats of a ref before ids are minted
        k = b["ref"] or f"seq{b['seq']}"
        b["dup"] = seen.get(k, 0)
        seen[k] = b["dup"] + 1
    segmented = [segment_block(b, detect, cfg) for b in blocks]
    segmented = [x for x in segmented if x["units"]]      # a mūla with no commentary to
                                                          # recite yields nothing

    n_units = sum(len(s["units"]) for s in segmented)
    n_padas = sum(len(u["padas"]) for s in segmented for u in s["units"])
    by_type, by_meter, by_src = {}, {}, {}
    for s in segmented:
        for u in s["units"]:
            by_type[u["type"]] = by_type.get(u["type"], 0) + 1
            by_meter[u["meter"]] = by_meter.get(u["meter"], 0) + 1
            by_src[u["meter_src"]] = by_src.get(u["meter_src"], 0) + 1

    no_ref = [s["id"] for s in segmented if not s["ref"]]
    print(f"blocks (Mula+bhāṣya) : {len(segmented)}")
    print(f"  without a parsed ref: {len(no_ref)}  {no_ref[:6]}")
    print(f"  orphan prose/colophon blocks not attached to a sutra: {len(orphans)}")
    print(f"units  (= clips)     : {n_units}")
    print(f"padas  (= TTS calls) : {n_padas}")
    print(f"\nunits by type : " + ", ".join(f"{k}={v}" for k, v in sorted(by_type.items())))
    print(f"units by meter: " + ", ".join(f"{k}={v}" for k, v in
                                          sorted(by_meter.items(), key=lambda x: -x[1])))
    print(f"meter source  : " + ", ".join(f"{k}={v}" for k, v in
                                          sorted(by_src.items(), key=lambda x: -x[1])))

    if a.out:
        json.dump(segmented, open(a.out, "w"), ensure_ascii=False, indent=1)
        print(f"\n-> {a.out}")


if __name__ == "__main__":
    main()
