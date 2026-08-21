#!/usr/bin/env python3
"""
Sarvamūla reader — DB builder.  RECOVERED 2026-07-21 by reverse-engineering the
existing web/sarvamula.db against the 38 source *.json files (the original builder
lived only in a scratchpad and was lost).  Reproduces the DB byte-for-content.

Source: 38 JSON files at repo root, one per work.  Each file:
    { "title": <code>, "content": { <uuid>: [ <block> ], ... } }   # content is an
ORDERED dict, uuid -> single-element list of a block dict.  Block fields seen:
    content_type, text[list of lines], is_padya, heading_level, pramana,
    skandha, adhyaya, verse, verse_end(dropped), needs_qc(dropped),
    kutra[list], variants[list], footnote[list]

Output: web/sarvamula.db  (tables: works, entries) — schema/values verified to
match the shipped DB exactly (see build_db.verify or `python3 build_db.py --check`).

Run:  cd /Users/prathosh/Sarvamula && python3 build_db.py
"""
import json, glob, os, re, sqlite3, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(ROOT, 'web', 'sarvamula.db')

# Display titles are NOT in the JSON (its "title" is a short code) — they were a
# hand-curated map in the original builder; recovered here from the shipped DB.
TITLES = {
    'aitareya_bhashya': 'Aitareya Bhashya',
    'anu_vyakhyana': 'Anuvyākhyāna',
    'atharvana_bhashya': 'Atharvana Bhashya',
    'bhagavata_tatparya': 'Bhāgavata Tātparya Nirṇaya',
    'chandogya_bhashya': 'Chandogya Bhashya',
    'dvadasha_stotra': 'Dvādaśa Stotra',
    'gita_bhashya': 'Gītā Bhāṣya',
    'gita_tatparya': 'Gītā Tātparya',
    'ishavasya_bhashya': 'Ishavasya Bhashya',
    'jayanti_kalpa': 'Jayanti Kalpa',
    'kanva_bhashya': 'Kanva Bhashya',
    'karma_nirnaya': 'Karma Nirnaya',
    'katha_lakshana': 'Katha Lakshana',
    'kathaka_bhashya': 'Kathaka Bhashya',
    'krshna_amrta_maharnava': 'Kṛṣṇāmṛtamahārṇava',
    'manduka_bhashya': 'Manduka Bhashya',
    'mayavada_khandana': 'Māyāvādakhaṇḍana',
    'mbtn': 'Mahābhārata Tātparya Nirṇaya',
    'nyasa_paddhati': 'Nyasa Paddhati',
    'nyaya_vivarana': 'Nyāyavivaraṇa',
    'parishishta': 'Parishishta',
    'pramana_lakshana': 'Pramana Lakshana',
    'prapancha_mithyatva_khandana': 'Prapancha Mithyatva Khandana',
    'rg_bhashya': 'Ṛg Bhāṣya',
    'sadachara_smriti': 'Sadachara Smriti',
    'sangraha_bhashya': 'Sangraha Bhashya',
    'shatprashna_bhashya': 'Shatprashna Bhashya',
    'sutra_bhashya': 'Brahmasūtra Bhāṣya',
    'taittiriya_bhashya': 'Taittiriya Bhashya',
    'talavakara_bhashya': 'Talavakara Bhashya',
    'tantrasara_sangraha': 'Tantrasārasaṅgraha',
    'tatva_sankhyana': 'Tatva Sankhyana',
    'tatva_viveka': 'Tatva Viveka',
    'tatvodyota': 'Tatvodyota',
    'upadhi_khandana': 'Upādhikhaṇḍana',
    'vishnu_tatva_nirnaya': 'Viṣṇutattvanirṇaya',
    'yamaka_bharata': 'Yamaka Bharata',
    'yati_pranava_kalpa': 'Yati Pranava Kalpa',
}

