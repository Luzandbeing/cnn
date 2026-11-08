#!/usr/bin/env python3
"""Strip block-level Chinese translations out of a transcript.json.

Some PDFs translate by paragraph, not by sentence: a block of English followed by a block
of Chinese covering several sentences. extract_pdf.py keeps the two glued together, so
`en` mixes English with Chinese and the sentence boundaries are wrong.

This script removes every CJK run, re-splits the remaining English into sentences, drops
punctuation debris, removes consecutive duplicates and renumbers 1..N. The result is an
English-only transcript: author `translations` for the sentences that need Chinese.

Usage:
    python3 clean_transcript.py transcript.json -o transcript_clean.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CJK = re.compile(
    r"[\u2e80-\u2fff\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef"
    r"\u2018\u2019\u201c\u201d\u3001\u3002\u300a\u300b]+"
)
ABB = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|St|e\.g|i\.e|etc|vs|No|Fig)\.$")
WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Za-z\"“'(\[])")


def sentences(chunk: str) -> list[str]:
    out: list[str] = []
    buf = ""
    for tok in SENT_SPLIT.split(chunk):
        if ABB.search(buf.rstrip()):
            buf = f"{buf} {tok}".strip()
            continue
        if buf:
            out.append(buf.strip())
        buf = tok.strip()
    if buf:
        out.append(buf.strip())
    return [s for s in out if s]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("transcript", help="transcript.json produced by extract_pdf.py")
    ap.add_argument("-o", "--output", help="cleaned transcript (default: <input>_clean.json)")
    ap.add_argument("--min-words", type=int, default=2,
                    help="drop fragments with fewer Latin words (default 2)")
    args = ap.parse_args()

    src = Path(args.transcript)
    data = json.loads(src.read_text(encoding="utf-8"))
    items = data.get("items") or []
    if not items:
        print(f"[clean_transcript] {src} has no items", file=sys.stderr)
        return 1
    if any((it.get("zh") or "").strip() for it in items):
        print("[clean_transcript] transcript already pairs Chinese per sentence — nothing to clean")
        return 0

    cjk_runs = 0
    kept = []
    for it in items:
        chunks, n = CJK.subn("\n", it.get("en") or "")
        cjk_runs += n
        for chunk in chunks.split("\n"):
            chunk = re.sub(r"\s+", " ", chunk).strip().lstrip(",;:")
            if not chunk:
                continue
            for s in sentences(chunk):
                if len(WORD.findall(s)) >= args.min_words:
                    kept.append({"page": it.get("page"), "en": s})

    dedup = []
    for it in kept:
        if dedup and dedup[-1]["en"] == it["en"]:
            continue
        dedup.append(it)
    for i, it in enumerate(dedup, 1):
        it["n"] = i
        it["zh"] = ""

    if not dedup:
        print("[clean_transcript] every English sentence was filtered out — check the PDF",
              file=sys.stderr)
        return 1

    dst = Path(args.output) if args.output else src.with_name(src.stem + "_clean.json")
    meta = dict(data.get("meta") or {})
    meta.update({"bilingual": False, "cleaned": True})
    dst.write_text(json.dumps({"items": dedup, "meta": meta}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    words = sum(len(WORD.findall(it["en"])) for it in dedup)
    print(f"[clean_transcript] {src.name} -> {dst.name}")
    print(f"  items {len(items)} -> {len(dedup)}   words {words}   CJK runs removed {cjk_runs}")
    if cjk_runs == 0:
        print("  note: no CJK found; the input was already English-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
