---
name: english-study-from-pdf
description: Use when the user wants to study English from a PDF (news transcript, subtitle sheet, article, textbook chapter) and wants vocabulary, phrases, grammar points, sentence patterns, exercises, or a rendered HTML study page. Extracts the PDF text, structures it into numbered sentence pairs, and renders a self-contained interactive page.
whenToUse: The user points at a PDF and asks for English learning material, vocabulary/grammar extraction, a study page, or a "英语学习" deliverable.
---

# English study page from a PDF

Turn one PDF into a self-contained interactive HTML study page: sentence-by-sentence
bilingual reading, vocabulary cards, phrase list, grammar points, sentence patterns,
and exercises with answers.

Division of labour: **the scripts do the mechanical work** (text extraction, sentence
splitting, HTML rendering) and **you do the teaching analysis** (choose the vocabulary,
explain the grammar, write the exercises). Never hand-write the HTML — the template
already handles layout, highlighting, TTS, progress tracking and deep links.

## Workflow

Let `SKILL_DIR` be the `resourceBase.path` returned when this skill loaded (the directory
containing this `SKILL.md`). Work in the session workspace, not in the skill directory.

### 1. Extract the transcript

```bash
python3 "$SKILL_DIR/scripts/extract_pdf.py" SOURCE.pdf -o "<out>/transcript.json"
```

The script normalizes text (NFKC + CJK radical/punctuation repair), splits the document
into `{n, page, en, zh}` items, and prints a summary (`mode`, `items`, `englishWords`,
`bilingual`). It bootstraps its own venv with PyMuPDF on first run (default
`<cwd>/.english-study/venv`, override with `ENGLISH_STUDY_VENV`); that first run needs
network, later runs are offline.

Two extraction modes are picked automatically (`--mode auto`):

- **number** — subtitle/transcript sheets whose lines start with a sentence number and
  pair English with Chinese.
- **prose** — unnumbered running text (articles, podcast transcripts, book chapters):
  wrapped lines are joined, paragraphs kept, and sentences split with abbreviation and
  decimal awareness. Force one with `--mode number` / `--mode prose`.

Read the summary before continuing:

- `bilingual: true` — the PDF already pairs English with Chinese; keep that translation.
- `bilingual: false` — English-only source. Every `zh` is empty; the page then hides the
  Chinese toggle and shows a 纯英文原文 badge. Optionally author Chinese for any subset of
  sentences in `study.json` as `"translations": {"12": "…", "13": "…"}` (see step 2) —
  never hand-edit `transcript.json`.
- `items: 0` or a "may be a scan" error — the PDF has no text layer. Tell the user instead
  of inventing content; OCR is out of scope for this skill.

In prose mode the sentence numbering is the extractor's, not the source's, so `ref` values
refer to those numbers. Spot-check a few items with `--format text` before citing refs:
spoken transcripts contain very long comma-heavy sentences (200+ characters) — that is
correct, not a splitting failure.

To read the extracted text (for your own analysis), do **not** paste the whole JSON into
context; page through it:

```bash
python3 "$SKILL_DIR/scripts/extract_pdf.py" SOURCE.pdf --format text --pages 1-6
```

`--format text` prints `n<TAB>en<TAB>zh<TAB>page`. Long documents: read in chunks of
5–8 pages while you draft the corresponding `study.json` sections, then continue with the
next chunk. Re-extraction is cheap and idempotent.

### 2. Author `study.json`

Write the analysis yourself. Ground every item in the actual text and cite the sentence
number in `ref`; the renderer cross-checks refs against the transcript and warns about
dangling ones.

```jsonc
{
  "meta": {
    "title": "…",                  // required
    "subtitle": "…",               // source + item count
    "level": "B1–B2",              // your CEFR judgement, shown as a badge
    "summary": "…",                // 3–5 sentences of Chinese overview
    "topics": ["山火与撤离", "…"],
    "learningFocus": ["…"],        // 4–6 bullets: what this text teaches
    "studyPlan": ["第 1 步（15 分钟）：…"],   // 4–6 timeboxed steps
    "estimatedMinutes": 90
  },
  "vocab": [
    {"term": "evacuate", "ipa": "/ɪˈvækjueɪt/", "pos": "v.", "zh": "撤离，疏散",
     "level": "B2",                // A2 | B1 | B2 | C1 (colours the badge)
     "note": "及物/不及物均可；名词 evacuation。",
     "forms": ["evacuated", "evacuating"],       // optional extra highlight forms
     "examples": [{"en": "…", "zh": "…", "ref": 2}]}
  ],
  "phrases": [
    {"term": "on high alert", "pos": "prep. phrase", "zh": "处于高度戒备状态",
     "note": "固定搭配；也可说 be on full alert。",
     "example": {"en": "…", "zh": "…"}, "ref": 26}
  ],
  "grammar": [
    {"title": "现在分词作结果状语", "structure": "主句 + , + v-ing",
     "explain": "…",                               // why it is used, in Chinese
     "examples": [{"en": "…", "zh": "…", "ref": 18, "note": "可选补充"}],
     "caution": "易错点/对比提醒"}
  ],
  "patterns": [
    {"en": "What started as A exploded to B.", "zh": "起初是 A，后来变成 B。",
     "usage": "使用场景说明", "rewrite": "同义改写", "ref": 75}
  ],
  "exercises": [
    {"type": "choice", "question": "…", "options": ["…", "…", "…", "…"],
     "answer": "A", "explain": "为什么"},
    {"type": "fill", "question": "… ______ (force) …", "answer": ["were forced", "was forced"],
     "explain": "…"},                                        // answer may be a string or a list
    {"type": "translate", "question": "翻译成英文：…", "answer": ["…"], "explain": "…"}
  ],
  "translations": { "12": "只给需要的句子写中文对照（纯英文原文时才用）", "13": "…" }
}
```

