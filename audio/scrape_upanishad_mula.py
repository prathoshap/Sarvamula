#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pull the Upaniṣad mūla for Aitareya / Bṛhadāraṇyaka(Kāṇva) / Chāndogya off anandamakaranda.in.

Our editions of these three bhāṣyas carry the COMMENTARY ONLY — Madhva's gloss with no
Upaniṣad text between the glosses, which is why they were segmented with mula="__none__"
and why the reader shows a bhāṣya on a text it never states. anandamakaranda's pages carry
both, marked up distinctly (span.shloka-line = mūla, div.bhashyam-block = bhāṣya), so the
mūla can be lifted and dropped into the gaps.

Parsed with a real HTML parser rather than a regex: bhashyam-block nests further tags, and
a non-greedy </div> match silently truncates every block at its first inner close — which
looked like "the site has half the bhāṣya we do" until it was parsed properly.

Output is document-ordered so the mūla can be placed by POSITION relative to the bhāṣya
that comments on it, which is the only ordering that survives the two editions disagreeing
about khaṇḍa boundaries.
"""
import argparse, json, re, unicodedata
from html.parser import HTMLParser

# gr-verse-text-gr-gadya-line is NOT mūla despite sitting in the verse container: all 195
# of Chāndogya's are the site's own topic labels (उद्गीथोपासना, भक्तिविरक्ती अपि मोक्षसाधने),
# never Upaniṣad text — none of them carries a daṇḍa. Reciting them would put an editor's
# subject headings into the mouth of the śruti.
KIND = {"shloka-line": "mula", "bhashyam-block": "bhashya",
        "gr-author-note": "note", "introduction-line": "intro",
        "gr-verse-text-gr-gadya-line": "label"}


class Reader(HTMLParser):
    """Emit (kind, text) in document order, attributing text to the nearest enclosing
    tagged ancestor — nested markup inside a block belongs to that block."""

    def __init__(self):
        super().__init__()
        self.stack, self.out, self.buf, self.cur = [], [], [], None

    def _flush(self):
        t = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if t and self.cur:
            self.out.append((self.cur, t))
        self.buf = []

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class", "") or ""
        kind = next((v for k, v in KIND.items() if k in cls), None)
        if tag == "br":
            self.buf.append(" ")
            return
        if kind:
            self._flush()
            self.stack.append((tag, kind))
            self.cur = kind
        elif self.stack:
            self.stack.append((tag, None))

    def handle_endtag(self, tag):
        if not self.stack:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                if self.stack[i][1]:
                    self._flush()
                del self.stack[i:]
                break
        self.cur = next((k for _, k in reversed(self.stack) if k), None)

    def handle_data(self, data):
        if self.cur:
            self.buf.append(data)


def norm(s):
    return re.sub(r"[^ऀ-ॿ]", "", unicodedata.normalize("NFC", s))


def parse(path):
    r = Reader()
    r.feed(open(path, encoding="utf-8", errors="replace").read())
    r._flush()
    return [(k, t) for k, t in r.out if norm(t)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    seq = parse(a.html)
    json.dump([{"kind": k, "text": t} for k, t in seq],
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    import collections
    c = collections.Counter(k for k, _ in seq)
    chars = collections.Counter()
    for k, t in seq:
        chars[k] += len(norm(t))
    print(f"{a.html}: " + ", ".join(f"{k}={c[k]} ({chars[k]:,} akṣ)" for k in sorted(c)))
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
