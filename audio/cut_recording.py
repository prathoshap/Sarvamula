#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cut a hand recitation into the reader's per-entry audio, and bake it.

Input per work: the WAV, the recorder's timestamps, the by_shloka file it was recorded from,
and an onset — the seconds of lead-in before the recorder's own clock starts, so every
timestamp is shifted by it. That offset is the single most important number here: get it
wrong and everything is uniformly late.

The timestamps do NOT partition the timeline. Consecutive blocks usually abut, which makes
it tempting to cut a whole entry as one slice — but a RE-RECORDED block leaves its discarded
take in the WAV, with the kept take starting after it. Dvādaśa Stotra has 36 such gaps
holding 6.7 minutes of rejected takes; cutting entries as single spans played every one of
them. So each block is cut on its own and the pieces are concatenated.

Cut points are the timestamps and nothing else: start_ms + onset, end_ms + onset, per block.
No energy analysis, no silence detection, no adjustment of any kind — the recorder's marks
are the authority.

Karaoke is per BLOCK, not per hemistich: one seg spanning each block, referencing every
display line of that block, so the whole block lights while it sounds. Seg times are taken
from the concatenated file, which drifts from the original timeline by the skipped takes.

Blocks are matched to database entries by text, walking both in order: the sidecar index
records the position of a block but not the entry it came from, and the entry is what the
reader keys audio to.
"""
import argparse, json, os, re, sqlite3, subprocess, sys, unicodedata
import numpy as np, soundfile as sf

DB = "/Users/prathosh/Sarvamula/web/sarvamula.db"
# No fades anywhere. The audio written is the raw cut, sample for sample.
# Silence prepended to every file. Browsers trim an AAC decoder's priming samples by their
# own rules — up to a frame, ~23 ms — and when they trim more than the encoder padded, the
# trim comes out of the first syllable. The file we write is byte-exact (verified against the
# source at 0.0 ms offset), so the loss is entirely decoder-side; a head of real silence
# gives it something harmless to take. Seg times are shifted by the same amount.
HEAD_PAD = 0.080
DEVA = re.compile(r"[अ-ह]")
SV = re.compile(r"[॒॑॓॔᳐-᳿꣠-ꣿ]")


def seek_point(y, sr, t0, floor=0.0, look=0.9, hop=0.01, thr=0.020, minsil=0.060, lead=0.150):
    """Where playback should BEGIN for a block starting at t0 — inside the pause before it.

    Our blocks abut, so seeking to t0 puts a browser's frame-quantised seek inside the first
    syllable. Aim into the preceding pause instead and the attack always survives.

    The pause must be REAL: at least `minsil` of continuous quiet, judged on an envelope
    smoothed by a moving maximum. Scaling the threshold to the window's median instead —
    which is what I did first — makes it rise with the speech around it, so a dip between two
    syllables passes as a pause and the target lands mid-word, which is the bug this replaces.

    Falls back to a fixed lead when no real pause is in reach (recitation straight through).
    This only chooses where to START PLAYING; it never alters a sample of the audio.
    """
    h = int(sr * hop)
    i1 = int(t0 / hop)
    i0 = max(int(floor / hop), i1 - int(look / hop))
    fallback = max(floor, t0 - lead)
    if i1 - i0 < 4:
        return fallback
    e = np.sqrt((y[i0*h:i1*h].reshape(-1, h) ** 2).mean(1) + 1e-12)
    w = 3                                        # ±30 ms moving max: ignore intra-word dips
    sm = np.array([e[max(0, i-w):i+w+1].max() for i in range(len(e))])
    need = max(1, int(minsil / hop))
    j = len(sm) - 1
    while j >= 0:
        while j >= 0 and sm[j] > thr:            # skip back over speech
            j -= 1
        k = j
        while k >= 0 and sm[k] <= thr:           # measure this quiet run
            k -= 1
        if j - k >= need:                        # long enough to be a pause
            end = i0 + j                         # last quiet frame before the speech
            return max(floor, min((end + 1) * hop - 0.020, t0))
        j = k
    return fallback


def envelope(x, sr, hop=0.010, smooth=6):
    """Frame energy, smoothed by a moving MAX (±60 ms) so a dip inside a word — or between two
    syllables of one — is not read as a pause. ±30 ms proved too narrow: three starts stopped
    350-680 ms short of where the utterance actually began."""
    h = int(sr * hop); n = len(x) // h
    e = np.sqrt((x[:n*h].reshape(n, h) ** 2).mean(1) + 1e-12)
    if smooth:
        e = np.array([e[max(0, i-smooth):i+smooth+1].max() for i in range(len(e))])
    return e, hop


def snap_edge(e, hop, t, kind, lo, hi, thr=0.020):
    """Move a mark to the pause that bounds its utterance, searching BOTH ways.

    The recorder marks the TAP, not the voice: on a retake the reciter resumes ~1 s before the
    mark registers, so the block opens mid-word. Anchored at the mark, this walks to the pause
    that actually delimits the speech — left when the mark sits inside an utterance, right when
    it sits in silence — and is bounded by [lo, hi] so it can never reach a neighbour.

    Fixes late starts. Does NOT remove a trailing burp: a throat-clear is bounded by pauses
    exactly as speech is, so nothing here can tell them apart. That needs the text.
    """
    i = int(round(t / hop))
    a, b = int(np.ceil(lo / hop)), int(hi / hop)
    if not (0 <= a < b < len(e)):
        return t
    i = min(max(i, a), b)
    if e[i] > thr:                                   # inside speech: find its edge
        j = i
        if kind == "start":
            while j > a and e[j-1] > thr: j -= 1      # back to where this utterance began
        else:
            while j < b and e[j+1] > thr: j += 1      # forward to where it ends
    else:                                            # in silence: move to the speech
        j = i
        if kind == "start":
            while j < b and e[j] <= thr: j += 1       # forward to the onset
        else:
            while j > a and e[j] <= thr: j -= 1       # back to the last speech
    t2 = j * hop
    return float(min(max(t2, lo), hi))



def carry(e, hop, t, kind, limit, bound, floor=0.100, margin=0.100, thr=0.020):
    """Carry an aligned edge outward to where the voice actually stops, then a little further.

    Forced alignment puts a boundary frame on the final token's NUCLEUS, and in Vedic chant
    the last syllable is HELD well past it — measured over 491 mantras, the voice runs a
    median 810 ms beyond the aligned end, p90 1.11 s. Cutting at the alignment therefore
    truncates the sustain, taking the closing visarga or anusvāra with it. The same happens at
    the front, on a smaller scale, to the opening attack.

    Verified as the mantra's own tail and not the next one's head: block #4 of RV_26 sustains
    680 ms past its aligned end while the following mantra is nineteen seconds away.

    So walk outward while the voice is still above the speech threshold, add `margin` so the
    cut lands inside the silence rather than on the last breath, and stop at `limit`. `bound`
    is the neighbouring edge and can never be crossed; `floor` is the least an edge moves, for
    the case where the walk meets silence at once.
    """
    i = min(max(int(round(t / hop)), 0), len(e) - 1)   # a mark can outrun the file
    if kind == "end":
        cap = min(len(e) - 1, i + int(limit / hop))
        j = i
        while j < cap and e[j] > thr:
            j += 1
        return min(max(j * hop + margin, t + floor), t + limit, bound)
    cap = max(0, i - int(limit / hop))
    j = i
    while j > cap and e[j] > thr:
        j -= 1
    return max(min(j * hop - margin, t - floor), t - limit, bound)


def key(s):
    return re.sub(r"[^अ-ह]", "", SV.sub("", unicodedata.normalize("NFC", s or "")))


def map_blocks(order, src, rows):
    """Walk blocks and entries together; assign each block to the entry holding its text."""
    ent = [(seq, key(t)) for seq, t in rows]
    out, ei, cursor = [], 0, 0
    for bid in order:
        txt = key(" ".join(src[bid][0]["text"]))
        probe = txt[:22] or txt
        placed = None
        for j in range(ei, min(ei + 3, len(ent))):        # never search backwards
            at = ent[j][1].find(probe, cursor if j == ei else 0)
            if at >= 0:
                placed, ei = ent[j][0], j
                cursor = at + max(1, len(txt))
                if j != ei:
                    cursor = at + max(1, len(txt))
                break
        if placed is None:
            # From ei+1, NOT ei. Searching ei again drops the cursor, so a passage that occurs
            # twice in a work re-matches its FIRST occurrence and the second is never reached:
            # Ṣaṭpraśna, Māṇḍūkya and Muṇḍaka each open and close with the same śānti mantra,
            # recited twice, and all six takes were landing on the opening entry. The loop above
            # already covers "still inside ei" — it searches ei from the cursor.
            for j in range(ei + 1, len(ent)):
                at = ent[j][1].find(probe)
                if at >= 0:
                    placed, ei, cursor = ent[j][0], j, at + max(1, len(txt))
                    break
        out.append((bid, placed))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--wav", required=True)
    ap.add_argument("--ts", required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--onset", type=float, required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--prefix", required=True, help="file/block id stem, e.g. dvs")
    ap.add_argument("--db", default=DB)
    ap.add_argument("--kind", default="recited")
    ap.add_argument("--snap", type=float, default=0.0,
                    help="seconds either side of a mark to search for the pause bounding it")
    ap.add_argument("--startsil", type=float, default=0.0,
                    help="carry each start back this far at most, so the opening attack is kept")
    ap.add_argument("--endsil", type=float, default=0.0,
                    help="carry each end forward this far at most, so the HELD final syllable "
                         "and its closing visarga or anusvāra are kept (they run a median "
                         "810 ms past where forced alignment puts the last token)")
    ap.add_argument("--joingap", type=float, default=0.0,
                    help="silence inserted BETWEEN two blocks of one entry. Needed once the "
                         "marks are aligned: a mark-cut slice carried ~3s of trailing pause, so "
                         "the gap between two mantras came for free, but an aligned slice ends "
                         "at the voice and the next would start on top of it.")
    ap.add_argument("--tailgap", type=float, default=0.0,
                    help="silence appended after the last block, so playback does not stop dead "
                         "on the final syllable")
    ap.add_argument("--append", action="store_true",
                    help="keep the work's other audio (e.g. its rendered bhāṣya) and replace "
                         "only the entries this recording covers")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    blocks = json.load(open(a.ts, encoding="utf-8"))["blocks"]
    src = json.load(open(a.src, encoding="utf-8"))["content"]
    con = sqlite3.connect(a.db); con.row_factory = sqlite3.Row
    rows = [(r["seq"], r["text_dev"]) for r in con.execute(
        "select seq, content_type, text_dev from entries where work=? "
        "and content_type not like 'Heading%' order by seq", (a.work,))]

    x, sr = sf.read(a.wav, dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    dur = len(x) / sr
    env, hop = (envelope(x, sr) if (a.snap or a.startsil or a.endsil) else (None, 0.01))
    order = [b["id"] for b in blocks]
    ts = {b["id"]: b for b in blocks}
    placed = map_blocks(order, src, rows)
    unplaced = [b for b, e in placed if e is None]
    print(f"{a.work}: {len(blocks)} blocks -> {len({e for _, e in placed if e is not None})} entries"
          f" | unplaced {len(unplaced)}")
    if unplaced:
        for b in unplaced[:5]:
            print("   UNPLACED:", " / ".join(src[b][0]["text"])[:70])

    # group consecutive blocks by entry, preserving recording order
    groups, cur = [], None
    for bid, seq in placed:
        if seq is None:
            continue
        if cur and cur[0] == seq:
            cur[1].append(bid)
        else:
            cur = (seq, [bid]); groups.append(cur)

    # ── snap every mark to the pause that bounds its recitation ──────────────────────────
    # Done over the WHOLE recording before any cutting, because an end can only be judged
    # against the next block's start — and the next block often belongs to another entry.
    #
    # Both edges drift the same way: the recorder marks the tap, and the tap is late. A start
    # lands after the reciter has resumed, so the opening word is lost; an end lands after the
    # NEXT mantra has begun, so its opening rides along at the tail. Snapping the start alone
    # fixed the first and worsened the second — walking an end forward to the end of the speech
    # it sat in swallowed the next mantra's phrase whole.
    #
    # So: snap each start back to its own onset, then clamp every end to the following start.
    # A block can never contain audio that belongs to the block after it.
    snapped_at, snapped = {}, []
    if a.snap:
        order = [b["id"] for b in blocks]
        raw = {b["id"]: (b["start_ms"]/1000.0 + a.onset, b["end_ms"]/1000.0 + a.onset) for b in blocks}
        starts = {}
        for i, bid in enumerate(order):
            bs, be = raw[bid]
            floor = raw[order[i-1]][0] if i else 0.0
            starts[bid] = snap_edge(env, hop, bs, "start", max(floor, bs - a.snap), bs + a.snap)
        for i, bid in enumerate(order):
            bs, be = raw[bid]
            ns = starts[bid]
            nxt = starts[order[i+1]] if i + 1 < len(order) else min(dur, be + a.snap)
            ne = snap_edge(env, hop, be, "end", be - a.snap, min(dur, be + a.snap))
            ne = min(ne, nxt)                      # never run into the next recitation
            if ne <= ns:
                ns, ne = bs, be
            snapped_at[bid] = (ns, ne)
            if abs(ns - bs) > 0.02:
                snapped.append(bs - ns)
        trimmed = sum(1 for b in blocks
                      if snapped_at[b["id"]][1] < b["end_ms"]/1000.0 + a.onset - 0.02)
        print(f"  snapped: {len(snapped)} starts moved back, {trimmed} ends pulled in")

    # ── carry aligned edges out into the silence beside them ────────────────────────────────
    # Also a whole-recording pass: an edge is bounded by its neighbour, and the neighbour is
    # often in a different entry. Applied after --snap so the two compose if ever used together.
    carried = {}
    if a.startsil or a.endsil:
        base = {b["id"]: (snapped_at.get(b["id"]) or
                          (b["start_ms"]/1000.0 + a.onset, b["end_ms"]/1000.0 + a.onset))
                for b in blocks}
        # Starts first, then ends bounded by the NEXT CARRIED START — not the next aligned
        # start. Bounding each edge against its aligned neighbour lets both reach into the same
        # gap, and the overlap is emitted in BOTH clips: a held syllable heard twice, once at
        # the end of one and again at the head of the next.
        ds, de, starts = [], [], {}
        for i, bid in enumerate(order):
            bs = base[bid][0]
            lo = base[order[i-1]][1] if i else 0.0
            starts[bid] = carry(env, hop, bs, "start", a.startsil, max(lo, 0.0)) if a.startsil else bs
        for i, bid in enumerate(order):
            bs, be = base[bid]
            hi = starts[order[i+1]] if i + 1 < len(order) else dur
            ns = starts[bid]
            ne = carry(env, hop, be, "end", a.endsil, min(hi, dur)) if a.endsil else be
            if ne <= ns:
                ns, ne = bs, be
            carried[bid] = (ns, ne)
            ds.append(bs - ns); de.append(ne - be)
        print(f"  carried edges: start out by {1000*min(ds):.0f}-{1000*max(ds):.0f} ms "
              f"(median {1000*sorted(ds)[len(ds)//2]:.0f}), "
              f"end out by {1000*min(de):.0f}-{1000*max(de):.0f} ms "
              f"(median {1000*sorted(de)[len(de)//2]:.0f})")

    os.makedirs(a.outdir, exist_ok=True)
    arows, trows, clipped = [], [], 0
    for n, (seq, bids) in enumerate(groups, 1):
        # ONE SLICE PER BLOCK, never one slice across the whole entry. The timestamps do NOT
        # partition the timeline: when a block is re-recorded the discarded take stays in the
        # WAV and the kept take begins after it, leaving a gap between one block's end and the
        # next block's start — 36 such gaps, 6.7 minutes, in Dvādaśa Stotra alone. Cutting an
        # entry as a single span swallows them and plays every rejected take.
        pieces, spans, pos, prev_end = [], [], 0, None
        for bid in bids:
            bs = ts[bid]["start_ms"] / 1000.0 + a.onset
            be = ts[bid]["end_ms"] / 1000.0 + a.onset
            if a.snap and bid in snapped_at:
                bs, be = snapped_at[bid]
            if bid in carried:
                bs, be = carried[bid]
            if be > dur:                  # recorder's clock outran the file
                clipped += 1; be = dur
            if be <= bs:
                continue
            p = x[int(bs * sr):int(be * sr)].copy()
            if pieces and a.joingap:
                g = np.zeros(int(a.joingap * sr), dtype=p.dtype)
                pieces.append(g); pos += len(g)
            spans.append((bid, pos / sr, (pos + len(p)) / sr))
            pieces.append(p); pos += len(p); prev_end = be
        if not pieces:
            continue
        head = np.zeros(int(HEAD_PAD * sr), dtype=pieces[0].dtype)
        tail = [np.zeros(int(a.tailgap * sr), dtype=pieces[0].dtype)] if a.tailgap else []
        seg = np.concatenate([head] + pieces + tail)
        spans = [(bid, t0 + HEAD_PAD, t1 + HEAD_PAD) for bid, t0, t1 in spans]
        stem = f"{a.prefix}_{seq:04d}"
        wav = os.path.join(a.outdir, stem + ".wav")
        sf.write(wav, seg, sr, subtype="PCM_16")
        m4a = os.path.join(a.outdir, stem + ".m4a")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-c:a", "aac", "-b:a", "128k",
                        "-movflags", "+faststart", m4a], check=True)
        os.unlink(wav)

        # display lines and one seg per block: the whole block lights while it sounds.
        # Seg times come from the CONCATENATED file, not the original timeline — the two
        # diverge by however much discarded-take audio was skipped.
        lines, segs, k = [], [], 0
        # The pause before a verse lies inside the PREVIOUS block's tail — our blocks abut,
        # so bounding the search at the previous block's end leaves nowhere to look. Bound it
        # at the previous block's START instead: playback may begin in the previous verse's
        # trailing silence, which is exactly what is wanted, and can never run back past it.
        prev_t0 = 0.0
        for bid, t0, t1 in spans:
            idx = []
            for ln in src[bid][0]["text"]:
                lines.append({"t": ln, "k": "padya"}); idx.append(k); k += 1
            qq = seek_point(seg, sr, t0, floor=prev_t0)
            segs.append({"s": round(t0, 3), "e": round(t1, 3), "ln": idx,
                         "q": round(qq, 3)})      # where a click should start playback
            prev_t0 = t0
        arows.append((a.work, stem, 0, f"{a.work}/{stem}.m4a", round(len(seg) / sr, 3),
                      a.kind, None, seq, json.dumps(lines, ensure_ascii=False),
                      json.dumps([seq]), None))
        trows.append((a.work, stem, 0, json.dumps(segs, ensure_ascii=False)))

    total = sum(r[4] for r in arows)
    print(f"  cut {len(arows)} files, {total/60:.1f} min"
          + (f" | {clipped} clamped to end-of-file" if clipped else ""))
    if not a.write:
        print("  [dry run — pass --write to bake]"); return
    if a.append:
        # Ṛg Bhāṣya holds its rendered bhāṣya alongside this recitation; only the blocks this
        # pass produces may be replaced, never the whole work.
        for r in arows:
            con.execute("DELETE FROM audio WHERE work=? AND block=?", (a.work, r[1]))
            con.execute("DELETE FROM audio_timings WHERE work=? AND block=?", (a.work, r[1]))
    else:
        con.execute("DELETE FROM audio WHERE work=?", (a.work,))
        con.execute("DELETE FROM audio_timings WHERE work=?", (a.work,))
    con.executemany("INSERT INTO audio (work,block,part,path,dur,kind,ref,seq,lines,covers,base) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)", arows)
    con.executemany("INSERT INTO audio_timings (work,block,part,segs) VALUES (?,?,?,?)", trows)
    con.commit()
    print(f"  baked {len(arows)} audio rows for {a.work}")


if __name__ == "__main__":
    main()