# ---------------------------------------------------------------------------
# content_type cleanup (2026-07-22).  The source JSONs carry a handful of junk
# content_type values (typos + a leaked pramāṇa flag + corruption).  Fixes are
# keyed on (work, seq) with the expected bad value asserted, so a data shift
# fails loudly instead of silently mis-tagging.  Disable with build(cleanup=False)
# / `--raw` to reproduce the ORIGINAL (pre-cleanup) DB byte-for-content.
#   (work, seq): (expected_bad, corrected)
CT_FIXES = {
    ('kanva_bhashya',  61): ('Colopon_Mula', 'Colophon_Mula'),      # typo
    ('kanva_bhashya',  99): ('Colohon_Mula', 'Colophon_Mula'),      # typo
    ('kanva_bhashya',  79): ('श',            'Sarvamula'),          # corrupt → prose gloss in the Sarvamūla stream
    ('mbtn',         1042): ('',             'Colophon_Sarvamula'), # stray "॥" closing the split colophon at seq 1041
    ('sutra_bhashya',1114): ('Yes',          'Sarvamula'),          # pramāṇa "Yes" flag leaked into content_type
    ('sutra_bhashya',1117): ('Yes',          'Sarvamula'),          #   "  (all four are pramana+padya quote verses)
    ('sutra_bhashya',1194): ('Yes',          'Sarvamula'),          #   "
    ('sutra_bhashya',1289): ('Yes',          'Sarvamula'),          #   "
}

# -------- block reordering (2026-08-08) --------------------------------------
# Skandha 10 of bhagavata_tatparya ships BOTH half-skandha headings and BOTH closing
# colophons bunched together BEFORE any content:
#     10678 Mangala | 10679 Skandha_Heading दशमस्कन्धः
#     10680 Colophon_Skandha इति दशमस्कन्धपूर्वार्धः समाप्तः
#     10681 Mangala | 10682 Skandha_Heading दशमस्कन्ध उत्तरार्धः
#     10683 Colophon_Skandha समाप्तश्च दशमस्कन्धः
# The reader chapters on Skandha_Heading, so the pūrvārdha chapter got 3 rows and the
# uttarārdha chapter swallowed all 5261 — i.e. the pūrvārdha looked EMPTY on the site
# even though its text (adhyāyas 1-49, 245,583 chars) was fully ingested and matches
# the source IDML. The content was never missing; only these four markers were.
#
# Each move asserts the block's content_type AND a text prefix, so a data shift fails
# loudly rather than silently relocating the wrong block.
#   (work, seq): (expected_ct, expected_text_prefix, move_to_just_after_seq)
BLOCK_MOVES = {
    ('bhagavata_tatparya', 10680): ('Colophon_Skandha', 'इति दशमस्कन्धपूर्वार्धः', 13064),
    ('bhagavata_tatparya', 10681): ('Mangala',          'भगवद्बादरायण',            13064),
    ('bhagavata_tatparya', 10682): ('Skandha_Heading',  'दशमस्कन्ध उत्तरार्धः',    13064),
    ('bhagavata_tatparya', 10683): ('Colophon_Skandha', 'समाप्तश्च दशमस्कन्धः',    15941),
}


def _apply_moves(slug, blocks, cleanup=True):
    """Reorder blocks per BLOCK_MOVES. `blocks` is the work's flat list in source order;
    seq is the index within it. Returns the reordered list (seq is re-derived after)."""
    moves = {s: v for (w, s), v in BLOCK_MOVES.items() if w == slug}
    if not cleanup or not moves:
        return blocks
    for s, (ct, pref, _) in moves.items():
        b = blocks[s]
        got_ct, got_tx = b.get('content_type', ''), ' '.join(b.get('text') or [])
        assert got_ct == ct and pref.lstrip('॥ ') in got_tx.replace('॥', '').strip(), (
            f"BLOCK_MOVES stale at {slug}:{s}: expected {ct!r}/{pref!r}, "
            f"got {got_ct!r}/{got_tx[:40]!r}")
    out = [b for i, b in enumerate(blocks) if i not in moves]
    # insert after the target, walking from the end so earlier inserts do not shift later
    for s in sorted(moves, reverse=True):
        tgt = moves[s][2]
        pos = out.index(blocks[tgt]) + 1
        out.insert(pos, blocks[s])
    return out