Rules that keep the page useful:

- `ref` must be an integer sentence number from the transcript — verify against the
  extractor output, never guess. Omit `ref` rather than invent one.
- Every section is optional; an empty/absent section hides its tab. Aim for roughly
  1 vocab item per 6–8 sentences, 1 grammar point per 25–35 sentences, and 10–15 exercises
  for a 300–400 sentence document. Proportional, not exhaustive.
- Vocabulary must actually occur in the document, and `examples[].en` should be the real
  sentence from that `ref` (shortened with `…` is fine).
- IPA: use one accent consistently (British is the default here) and say so in `meta.note`
  only if it matters.
- Transcripts are machine-generated and contain mis-hearings. When you hit one, teach the
  correct form and flag it (e.g. a spoken "a step in stone" that should be *a stepping
  stone*) — put the note on the vocabulary/phrase entry rather than silently fixing the
  quoted sentence.
- Exercises: mix meaning (vocabulary in context), form (word formation, tense, passive)
  and production (translation using the text's own patterns). `explain` should teach the
  rule, not just state the answer.
- `translations` is only for English-only sources. Keep it to a subset the learner needs
  (key openings, hard sentences) rather than machine-translating everything; the page shows
  the toggle as soon as one sentence has Chinese. Keys that are not sentence numbers, or
  that duplicate Chinese already present in the transcript, are reported as warnings.

### 3. Render

```bash
python3 "$SKILL_DIR/scripts/render_study.py" \
  --transcript "<out>/transcript.json" --study "<out>/study.json" -o "<out>/index.html"
```

`--check` validates without writing. The renderer prints per-section counts and warns
about dangling `ref`s, choice questions without options, and empty answers — fix what it
reports before presenting.

### 4. Verify and deliver

The page is offline and dependency-free, but it is JavaScript-rendered, so a wrong field
name shows up as an empty tab. Verify before claiming success:

- Re-run with `--check`, or render and confirm the printed counts are non-zero.
- If a headless browser is available, load it and confirm rendering, e.g.
  `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --dump-dom "file://$PWD/<out>/index.html"`
  (macOS Chrome may not exit after dumping; run it in the background and kill it, or add
  `--virtual-time-budget=4000`). Count `class="vcard"`, `class="sent"` and
  `<details` occurrences against the study.json counts.
- Then `present` the `index.html` and tell the user what to click: 逐句精读 for reading
  with audio, 生词 for the cards and mastery tracking, 练习 for the drills.

## Output layout

```
<workspace>/study/<pdf-stem>/
  transcript.json   # machine output, do not hand-edit
  study.json        # your analysis, editable and re-renderable
  index.html        # the deliverable
```

Keep the three files together: re-rendering after editing `study.json` is instant, so
never rewrite the HTML by hand.

## Page features (already implemented — do not re-invent)

- Tabs: 概览 / 逐句精读 / 收藏句 / 生词 / 短语搭配 / 语法点 / 句型模板 / 练习 (empty
  sections hidden; 收藏句 is always present and shows an empty-state hint).
- Deep links: `#sentences`, `#vocab`, `#starred`, … select a tab; `#s123` jumps to
  sentence 123, and `ref` links work across tabs.
- Sentence list: Chinese hidden/shown as one toggle (auto-hidden, with a 纯英文原文 badge,
  when the source has no Chinese and no `translations` were authored), per-sentence TTS
  (Web Speech API, rate selectable), star/favourite, filter to starred or
  vocabulary-bearing sentences. The `★ 收藏句 N` toolbar button flips straight to the
  starred-only view.
- 收藏句 tab: starred sentences with Chinese, audio and a jump-back link, plus
  导出 Markdown (triggers a `.md` download and shows a selectable preview) and 清空收藏.
  Toggling a star anywhere refreshes the toolbar counter, the tab badge and any visible
  list immediately, including removing the row while the starred-only filter is active.
- Vocabulary cards: meaning, IPA, level badge, example with a link to its sentence,
  "mastered" toggle, filters and search; mastery + stars + language toggle + TTS rate
  persist in `localStorage` under `englishStudy:<pdf-stem>`.
- Grammar accordions, phrase table, pattern cards, self-checking exercises
  (multiple choice / fill-in / translation) with 显示全部答案 and 重做.
- Dark mode follows the system theme; print stylesheet expands all Chinese and tabs.

## Environment notes

- `extract_pdf.py` needs PyMuPDF only; the bootstrap venv is created in the workspace so
  no approval is needed for writes outside it. Set `ENGLISH_STUDY_VENV=/some/dir` to share
  one venv across workspaces.
- `render_study.py` is pure standard library and needs no venv.
- Both scripts are safe to re-run; extraction output paths are deterministic.
