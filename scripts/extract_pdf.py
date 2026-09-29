#!/usr/bin/env python3
"""Extract a sentence list from a PDF into transcript.json for English study.

Handles the common "bilingual subtitle/transcript PDF" shape: numbered lines
where each item holds an English sentence followed by its Chinese translation.
Also handles plain English PDFs (then every item has an empty Chinese field).

Self-bootstrapping: when PyMuPDF is missing this script creates a virtualenv
(default: <cwd>/.english-study/venv), installs PyMuPDF into it, and re-executes
itself with that interpreter. Set ENGLISH_STUDY_VENV=<dir> to use another venv.

Usage:
    python3 extract_pdf.py SOURCE.pdf [-o transcript.json] [--format json|text|md]
                                       [--pages 1-5] [--min-items 1]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

VENV_ENV = "ENGLISH_STUDY_VENV"
DEFAULT_VENV_DIR = Path(".english-study") / "venv"


# --------------------------------------------------------------------------- #
# dependency bootstrap
# --------------------------------------------------------------------------- #
def _venv_python(venv_dir: Path) -> Path:
    for candidate in ("bin/python", "Scripts/python.exe"):
        path = venv_dir / candidate
        if path.exists():
            return path
    return venv_dir / "bin/python"


def _bootstrap() -> Path | None:
    """Create/reuse a venv with PyMuPDF. Return its interpreter, or None."""
    override = os.environ.get(VENV_ENV)
    venv_dir = Path(override).expanduser().resolve() if override else (Path.cwd() / DEFAULT_VENV_DIR).resolve()
    python = _venv_python(venv_dir)

    if not venv_dir.exists():
        print(f"[extract_pdf] creating venv at {venv_dir}", file=sys.stderr)
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    if not python.exists():
        print(f"[extract_pdf] venv has no interpreter: {venv_dir}", file=sys.stderr)
        return None
    # comparing interpreters by path would follow venv/bin/python's symlink back
    # to the system interpreter, so compare the venv root instead
    if Path(sys.prefix).resolve() == venv_dir.resolve():
        return None
    probe = subprocess.run([str(python), "-c", "import pymupdf"], capture_output=True)
    if probe.returncode != 0:
        print("[extract_pdf] installing pymupdf into the venv (one time)", file=sys.stderr)
        pip = venv_dir / ("Scripts/pip.exe" if os.name == "nt" else "bin/pip")
        install = subprocess.run(
            [str(pip), "install", "--disable-pip-version-check", "--no-input", "pymupdf"],
            capture_output=True,
            text=True,
        )
        if install.returncode != 0:
            print(install.stdout[-2000:] + install.stderr[-2000:], file=sys.stderr)
            return None
    return python


def _import_pdf_library():
    """Import PyMuPDF, bootstrapping a venv (and re-exec) if needed."""
    try:
        import pymupdf  # noqa: F401  (PyMuPDF >= 1.24)

        return pymupdf
    except ImportError:
        pass
    try:
        import fitz  # older name of the same library

        return fitz
    except ImportError:
        pass

    python = _bootstrap()
    if python is not None:
        os.execv(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]])
    raise SystemExit(
        "[extract_pdf] PyMuPDF is unavailable and could not be installed.\n"
        f"  Try: python3 -m venv <dir> && <dir>/bin/pip install pymupdf, then set {VENV_ENV}=<dir>"
    )


# --------------------------------------------------------------------------- #
# text normalization
# --------------------------------------------------------------------------- #
# NFKC folds Kangxi radicals (U+2F00-U+2FDF) onto real ideographs, but the CJK
# Radicals Supplement (U+2E80-U+2EFF) survives it. Fonts that emit radicals
# instead of characters are common in generated Chinese PDFs, so map them.
RADICAL_MAP = str.maketrans(
    {
        "\u2e80": "一", "\u2e84": "乙", "\u2e86": "亠", "\u2e87": "儿", "\u2e88": "入",
        "\u2e8a": "八", "\u2e8c": "冂", "\u2e8d": "冖", "\u2e95": "卩", "\u2e9c": "刀",
        "\u2e9d": "力", "\u2ea0": "民", "\u2ea2": "欠", "\u2ea3": "止", "\u2ea7": "爪",
        "\u2ea8": "父", "\u2eab": "片", "\u2ead": "牛", "\u2eaf": "犬", "\u2eb2": "玄",
        "\u2eb7": "目", "\u2eb9": "立", "\u2ebc": "而", "\u2ebd": "耳", "\u2ec2": "至",
        "\u2ec3": "臼", "\u2ec4": "西", "\u2ec5": "见", "\u2ec6": "角", "\u2ec7": "言",
        "\u2ec8": "谷", "\u2ec9": "贝", "\u2eca": "赤", "\u2ecb": "车", "\u2ecd": "辶",
        "\u2ecf": "邑", "\u2ed0": "酉", "\u2ed1": "釆", "\u2ed2": "里", "\u2ed3": "长",
        "\u2ed4": "門", "\u2ed6": "隹", "\u2ed7": "雨", "\u2ed8": "青", "\u2ed9": "非",
        "\u2eda": "面", "\u2edb": "风", "\u2edc": "飞", "\u2edd": "食", "\u2ede": "首",
        "\u2edf": "香", "\u2ee0": "馬", "\u2ee2": "马", "\u2ee3": "骨", "\u2ee4": "高",
        "\u2ee5": "鱼", "\u2ee6": "鳥", "\u2ee7": "鹵", "\u2ee8": "麦", "\u2ee9": "黄",
        "\u2eea": "黍", "\u2eeb": "黑", "\u2eec": "黹", "\u2eed": "黾", "\u2eee": "鼎",
        "\u2eef": "鼓", "\u2ef0": "鼠", "\u2ef1": "鼻", "\u2ef2": "齐", "\u2ef3": "齿",
        "\u2ef4": "龍", "\u2ef5": "龜",
    }
)

# lines that are watermarks / download prompts rather than study content
NOISE_PATTERNS = (
    re.compile(r"小鹦看看|Pollykann"),
    re.compile(r"台词本|字幕由|自动生成"),
    re.compile(r"^\s*https?://\S+\s*$"),
)

ITEM_RE = re.compile(r"^[ \t]*(\d{1,4})[ \t]+(?=\S)")
CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
# NFKC turns fullwidth Chinese punctuation into ASCII; put it back next to CJK
ASCII_PUNCT = {",": "，", ".": "。", ";": "；", ":": "：", "!": "！", "?": "？", "(": "（", ")": "）"}
CJK_PUNCT_RE = re.compile(
    r"[,.;:!?()](?=[\u3400-\u9fff\uf900-\ufaff])|(?<=[\u3400-\u9fff\uf900-\ufaff])[,.;:!?()]"
)
# a line wrap inside Chinese leaves a space between two ideographs; the wrap
# inside English needs its space, so only the Chinese side is squeezed
CJK_EDGE = "[\u3400-\u9fff\uf900-\ufaff，。；：！？、（）《》「」“”…—]"
CJK_SPACE_RE = re.compile(f"(?<={CJK_EDGE})[ \t]+(?={CJK_EDGE})")


def normalize_chinese(text: str) -> str:
    """Restore CJK punctuation and drop wrap-induced spaces in a Chinese run."""
    text = CJK_PUNCT_RE.sub(lambda match: ASCII_PUNCT[match.group(0)], text)
    return CJK_SPACE_RE.sub("", text)


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).translate(RADICAL_MAP)


def is_noise(line: str) -> bool:
    return any(pattern.search(line) for pattern in NOISE_PATTERNS)


def split_bilingual(text: str) -> tuple[str, str]:
    """Split one numbered item into (english, chinese)."""
    text = re.sub(r"[ \t]+", " ", text).strip()
    match = CJK_RE.search(text)
    if match is None:
        return text, ""
    index = match.start()
    english, chinese = text[:index], text[index:]
    return english.strip(" \t-—–"), normalize_chinese(chinese.strip())


def collect_lines(doc, page_from: int, page_to: int) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for number in range(page_from, page_to + 1):
        page = doc.load_page(number - 1)
        for raw_line in normalize(page.get_text()).splitlines():
            line = raw_line.rstrip()
            if not line.strip() or is_noise(line):
                continue
            lines.append((number, line))
    return lines


def parse_items(lines: list[tuple[int, str]]) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    warnings: list[str] = []
    buffer: list[str] = []
    current: dict | None = None
    expected = 1

    def flush() -> None:
        if current is None:
            return
        english, chinese = split_bilingual(" ".join(buffer))
        current["en"] = english
        current["zh"] = chinese
        items.append(current)

    for page, line in lines:
        match = ITEM_RE.match(line)
        if match is not None:
            number = int(match.group(1))
            # accept a new item on the expected number, or any larger number
            # (keeps going after an unnumbered gap instead of merging items)
            if number == expected or number > expected:
                flush()
                if number != expected:
                    warnings.append(f"numbering jumped from {expected - 1} to {number} (page {page})")
                expected = number + 1
                current = {"n": number, "page": page, "en": "", "zh": ""}
                buffer = [line[match.end():]]
                continue
        if current is None:
            continue  # title/preamble before the first numbered line
        buffer.append(line)

    flush()
    return items, warnings


# --------------------------------------------------------------------------- #
# output
# --------------------------------------------------------------------------- #
def build_document(pdf_path: Path, items: list[dict], pages: int, warnings: list[str], elapsed: float) -> dict:
    english_words = sum(len(re.findall(r"[A-Za-z][A-Za-z'’-]*", item["en"])) for item in items)
    bilingual = sum(1 for item in items if item["zh"])
    return {
        "source": {
            "path": str(pdf_path),
            "name": pdf_path.name,
            "stem": pdf_path.stem,
            "pages": pages,
        },
        "stats": {
            "pages": pages,
            "items": len(items),
            "englishWords": english_words,
            "itemsWithChinese": bilingual,
            "bilingual": len(items) > 0 and bilingual >= len(items) * 0.6,
            "extractedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "extractor": "extract_pdf.py (PyMuPDF)",
            "seconds": round(elapsed, 2),
        },
        "warnings": warnings,
        "items": items,
    }


def render_text(document: dict, style: str) -> str:
    items = document["items"]
    source = document["source"]
    stats = document["stats"]
    out = [
        f"# {source['name']}",
        f"pages={stats['pages']} items={stats['items']} englishWords={stats['englishWords']} "
        f"withChinese={stats['itemsWithChinese']} bilingual={stats['bilingual']}",
        "",
    ]
    for item in items:
        if style == "md":
            out.append(f"{item['n']}. **{item['en']}**")
            if item["zh"]:
                out.append(f"   - {item['zh']}  (p.{item['page']})")
        else:
            out.append(f"{item['n']}\t{item['en']}\t{item['zh']}\t{'' if item['zh'] else ''}\t{item['page']}")
    return "\n".join(out) + "\n"


def parse_pages(spec: str | None, total: int) -> tuple[int, int]:
    if not spec:
        return 1, total
    match = re.fullmatch(r"(\d+)(?:\s*-\s*(\d+))?", spec.strip())
    if match is None:
        raise SystemExit(f"[extract_pdf] bad --pages value: {spec!r} (expected N or N-M)")
    first = int(match.group(1))
    last = int(match.group(2)) if match.group(2) else first
    if first < 1 or last < first or first > total:
        raise SystemExit(f"[extract_pdf] --pages {spec} is outside 1-{total}")
    return first, min(last, total)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract a numbered bilingual sentence list from a PDF.")
    parser.add_argument("pdf", help="source PDF path")
    parser.add_argument("-o", "--output", help="transcript JSON path (default: <stem>.transcript.json)")
    parser.add_argument("--format", choices=("json", "text", "md"), default="json",
                        help="json writes the file; text/md print to stdout")
    parser.add_argument("--pages", help="page range to extract, e.g. 1-5")
    parser.add_argument("--min-items", type=int, default=1, help="fail when fewer items are found")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    pdf_path = Path(args.pdf).expanduser()
    if not pdf_path.is_file():
        raise SystemExit(f"[extract_pdf] no such file: {pdf_path}")

    pymupdf = _import_pdf_library()
    doc = pymupdf.open(pdf_path)
    try:
        page_from, page_to = parse_pages(args.pages, doc.page_count)
        lines = collect_lines(doc, page_from, page_to)
        items, warnings = parse_items(lines)
        document = build_document(pdf_path, items, doc.page_count, warnings, time.perf_counter() - started)
    finally:
        doc.close()

    if len(items) < args.min_items:
        raise SystemExit(
            f"[extract_pdf] found only {len(items)} numbered items in {pdf_path.name}. "
            "This PDF may be a scan (no text layer) or not numbered; "
            "try --pages or inspect the text layer first."
        )

    if args.format in ("text", "md"):
        sys.stdout.write(render_text(document, args.format))
        return 0

    output = Path(args.output) if args.output else pdf_path.with_suffix(".transcript.json")
    output.write_text(json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8")
    stats = document["stats"]
    print(f"[extract_pdf] {pdf_path.name}")
    print(f"  items      : {stats['items']}  (pages {page_from}-{page_to} of {stats['pages']})")
    print(f"  english    : {stats['englishWords']} words, bilingual={stats['bilingual']}")
    print(f"  written    : {output}")
    for warning in warnings[:5]:
        print(f"  warning    : {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
