#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sarvamula audio assembly — SUTRA rules (hardcoded, approved 2026-07-31).

Two model facts we design around (Vagdhenu / IndicF5):
  * the model CANNOT voice a lone pranava ( ॐ collapses to ~silence), and
  * the model EATS the first syllable of any render.
Both are solved by one move: prepend a SACRIFICIAL ॐ to the TTS body (it absorbs
the first-syllable clip so the real first word survives), and splice a human-recorded
exemplar ॐ (assets/pranava_exemplar.wav, the author's own voice — matches the model).

SUTRA assembly patterns  (EX = exemplar ॐ, ~0.56s ; GAP = 0.25s ; TIGHT = 0.08s):
  general sutra :  EX  +GAP+  body  +GAP+  EX
  FIRST sutra   :  EX  +GAP+  EX  +TIGHT+  body  +GAP+  EX      # BSB 1.1.1 only
     - two leading pranavas: maṅgala ॐ  +  the sutra's own INTEGRAL ॐ, which flows
       tight into "atha…" (the integral ॐ is part of the sutra text).

body TTS text  = "ॐ " + <sutra body>   (sacrificial primer, see sutra_tts_text()).
The primer's clipped ॐ residue is removed by trimming the body's leading silence
before splicing.
"""
import os, subprocess, tempfile

AUDIO = os.path.dirname(os.path.abspath(__file__))
EXEMPLAR = os.path.join(AUDIO, "assets", "pranava_exemplar.wav")
SR = 24000
GAP   = 0.25   # normal pranava gap
TIGHT = 0.08   # first-sutra: integral ॐ -> "atha" (part of the sutra)
PRIMER = "ॐ "  # sacrificial leading ॐ prepended to every sutra body before TTS

# BSB first sutra (integral opening ॐ). Extend if other works have their own.
FIRST_SUTRA_IDS = {"bsb_1_1_1"}

def sutra_tts_text(body_deva):
    """Text to send to the renderer for a sutra body (with sacrificial primer)."""
    return PRIMER + body_deva.strip()

def _run(*a):
    subprocess.run(a, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def _silence(dur, path):
    _run("ffmpeg", "-y", "-f", "lavfi", "-i",
         f"anullsrc=r={SR}:cl=mono", "-t", f"{dur}", path)

def _trim_lead_silence(src, dst):
    _run("ffmpeg", "-y", "-i", src, "-af",
         "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0",
         "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", dst)

def _concat(parts, out):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for p in parts:
            f.write(f"file '{p}'\n")
        lst = f.name
    _run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
         "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", out)
    os.unlink(lst)

def assemble_sutra(body_wav, out_wav, first=False):
    """body_wav = rendered sutra body (primer ॐ already clipped by the model).
    Splices exemplar pranava(s) per the approved pattern."""
    tmp = tempfile.mkdtemp()
    body_t = os.path.join(tmp, "body.wav"); _trim_lead_silence(body_wav, body_t)
    g   = os.path.join(tmp, "g25.wav"); _silence(GAP, g)
    gt  = os.path.join(tmp, "g08.wav"); _silence(TIGHT, gt)
    if first:
        parts = [EXEMPLAR, g, EXEMPLAR, gt, body_t, g, EXEMPLAR]
    else:
        parts = [EXEMPLAR, g, body_t, g, EXEMPLAR]
    _concat(parts, out_wav)
    return out_wav


if __name__ == "__main__":
    # reproduce the approved BSB 1.1.1 from the rendered body
    body = os.path.join(AUDIO, "out6", "fix_omprimer.wav")   # "ॐ अथातो ब्रह्मजिज्ञासा" render
    out  = os.path.join(AUDIO, "sutra_1_1_1_final.wav")
    assemble_sutra(body, out, first=True)
    dur = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                          "-of","default=nk=1:nw=1", out], capture_output=True, text=True).stdout.strip()
    print(f"BSB 1.1.1 (first-sutra rule) -> {out}  {dur}s")