# -------- search normalization (norm) — VOWEL-PRESERVING (2026-07-22) --------
# Replaces the old consonant-skeleton fold. Keeps vowels (long→short), merges the
# spelling-tolerance classes: aspirates (kh=k), retroflex/dental (ṭ=t, ḍ=d),
# sibilants (ś=ṣ=s); drops anusvāra/visarga/avagraha; vocalic-ṛ → "ri" (so
# कृष्ण / kṛṣṇa / krishna all unify). Devanāgarī is handled syllable-aware with
# implicit-a. **norm() in web/app.js MUST stay byte-identical to this.**
_CONS = {  # base consonant (aspirate + retroflex/dental + sibilant folded)
    'क':'k','ख':'k','ग':'g','घ':'g','ङ':'n','च':'c','छ':'c','ज':'j','झ':'j','ञ':'n',
    'ट':'t','ठ':'t','ड':'d','ढ':'d','ण':'n','त':'t','थ':'t','द':'d','ध':'d','न':'n',
    'प':'p','फ':'p','ब':'b','भ':'b','म':'m','य':'y','र':'r','ल':'l','व':'v',
    'श':'s','ष':'s','स':'s','ह':'h','ळ':'l',
}
_MATRA = {'ा':'a','ि':'i','ी':'i','ु':'u','ू':'u','ृ':'ri','ॄ':'ri','ॢ':'li','ॣ':'li',
          'े':'e','ै':'e','ो':'o','ौ':'o'}          # anusvāra/visarga NOT here (see below)
_IND = {'अ':'a','आ':'a','इ':'i','ई':'i','उ':'u','ऊ':'u','ऋ':'ri','ॠ':'ri',
        'ऌ':'li','ॡ':'li','ए':'e','ऐ':'e','ओ':'o','औ':'o'}
_VIRAMA = '्'
_DEVA = re.compile('[ऀ-ॿ]')
_INDIC = re.compile('[ऀ-ൿ]')  # Devanāgarī + all Indic scripts (Bengali, Gujarati, Kannada, Malayalam, Oriya, Punjabi, Tamil, Telugu)
_OFFSETS = [  # Unicode offsets to convert Indic scripts to Devanāgarī
    (0x0B80, 0x0BFF, 0x0280),  # Tamil: 0x0280
    (0x0B00, 0x0B7F, 0x0200),  # Oriya: 0x0200
    (0x0A80, 0x0AFF, 0x0180),  # Gujarati: 0x0180
    (0x0A00, 0x0A7F, 0x0100),  # Punjabi: 0x0100
    (0x0C00, 0x0C7F, 0x0300),  # Telugu: 0x0300
    (0x0C80, 0x0CFF, 0x0380),  # Kannada: 0x0380
    (0x0D00, 0x0D7F, 0x0400),  # Malayalam: 0x0400
    (0x0980, 0x09FF, 0x0080),  # Bengali: 0x0080
]
_WS   = re.compile(r'\s+')

def script_to_dev(s):
    """Convert any Indic script (Kannada, Telugu, etc.) to Devanāgarī using Unicode offsets."""
    out = []
    for ch in s:
        o = ord(ch)
        # Check if char is already Devanāgarī
        if 0x0900 <= o <= 0x097F:
            out.append(ch)
            continue
        # Try to convert from other Indic script
        found = False
        for lo, hi, offset in _OFFSETS:
            if lo <= o <= hi:
                out.append(chr(o - offset))
                found = True
                break
        if not found:
            out.append(ch)
    return ''.join(out)

