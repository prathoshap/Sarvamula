#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sarvamula → Vagdhenu text-prep / segmentation.
Turns a reader block (sutra + bhashya prose + embedded verse quotes) into an
ordered list of render units, applying the ironing-out rules:

  R1  Sutra: strip the editorial [ ] around the pranava ( om), keep the om.
  R2  Gadya (prose): render each visarga separately -> split the prose so every
      visarga becomes segment-final (prep_text.visarga_echo_final then gives it
      the chant echo:  yataH -> "yataha").
  R3  Padya: every quoted "..." verse/mantra is its OWN render unit (verses never
      run together); each unit is split into padas on dandas for meter detection.

Output: units = [ {type: gadya|padya, text, padas:[...]} , ... ] in reading order.
This is script/segmentation only — no GPU, no model. The shard for render.py is
built from `padas`; meter is auto-detected on ece (render_core.detect_meter_key).
"""
import re, json, sys

DANDA = "।"; DDANDA = "॥"; VISARGA = "ः"; OM = "ॐ"

# ── R1 ────────────────────────────────────────────────────────────────────────
def strip_om_brackets(t):
    # [ॐ] -> ॐ  (and any stray editorial square brackets)
    return t.replace("[" + OM + "]", OM).replace("[", "").replace("]", "")

# ── quote splitting (curly “ ”, single ‘ ’, or straight ") -> gadya / padya ────
# Editions are not consistent about which quote mark they use: BSB prints doubles (740 in
# a 300-entry sample, singles twice), while the Bhāgavata Tātparya prints SINGLES only
# (363/366 in the same-size sample, zero doubles). A doubles-only pattern therefore found
# no quotations at all there and folded every citation into the surrounding prose — the
# quotation would have been recited as bhāṣya rather than as verse.
# Doubles are tried first so a single mark nested inside a double-quoted passage does not
# split it.
_QUOTE = re.compile(r'[“"]([^”"]*)[”"]|‘([^’]*)’')

def split_quotes(text):
    units, pos = [], 0
    for m in _QUOTE.finditer(text):
        pre = text[pos:m.start()]
        if pre.strip(" ,;\n\t" + DANDA + DDANDA):
            units.append(("gadya", pre))
        units.append(("padya", m.group(1) if m.group(1) is not None else m.group(2)))
        pos = m.end()
    tail = text[pos:]
    if tail.strip(" ,;\n\t" + DANDA + DDANDA):
        units.append(("gadya", tail))
    return units

# ── R4: hard breaks inside a chunk, beyond the daṇḍas ─────────────────────────
# Each break starts a new render pada, i.e. its own TTS call. The model sees only
# bare text — punctuation is stripped before it — so anything left in one pada is
# phrased as a single breath. Two printed cues therefore have to become breaks:
#   , ;    phrase boundary. Inside a quotation these commonly separate DISTINCT
#          ṛcs/clauses (u08 is RV 7.99.1 + 7.99.2), which the model otherwise
#          re-groups across.
#   _ _ _  lacuna. The edition marks elided text, so the two sides are different
#          citations and must never be run together. (This used to be flattened to
#          a space by clean(), silently welding the halves.)
_BREAK = re.compile(r"[" + DANDA + DDANDA + r",;]|_[\s_]*")

# ── cleaning ──────────────────────────────────────────────────────────────────
def clean(t):
    t = re.sub(r"[०-९]+", "", t)       # strip Devanagari digits
    t = re.sub(r"[/]", "", t)                    # ref slashes
    t = re.sub(r"\s+", " ", t).strip(" ,;-")
    return t

# Boundary kinds. The distinction matters twice over: a HARD boundary (daṇḍa, comma,
# lacuna) is a sentence/clause break that must be HEARD as a pause and must never be
# merged away, while a visarga split is sub-clause — it exists only to put the visarga
# pada-final so the model gives it its learned echo, and it is safe to merge across.
# Conflating them let R7's short-pada merge swallow daṇḍa pauses.
HARD, SOFT = "hard", "soft"


def gadya_segments(t):
    """[(text, boundary_after)] for prose. Hard breaks split first; each resulting
    sentence is then split after every visarga, and only the LAST of those inherits the
    sentence's hard boundary."""
    out, pos, chunks = [], 0, []
    for m in _BREAK.finditer(t):
        chunks.append(t[pos:m.start()]); pos = m.end()
    chunks.append(t[pos:])
    for chunk in chunks:
        vs = [c for c in (clean(x) for x in re.split(r"(?<=" + VISARGA + r")", chunk)) if c]
        for i, c in enumerate(vs):
            out.append((c, HARD if i == len(vs) - 1 else SOFT))
    return out


