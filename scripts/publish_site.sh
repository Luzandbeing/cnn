#!/usr/bin/env bash
# Publish a rendered study page into the English study site (GitHub Pages).
#
# Usage:
#   publish_site.sh <study-dir> [--name "2026.11.08 - Title"] [--site DIR] [--dry-run]
#
# <study-dir> must contain index.html + study.json (render_study.py output).
# Site root defaults to ~/Documents/English; override with SITE_DIR or --site.
# --dry-run copies the page and rebuilds the site index, but does not commit or push.
set -euo pipefail

die() { echo "publish_site: $*" >&2; exit 1; }

SITE="${SITE_DIR:-$HOME/Documents/English}"
STUDY=""
NAME=""
DRY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --name) [ $# -ge 2 ] || die "--name needs a value"; NAME="$2"; shift 2 ;;
    --site) [ $# -ge 2 ] || die "--site needs a value"; SITE="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    -*) die "unknown option: $1" ;;
    *) [ -z "$STUDY" ] || die "only one <study-dir> allowed"; STUDY="$1"; shift ;;
  esac
done

[ -n "$STUDY" ] || die "usage: publish_site.sh <study-dir> [--name ...] [--site DIR] [--dry-run]"
STUDY="${STUDY%/}"
[ -f "$STUDY/index.html" ] || die "no index.html in $STUDY — render first"
[ -f "$STUDY/study.json" ] || die "no study.json in $STUDY"
[ -d "$SITE" ] || die "site not found: $SITE (set SITE_DIR)"
[ -d "$SITE/.git" ] || die "not a git repo: $SITE"
[ -f "$SITE/tools/build_index.py" ] || die "missing $SITE/tools/build_index.py"
[ -f "$SITE/tools/publish.sh" ] || die "missing $SITE/tools/publish.sh"
[ -d "$SITE/study" ] || die "missing $SITE/study"

if [ -z "$NAME" ]; then
  title="$(python3 - "$STUDY/study.json" <<'PY'
import json, sys
meta = json.load(open(sys.argv[1], encoding="utf-8")).get("meta") or {}
print((meta.get("title") or "").strip())
PY
)"
  [ -n "$title" ] || die "study.json has no meta.title — pass --name"
  NAME="$(date +%Y.%m.%d) - $title"
fi
NAME="${NAME//\//-}"

DEST="$SITE/study/$NAME"
mkdir -p "$DEST"
cp "$STUDY/index.html" "$STUDY/study.json" "$DEST/"
for f in transcript.json transcript_clean.json; do
  if [ -f "$STUDY/$f" ]; then cp "$STUDY/$f" "$DEST/"; fi
done
echo "==> page copied to $DEST"

echo "==> rebuilding site index"
python3 "$SITE/tools/build_index.py"

dirty="$(git -C "$SITE" status --porcelain | wc -l | tr -d ' ')"
if [ "$dirty" -gt 0 ]; then
  echo "    note: these changed paths will be committed by tools/publish.sh:"
  git -C "$SITE" status --short | sed 's/^/      /'
fi

if [ "$DRY" = "1" ]; then
  echo "==> dry run: stopped before commit/push"
  exit 0
fi

echo "==> publishing (tools/publish.sh)"
"$SITE/tools/publish.sh"