def norm(s):
    """Search key. Vowel-preserving, multi-script normalization. Handles all Indic scripts
    (Kannada, Telugu, Malayalam, etc.) by converting to Devanāgarī first via script_to_dev().
    MUST stay byte-identical to norm() in web/app.js (which normalizes search queries).
    Built text_skel values are Devanāgarī; queries are converted to match."""
    s = s or ''
    # Convert any Indic script to Devanāgarī first (Kannada, Telugu, Malayalam, etc.)
    if _INDIC.search(s):
        s = script_to_dev(s)
    if _DEVA.search(s):
        out = []; i = 0; n = len(s)
        while i < n:
            ch = s[i]
            if ch in _CONS:
                out.append(_CONS[ch])
                nx = s[i+1] if i+1 < n else ''
                if nx == _VIRAMA: i += 2; continue          # halant → bare consonant
                if nx in _MATRA: out.append(_MATRA[nx]); i += 2; continue
                out.append('a'); i += 1; continue           # inherent 'a'
            if ch in _IND:   out.append(_IND[ch]);   i += 1; continue
            if ch in _MATRA: out.append(_MATRA[ch]); i += 1; continue
            if ch == 'ॐ':    out.append('om');       i += 1; continue
            if ch.isspace() or ch in '।॥': out.append(' '); i += 1; continue
            i += 1                                          # drop anusvāra/visarga/avagraha/digits/ZWJ
        return _WS.sub(' ', ''.join(out)).strip()
    # latin / IAST query branch (order matters)
    s = s.lower()
    s = re.sub(r'[ṃṁḥ]', '', s)
    s = s.replace('ṭ', 't').replace('ḍ', 'd')
    s = re.sub(r'[ṇṅñ]', 'n', s)
    s = re.sub(r'[ḷḻ]', 'l', s)
    s = re.sub(r'ś|ṣ|sh', 's', s)
    s = s.replace('ch', 'c')
    s = re.sub(r'([kgtdpbjc])h', r'\1', s)
    s = re.sub(r'[āâ]', 'a', s); s = re.sub(r'[īî]', 'i', s); s = re.sub(r'[ūû]', 'u', s)
    s = re.sub(r'[ēê]', 'e', s); s = re.sub(r'[ōô]', 'o', s)
    s = re.sub(r'[ṛṝ]', 'ri', s)
    # Vocalic r: smrutha → smrita (matches Devanagari ṛ normalization)
    s = s.replace('mru', 'mri')
    # Diphthongs must fold as the Devanāgarī branch folds them: _MATRA/_IND collapse ै and ौ to
    # 'e' and 'o', so द्वैत keys as "dveta" — a typed "dvaita" stayed "dvaita" and matched
    # nothing in any of the 37 works, while the Devanāgarī spelling found it. Kept identical to
    # norm() in web/app.js, which is the invariant this key depends on.
    s = re.sub(r'ai', 'e', s)
    s = re.sub(r'au', 'o', s)
    s = re.sub(r'[^a-z ]', '', s)
    return _WS.sub(' ', s).strip()

fold = norm   # legacy alias (older call sites / notes)

TOPIC = lambda ct: ct.startswith('Heading') or ct in ('Subject', 'Title')

def jdump(v):
    return json.dumps(v, ensure_ascii=False) if v is not None else None

def load_rows(cleanup=True):
    """Return (entries, works) in the deterministic order the DB was built.
    cleanup=True applies CT_FIXES; cleanup=False reproduces the original DB."""
    slugs = sorted(os.path.splitext(os.path.basename(f))[0]
                   for f in glob.glob(os.path.join(ROOT, '*.json')))
    entries, works = [], []
    applied = 0
    for ordi, slug in enumerate(slugs):
        with open(os.path.join(ROOT, slug + '.json'), encoding='utf-8') as fh:
            content = json.load(fh)['content']
        seq = 0
        n_blocks = n_padya = n_topics = 0
        # flatten first so BLOCK_MOVES can address blocks by their source-order seq
        flat = [b for blocks in content.values() for b in blocks]
        ct_by_src = {id(b): i for i, b in enumerate(flat)}   # source seq, for CT_FIXES
        flat = _apply_moves(slug, flat, cleanup)
        for b in flat:
            if True:
                src_seq = ct_by_src[id(b)]
                ct = b.get('content_type', '')
                # CT_FIXES is keyed on SOURCE seq, which moves do not change
                if cleanup and (slug, src_seq) in CT_FIXES:
                    bad, good = CT_FIXES[(slug, src_seq)]
                    assert ct == bad, (
                        f"CT_FIXES stale at {slug}:{src_seq}: expected {bad!r}, got {ct!r}")
                    ct = good
                    applied += 1
                text_dev = ' '.join(b.get('text') or [])
                is_padya = int(bool(b.get('is_padya', False)))
                pramana  = int(bool(b.get('pramana', False)))
                entries.append((
                    slug, seq, ct, b.get('heading_level'), is_padya, pramana,
                    b.get('skandha'), b.get('adhyaya'), b.get('verse'),
                    text_dev, fold(text_dev),
                    jdump(b.get('kutra')), jdump(b.get('variants')),
                    jdump(b.get('footnote')),
                ))
                seq += 1
                n_blocks += 1
                n_padya  += is_padya
                n_topics += 1 if TOPIC(ct) else 0
        works.append((slug, TITLES.get(slug, slug), ordi, n_blocks, n_padya, n_topics))
    if cleanup and applied:
        print(f"cleanup: applied {applied}/{len(CT_FIXES)} content_type fixes")
    return entries, works