def padya_segments(t):
    """Verse: every break is a metrical line boundary, so all are HARD."""
    return [(c, HARD) for c in (clean(p) for p in _BREAK.split(t)) if c]


# back-compat: text-only views
def gadya_padas(t):
    return [c for c, _ in gadya_segments(t)]

def padya_padas(t):
    return [c for c, _ in padya_segments(t)]

def depranava(padas):
    """Pull the pranava out of the TTS text and report it for splicing.

    The model CANNOT voice a lone ॐ — it collapses to ~1.2s of mush (heard at the head
    of bsb_1_1_1's maṅgala verse). Each of BSB's 16 pādas opens its bhāṣya with a bare
    ॐ pada, so those must be dropped from the render and replaced at assembly with the
    human-recorded exemplar, exactly as the sutra pranavas already are.

    Returns (padas_without_pranava, opens_pranava)."""
    out, opens = [], False
    for i, p in enumerate(padas):
        s = p.strip()
        if s == OM:
            if not out:
                opens = True          # unit-initial: assembly splices the exemplar
            continue                  # never send a lone ॐ to the model
        if OM in s:                   # inline ॐ: strip it, keep the words
            s = re.sub(r"\s+", " ", s.replace(OM, " ")).strip()
            if not out and p.strip().startswith(OM):
                opens = True
        if s:
            out.append(s)
    return out, opens


def build_units(sutra, bhashya):
    units = []
    # sutra body for TTS = pranavas REMOVED (the ॐ are spliced as the exemplar in
    # assemble.py, not rendered). Brackets/daṇḍas/ॐ all stripped -> just the aphorism.
    s = clean(strip_om_brackets(sutra)).replace(DANDA, "").replace(DDANDA, "").replace(OM, "")
    s = re.sub(r"\s+", " ", s).strip()
    if s:
        units.append({"type": "sutra", "text": s, "padas": [s], "opens_pranava": False})
    for kind, chunk in split_quotes(bhashya):
        segs = gadya_segments(chunk) if kind == "gadya" else padya_segments(chunk)
        pad, opens = depranava([c for c, _ in segs])
        bounds = [b for c, b in segs if c.strip() and c.strip() != OM][:len(pad)]
        while len(bounds) < len(pad):
            bounds.append(HARD)
        if pad:
            # keep the raw chunk: an UNQUOTED verse (the maṅgala śloka opening each
            # pāda's bhāṣya) lands here typed gadya, and gadya splits at visargas —
            # which cuts mid-pāda. segment_bsb re-splits it on daṇḍas once chandas
            # detection confirms it is a complete verse, and needs the daṇḍas for that.
            units.append({"type": kind, "text": " ".join(pad), "padas": pad,
                          "bounds": bounds, "opens_pranava": opens,
                          "raw": clean(chunk)})
    return units


SUTRA = "॥ [ॐ] जन्माद्यस्य यतः [ॐ]॥ १/१/२॥"
BHASHYA = (
"ब्रह्मणो लक्षणमाह- जन्माद्यस्य यतः।\n"
"सृष्टिस्थितिसंहारनियमनज्ञानाज्ञानबन्धमोक्षा यतः।\n"
"“उत्पत्तिस्थितिसंहारा नियतिर्ज्ञानमावृतिः।\n"
"बन्धमोक्षौ च पुरुषाद् यस्मात् स हरिरेकराट्॥”\n"
"इति स्कान्दे।\n"
"“यतो वा इमानि भूतानि जायन्ते।\n"
"येन जातानि जीवन्ति।\n"
"यत् प्रयन्त्यभि संविशन्ति।\n"
"तद् विजिज्ञासस्व।\n"
"तद् ब्रह्मेति”, “य उ त्रिधातु पृथिवीमुत द्यामेको दाधार भुवनानि विश्वा”, "
"“चतुर्भिः साकं नवतिं च नामभिश्चक्रं न वृत्तं व्यतीँरवीविपत्”, "
"“परो मात्रया तन्वा वृधान न ते महित्वमन्वश्नुवन्ति, _ _ _ न ते विष्णो जायमानो न जातो देव महिम्नः परमन्तमाप”, "
"“यो नः पिता जनिता यो विधाता धामानि वेद भुवनानि विश्वा” इत्यादि च॥ २॥"
)

if __name__ == "__main__":
    units = build_units(SUTRA, BHASHYA)
    for i, u in enumerate(units, 1):
        print(f"[{i:02d}] {u['type']:5s} | {len(u['padas'])} pada(s)")
        for p in u["padas"]:
            print(f"        · {p}")
    json.dump(units, open("/Users/prathosh/Sarvamula/audio/units_bsb_1_1_2.json", "w"),
              ensure_ascii=False, indent=2)
    print(f"\n{len(units)} units -> units_bsb_1_1_2.json")
