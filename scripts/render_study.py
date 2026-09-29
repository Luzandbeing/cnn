#!/usr/bin/env python3
"""Render transcript.json + study.json into one self-contained HTML study page.

Pure standard library: the template holds all CSS/JS, this script only embeds the
two JSON documents and reports what it rendered.

Usage:
    python3 render_study.py --transcript transcript.json --study study.json -o index.html
    python3 render_study.py --study study.json --check     # validate without writing
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "template.html"
PLACEHOLDERS = ("__STUDY_JSON__", "__TRANSCRIPT_JSON__")

SECTIONS = {
    "vocab": "生词",
    "phrases": "短语搭配",
    "grammar": "语法点",
    "patterns": "句型模板",
    "exercises": "练习",
}


def load_json(path: Path, label: str) -> dict:
    if not path.is_file():
        raise SystemExit(f"[render_study] {label} file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"[render_study] {label} is not valid JSON: {error}") from None
    if not isinstance(data, dict):
        raise SystemExit(f"[render_study] {label} must be a JSON object")
    return data


def validate(study: dict, transcript: dict) -> list[str]:
    """Return warnings; raise on problems the page cannot render at all."""
    warnings: list[str] = []
    meta = study.get("meta")
    if not isinstance(meta, dict) or not str(meta.get("title", "")).strip():
        raise SystemExit("[render_study] study.json needs meta.title")

    items = transcript.get("items")
    if not isinstance(items, list) or not items:
        raise SystemExit("[render_study] transcript.json has no items (run extract_pdf.py first)")
    numbers = {item.get("n") for item in items if isinstance(item, dict)}

    for key in SECTIONS:
        value = study.get(key)
        if value is None:
            warnings.append(f"study.json has no '{key}' section; the tab is hidden")
            continue
        if not isinstance(value, list):
            raise SystemExit(f"[render_study] '{key}' must be a JSON array")
        for index, entry in enumerate(value, 1):
            if not isinstance(entry, dict):
                raise SystemExit(f"[render_study] {key}[{index}] must be an object")
            refs = []
            if isinstance(entry.get("ref"), int):
                refs.append(entry["ref"])
            for example in entry.get("examples") or []:
                if isinstance(example, dict) and isinstance(example.get("ref"), int):
                    refs.append(example["ref"])
            if isinstance(entry.get("example"), dict) and isinstance(entry["example"].get("ref"), int):
                refs.append(entry["example"]["ref"])
            for ref in refs:
                if ref not in numbers:
                    warnings.append(f"{key}[{index}] references sentence {ref}, which is not in the transcript")

    for index, entry in enumerate(study.get("exercises") or [], 1):
        kind = entry.get("type", "choice")
        if kind not in ("choice", "fill", "translate"):
            warnings.append(f"exercises[{index}] has unknown type {kind!r}; rendered as fill-in")
        if kind == "choice" and not entry.get("options"):
            warnings.append(f"exercises[{index}] is a choice question without options")
        if entry.get("answer") in (None, "", []):
            warnings.append(f"exercises[{index}] has no answer")

    if not meta.get("summary"):
        warnings.append("meta.summary is empty; the overview will look bare")
    return warnings


def embed(payload: dict) -> str:
    """Serialize for a <script type=application/json> block."""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # a literal </script> would end the block early
    return text.replace("</", "<\\/")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a self-contained English study page.")
    parser.add_argument("--transcript", required=True, help="transcript.json from extract_pdf.py")
    parser.add_argument("--study", required=True, help="study.json with the learning content")
    parser.add_argument("-o", "--output", help="output HTML path (default: <study dir>/index.html)")
    parser.add_argument("--template", help=f"HTML template (default: {DEFAULT_TEMPLATE})")
    parser.add_argument("--check", action="store_true", help="validate inputs only, write nothing")
    args = parser.parse_args(argv)

    transcript = load_json(Path(args.transcript), "transcript")
    study = load_json(Path(args.study), "study")
    warnings = validate(study, transcript)

    counts = {key: len(study.get(key) or []) for key in SECTIONS}
    items = len(transcript["items"])
    level = (study.get("meta") or {}).get("level", "—")

    print(f"[render_study] transcript: {items} sentences")
    print(f"[render_study] study     : level={level} " +
          " ".join(f"{name}={counts[key]}" for key, name in SECTIONS.items()))
    for warning in warnings:
        print(f"  warning   : {warning}")

    if args.check:
        print("[render_study] --check only: nothing written")
        return 0
    if items == 0 or sum(counts.values()) == 0:
        print("[render_study] refusing to render a page with no sentences and no content", file=sys.stderr)
        return 2

    template_path = Path(args.template) if args.template else DEFAULT_TEMPLATE
    if not template_path.is_file():
        raise SystemExit(f"[render_study] template not found: {template_path}")
    template = template_path.read_text(encoding="utf-8")
    for placeholder in PLACEHOLDERS:
        if placeholder not in template:
            raise SystemExit(f"[render_study] template is missing {placeholder}: {template_path}")

    html = template.replace("__STUDY_JSON__", embed(study)).replace("__TRANSCRIPT_JSON__", embed(transcript))

    output = Path(args.output) if args.output else Path(args.study).resolve().parent / "index.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"[render_study] written   : {output}  ({output.stat().st_size / 1024:.1f} KB)  "
          f"{time.strftime('%H:%M:%S')}")
    print(f"[render_study] open with : open '{output}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