def build(out=OUT, cleanup=True):
    entries, works = load_rows(cleanup=cleanup)
    if os.path.exists(out):
        os.remove(out)
    db = sqlite3.connect(out)
    db.executescript("""
        CREATE TABLE works(slug TEXT PRIMARY KEY, title TEXT, ord INT,
            n_blocks INT, n_padya INT, n_topics INT);
        CREATE TABLE entries(id INTEGER PRIMARY KEY, work TEXT, seq INT,
            content_type TEXT, heading_level INT, is_padya INT, pramana INT,
            skandha INT, adhyaya INT, verse INT, text_dev TEXT, text_skel TEXT,
            kutra TEXT, variants TEXT, footnote TEXT);
    """)
    db.executemany("INSERT INTO works VALUES(?,?,?,?,?,?)", works)
    db.executemany(
        """INSERT INTO entries
           (work,seq,content_type,heading_level,is_padya,pramana,
            skandha,adhyaya,verse,text_dev,text_skel,kutra,variants,footnote)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", entries)
    db.commit()
    db.close()
    print(f"built {out}: {len(works)} works, {len(entries)} entries")

_COLS_E = ("work,seq,content_type,heading_level,is_padya,pramana,skandha,"
           "adhyaya,verse,text_dev,text_skel,kutra,variants,footnote")

def _diff_dbs(ref, new, label=""):
    """Print + return the row/works diffs between two DBs. Returns diff row-list."""
    a, b = sqlite3.connect(ref), sqlite3.connect(new)
    ra = a.execute(f"SELECT {_COLS_E} FROM entries ORDER BY work,seq").fetchall()
    rb = b.execute(f"SELECT {_COLS_E} FROM entries ORDER BY work,seq").fetchall()
    wa = a.execute("SELECT slug,title,ord,n_blocks,n_padya,n_topics FROM works ORDER BY slug").fetchall()
    wb = b.execute("SELECT slug,title,ord,n_blocks,n_padya,n_topics FROM works ORDER BY slug").fetchall()
    a.close(); b.close()
    cols = _COLS_E.split(',')
    rowdiffs = []
    if len(ra) != len(rb):
        print(f"ENTRY COUNT differs: ref={len(ra)} new={len(rb)}")
    for x, y in zip(ra, rb):
        if x != y:
            changed = [(cols[ci], x[ci], y[ci]) for ci in range(len(cols)) if x[ci] != y[ci]]
            rowdiffs.append((x[0], x[1], changed))
            print(f"  {x[0]}:{x[1]}  " +
                  "  ".join(f"[{c}] {o!r} → {n!r}" for c, o, n in changed))
    if wa != wb:
        print("WORKS differ:")
        for x, y in zip(wa, wb):
            if x != y: print(f"  ref={x}\n  new={y}")
    return rowdiffs, (wa != wb)

def check(ref=OUT, cleanup=True):
    """Build (cleanup default) to a temp DB and diff every row/aggregate vs `ref`."""
    tmp = ref + '.check'
    build(tmp, cleanup=cleanup)
    rowdiffs, wdiff = _diff_dbs(ref, tmp)
    os.remove(tmp)
    ok = not rowdiffs and not wdiff
    print("✅ EXACT MATCH — builder reproduces the shipped DB" if ok
          else f"❌ {len(rowdiffs)} differing rows")
    return ok

def diff_cleanup():
    """Prove the cleanup touches ONLY the intended rows: build raw vs clean and
    show the delta (expected == CT_FIXES, content_type-only)."""
    raw, clean = OUT + '.raw', OUT + '.clean'
    build(raw, cleanup=False)
    build(clean, cleanup=True)
    print(f"--- cleanup delta (raw → clean), expect {len(CT_FIXES)} content_type-only rows ---")
    rowdiffs, wdiff = _diff_dbs(raw, clean)
    os.remove(raw); os.remove(clean)
    only_ct = all(len(ch) == 1 and ch[0][0] == 'content_type' for _, _, ch in rowdiffs)
    ok = (len(rowdiffs) == len(CT_FIXES)) and only_ct and not wdiff
    print(f"✅ cleanup affects exactly {len(rowdiffs)} rows, content_type only, aggregates unchanged"
          if ok else "❌ unexpected cleanup delta (see above)")
    return ok

if __name__ == '__main__':
    if '--check' in sys.argv:            # regression: clean build == shipped DB
        sys.exit(0 if check() else 1)
    if '--diff-cleanup' in sys.argv:     # audit: show the raw→clean delta
        sys.exit(0 if diff_cleanup() else 1)
    build(cleanup='--raw' not in sys.argv)  # default build applies cleanup; --raw = original
