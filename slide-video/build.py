#!/usr/bin/env python3
"""slide-video build (v2): YAML script -> HTML + MP3 + MP4 (+ optional VTT).

v2 schema: named layouts (title, hook, compare, example, iterations, enumeration,
recap, code, math, diagram, table, html-escape) plus cross-cutting affordances
(copy-btn on text/code, info-btn deep-dive panels, intra-slide micro-reveals
at sentence-boundary granularity, color-as-config, voice config).

Pipeline:
  1. edge-tts  : render narration -> mp3 + sentence-boundary timestamps
  2. dispatch  : per-layout HTML emitter -> slide HTML
  3. template  : inject slides + slideTimes[] + revealEvents[] + infoData[]
  4. (optional) Playwright headless capture -> webm
  5. (optional) ffmpeg mux -> mp4
  6. (optional) emit .vtt captions
"""

import argparse
import asyncio
import hashlib
import html as html_lib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from urllib.parse import quote
from pathlib import Path

import edge_tts
import yaml
from mutagen.mp3 import MP3

HERE = Path(__file__).parent
TEMPLATE_PATH = HERE / "template.html"
CDN_CACHE_DIR = HERE / "resources" / "cdn-cache"

# Curated voice shortlist — register-tagged for easy authoring.
VOICE_SHORTLIST = {
    "conversational":   "en-US-AriaNeural",
    "formal":           "en-US-GuyNeural",
    "friendly":         "en-US-JennyNeural",
    "calm":             "en-US-DavisNeural",
    "neutral":          "en-US-EmmaNeural",
    "british-female":   "en-GB-SoniaNeural",
    "british-male":     "en-GB-RyanNeural",
    "german-female":    "de-DE-KatjaNeural",
    "german-male":      "de-DE-ConradNeural",
    # Multilingual voices (v2.4): one voice that speaks many languages.
    # Use for bilingual builds when both tracks should sound like the SAME
    # speaker. Native-language voices (above) have the more idiomatic accent;
    # multilingual voices keep cross-language voice identity. Let the
    # operator's ear decide — generate a one-sentence sample in each first.
    "multilingual-male":    "en-US-AndrewMultilingualNeural",
    "multilingual-female":  "en-US-AvaMultilingualNeural",
    "german-multilingual-male":   "de-DE-FlorianMultilingualNeural",
    "german-multilingual-female": "de-DE-SeraphinaMultilingualNeural",
}


# ============================================================================
# CDN dep inlining (v2.2 — closes Run #22 C5-r offline-broken finding)
# ============================================================================

def _fetch_cached(url: str, cache_dir: Path) -> str:
    """Fetch URL contents, cache to disk, return as text."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    name_base = url.rstrip("/").split("/")[-1].split("?")[0] or "asset"
    cached = cache_dir / f"{name_base}-{h}"
    if not cached.exists():
        print(f"       fetching {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "slide-video-skill/2.2"})
        with urllib.request.urlopen(req, timeout=30) as r:
            content = r.read().decode("utf-8")
        cached.write_text(content, encoding="utf-8")
    return cached.read_text(encoding="utf-8")


_LINK_PATTERN = re.compile(
    r'<link\s+rel="stylesheet"\s+href="(https?://[^"]+)"[^>]*?/?>',
    re.IGNORECASE,
)
_SCRIPT_PATTERN = re.compile(
    r'<script([^>]*?)src="(https?://[^"]+)"([^>]*?)>([^<]*)</script>',
    re.IGNORECASE | re.DOTALL,
)
_ONLOAD_PATTERN = re.compile(r'onload="([^"]+)"', re.IGNORECASE | re.DOTALL)


def inline_cdn_deps(html_text: str, cache_dir: Path = CDN_CACHE_DIR) -> str:
    """Replace external <script src="CDN"> and <link rel="stylesheet" href="CDN">
    tags with inline equivalents. Fetches CDN content (cached locally) and
    embeds. Closes the offline-distribution gap surfaced by Run #22 C5-r.

    Notes:
    - Google Fonts @import inside <style> blocks is NOT inlined in v2.2 (would
      require fetching woff2 font files and base64-embedding into the CSS).
      Typography falls back to system fonts offline; functional rendering of
      math/code/diagrams works.
    - Scripts with `onload=` attributes (e.g., KaTeX auto-render): the onload
      code is wrapped in a DOMContentLoaded handler appended after the inlined
      script content, since `defer` doesn't apply to inline scripts.
    """
    out = html_text

    # CSS first (so fonts.googleapis.com @imports inside the inlined sheets
    # aren't double-processed by the script regex)
    for m in list(_LINK_PATTERN.finditer(out)):
        url = m.group(1)
        try:
            css = _fetch_cached(url, cache_dir)
        except Exception as e:
            print(f"       WARNING: inline-deps failed to fetch {url}: {e}")
            continue
        replacement = f"<style>\n/* inlined from {url} */\n{css}\n</style>"
        out = out.replace(m.group(0), replacement, 1)

    # Scripts — preserve onload semantics by wrapping in DOMContentLoaded handler
    for m in list(_SCRIPT_PATTERN.finditer(out)):
        url = m.group(2)
        post_attrs = m.group(3) or ""
        try:
            js = _fetch_cached(url, cache_dir)
        except Exception as e:
            print(f"       WARNING: inline-deps failed to fetch {url}: {e}")
            continue
        onload_match = _ONLOAD_PATTERN.search(post_attrs)
        if onload_match:
            onload_code = onload_match.group(1).replace("&quot;", '"').replace("&apos;", "'")
            replacement = (
                f"<script>\n/* inlined from {url} */\n{js}\n"
                f"document.addEventListener('DOMContentLoaded', function() {{ {onload_code} }});\n"
                f"</script>"
            )
        else:
            replacement = f"<script>\n/* inlined from {url} */\n{js}\n</script>"
        out = out.replace(m.group(0), replacement, 1)

    return out


# ============================================================================
# TTS
# ============================================================================

async def run_tts(text: str, voice: str, out_mp3: Path) -> list[float]:
    """Render TTS; return sentence-start offsets in seconds."""
    communicate = edge_tts.Communicate(text, voice)
    raw: list[tuple[float, str]] = []
    with open(out_mp3, "wb") as f:
        async for chunk in communicate.stream():
            ctype = chunk.get("type")
            if ctype == "audio":
                f.write(chunk["data"])
            elif ctype == "SentenceBoundary":
                # offset is in 100-ns units (HNS)
                raw.append((chunk["offset"] / 10_000_000, chunk.get("text", "")))
    # v2.5: edge-tts splits long inputs into multiple service requests at
    # whitespace seams; a seam landing mid-sentence emits a spurious extra
    # SentenceBoundary whose text does not END a sentence (e.g. 'Sie' +
    # 'setzen eine harte Längenobergrenze.'). Merge such fragments into their
    # successor so boundary counts match the authoring-side sentence split.
    boundaries: list[float] = []
    carry_start: float | None = None
    for start, btext in raw:
        if carry_start is not None:
            start = carry_start
            carry_start = None
        if btext and not re.search(r"[.!?…][\"'»«)\]]*\s*$", btext.strip()):
            carry_start = start
            continue
        boundaries.append(start)
    if carry_start is not None:
        boundaries.append(carry_start)
    if not boundaries:
        raise RuntimeError(
            "edge-tts produced no SentenceBoundary events. "
            "Check that narration contains complete sentences ending in . ! or ?"
        )
    return boundaries


SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def count_sentences(text: str) -> int:
    parts = [p for p in SENT_SPLIT.split(text.strip()) if p]
    return max(1, len(parts))


# Patterns that commonly trip the sentence splitter — author-visible diagnostic
# only. Documented pitfall class beyond simple period-abbreviations.
SPLITTER_PITFALL_PATTERNS = [
    (re.compile(r"\b\d+\.\d+\b"), "decimal/version (e.g. `2.0`, `top_k=5.0`)"),
    (re.compile(r"\b[Vv]\d+\.\d+\b"), "version string (e.g. `v2.0`)"),
    (re.compile(r"\b\w+\.(yaml|yml|json|md|txt|html|js|py|csv|tsv|sh|toml|ini)\b"),
     "file extension (e.g. `script.yaml`)"),
    (re.compile(r"\bNo\.\s*\d+", re.IGNORECASE), "ordinal `No. N`"),
    (re.compile(r"\b\d+\."), "period after digit (e.g. `1.`, `42.`)"),
    (re.compile(r"https?://\S+"), "URL"),
    (re.compile(r"\.{3,}"), "ellipsis"),
    (re.compile(r"\b(e\.g|i\.e|Dr|Mr|Mrs|Ms|etc|cf|vs|approx|fig|eq)\.", re.IGNORECASE),
     "abbreviation"),
]


def detect_splitter_pitfalls(text: str) -> list[str]:
    """Identify period-bearing patterns that commonly trip the sentence splitter."""
    hits = []
    for rx, label in SPLITTER_PITFALL_PATTERNS:
        matches = rx.findall(text)
        if matches:
            sample = matches[0] if isinstance(matches[0], str) else matches[0][0]
            hits.append(f"{label}: `{sample}`")
    return hits


# ============================================================================
# Layout dispatchers — each takes a slide dict, returns inner HTML
# ============================================================================

def _badge_html(badge: dict | None) -> str:
    if not badge:
        return ""
    text = badge.get("text", "")
    color = badge.get("color", "blue")
    return f'<div class="concept-badge badge-{color}">{html_lib.escape(text)}</div>'


def _info_btn_html(slide: dict) -> str:
    panel = slide.get("info_panel")
    if not panel:
        return ""
    topic = panel.get("topic", "info")
    return f'<button class="info-btn" onclick="openInfo(\'{topic}\', event)" title="Open side panel with more detail">&#9432; more</button>'


_BRACKET_PLACEHOLDER_RX = re.compile(r"\[[^\[\]\n]+\]")


def _copy_btn_html(text: str | bool | None, label: str = "Copy example") -> str:
    if not text:
        return ""
    if text is True:
        # Copy button without explicit text — caller must set the text via JS or omit
        return ""
    # JSON-escape for inline JS, THEN attribute-escape: json.dumps produces a
    # double-quoted string which would otherwise terminate the double-quoted
    # onclick attribute at its first character (shipped bug, found 2026-06-11
    # in a production beginner-video output — every copy button dead).
    # The browser decodes &quot; in attribute values before the JS parser runs.
    safe = html_lib.escape(json.dumps(text), quote=True)
    btn = f'<button class="copy-btn" onclick="copyText({safe}, this, event)">{html_lib.escape(label)}</button>'
    # Bracket-placeholder hint: if the copy text contains [bracketed text],
    # surface a one-line reminder so HTML-only viewers (who don't have the
    # audio narration's bracket convention explainer) know to substitute
    # before pasting. Audio viewers see this redundantly — net win for
    # discoverability outweighs the minor on-screen repetition.
    if isinstance(text, str) and _BRACKET_PLACEHOLDER_RX.search(text):
        btn += '<span class="copy-hint">Replace <code>[bracketed parts]</code> before sending.</span>'
    return btn


def render_title(slide: dict) -> str:
    """Title slide: badge + h1 + subtitle + optional author."""
    parts = [_badge_html(slide.get("badge"))]
    if "title" in slide:
        parts.append(f'<h1>{slide["title"]}</h1>')
    if "subtitle" in slide:
        parts.append(f'<p class="subtitle">{slide["subtitle"]}</p>')
    if "author" in slide:
        parts.append(f'<p class="author">{html_lib.escape(slide["author"])}</p>')
    return "\n".join(p for p in parts if p)


def render_hook(slide: dict) -> str:
    """Hook slide: h2 with optional highlighted span + subtitle."""
    parts = []
    if "heading" in slide:
        parts.append(f'<h2>{slide["heading"]}</h2>')
    if "subtitle" in slide:
        parts.append(f'<p class="subtitle">{slide["subtitle"]}</p>')
    return "\n".join(parts)


def render_compare(slide: dict) -> str:
    """Compare slide: 2 boxes side-by-side or stacked.

    YAML pair keys (pick one per slide):
      bad / good     — value-coded comparison (red/green styling)
      left / right   — neutral comparison (no value implication, gray/blue styling)

    Each pair-side accepts:
      label : str   — header text for the box
      text  : str   — body HTML (canonical field; `body` accepted for back-compat)
      copy  : str   — optional copy-button payload
    """
    parts = [_badge_html(slide.get("badge"))]
    if "heading" in slide:
        parts.append(f'<h2>{slide["heading"]}</h2>')

    direction = slide.get("direction", "row")
    container_class = "compare-container" + (" column" if direction == "column" else "")

    boxes = []
    for kind in ("bad", "good", "left", "right"):
        if kind not in slide:
            continue
        b = slide[kind]
        label = b.get("label", "")
        body = b.get("text") or b.get("body", "")
        copy_text = b.get("copy")
        copy_btn = _copy_btn_html(copy_text) if copy_text else ""
        box = (
            f'<div class="compare-box compare-{kind}">\n'
            f'  <div class="compare-label">{html_lib.escape(label)}</div>\n'
            f'  {body}\n'
            f'  {copy_btn}\n'
            f'</div>'
        )
        boxes.append(box)

    parts.append(f'<div class="{container_class}">\n' + "\n".join(boxes) + "\n</div>")
    return "\n".join(p for p in parts if p)


def render_example(slide: dict) -> str:
    """Example slide: labelled box, optional ai-output sub-region with accent.

    YAML schema:
      body:
        label       : str — header text for the labelled box
        label_color : str — "you" / "ai-green" / "ai-purple" / "ai-blue" (default: you)
        text        : str — direct body HTML (used when no `output` sub-region)
        copy        : str — copy-button payload for the direct-text path
        output:               — optional ai-output sub-region (if present, replaces text)
          accent : str — accent border color (default: green)
          text   : str — output body HTML (canonical; `body` accepted for back-compat)
          copy   : str — optional copy-button payload
    """
    parts = [_badge_html(slide.get("badge"))]
    if "heading" in slide:
        parts.append(f'<h2>{slide["heading"]}</h2>')

    body = slide.get("body", {})
    label = body.get("label", "")
    label_color = body.get("label_color", "you")  # "you" / "ai-green" / "ai-purple" / "ai-blue"
    output = body.get("output")
    direct_text = body.get("text")

    inner_parts = [f'<div class="label label-{label_color}">{html_lib.escape(label)}</div>']

    if output:
        accent = output.get("accent", "green")
        out_body = output.get("text") or output.get("body", "")
        copy_text = output.get("copy")
        copy_btn = _copy_btn_html(copy_text) if copy_text else ""
        inner_parts.append(
            f'<div class="ai-output border-{accent}">\n'
            f'  {out_body}\n'
            f'  {copy_btn}\n'
            f'</div>'
        )
    elif direct_text:
        inner_parts.append(direct_text)
        copy_text = body.get("copy")
        if copy_text:
            inner_parts.append(_copy_btn_html(copy_text))

    parts.append('<div class="example-box">\n' + "\n".join(inner_parts) + "\n</div>")
    return "\n".join(p for p in parts if p)


def render_iterations(slide: dict) -> str:
    """Iterations slide: numbered steps, each (num, finding, result)."""
    parts = [_badge_html(slide.get("badge"))]
    if "heading" in slide:
        parts.append(f'<h2>{slide["heading"]}</h2>')

    color = slide.get("color", "purple")
    reveal_per_step = slide.get("reveal") == "per-step-at-sentence"
    container_attr = ' data-reveal-children="1"' if reveal_per_step else ""

    box_inner = []
    for step in slide.get("steps", []):
        num = step.get("num", "")
        finding = step.get("finding", "")
        result = step.get("result", "")
        box_inner.append(
            f'<div class="iteration-step">\n'
            f'  <div class="iter-num highlight-{color}">{html_lib.escape(num)}</div>\n'
            f'  <div class="iter-finding">{finding}</div>\n'
            f'  <div class="iter-result">{result}</div>\n'
            f'</div>'
        )

    parts.append(
        f'<div class="example-box"{container_attr} style="padding: 1.2rem 1.8rem;">\n'
        + "\n".join(box_inner)
        + "\n</div>"
    )
    return "\n".join(p for p in parts if p)


def render_enumeration(slide: dict) -> str:
    """Enumeration slide: n-cell grid of (num, name, desc, optional example)."""
    parts = [_badge_html(slide.get("badge"))]
    if "heading" in slide:
        parts.append(f'<h2>{slide["heading"]}</h2>')
    if "intro" in slide:
        parts.append(
            f'<p style="font-size:0.9rem; color:rgba(255,255,255,0.4); '
            f'margin-top:-0.5rem; margin-bottom:0.8rem;">{slide["intro"]}</p>'
        )

    columns = slide.get("columns", 2)
    color = slide.get("color", "blue")
    grid_class = f"components-grid cols-{columns}" if columns != 2 else "components-grid"

    reveal_mode = (slide.get("reveal") or {}).get("mode") if isinstance(slide.get("reveal"), dict) else slide.get("reveal")
    reveal_per_item = reveal_mode in ("per-item-at-sentence", "per-item-at-sentence-plus-1", "at-sentence-indices")
    container_attr = ' data-reveal-children="1"' if reveal_per_item else ""

    items_html = []
    for item in slide.get("items", []):
        num = item.get("num", "")
        name = item.get("name", "")
        desc = item.get("desc", "")
        example = item.get("example", "")
        copy_text = item.get("copy")
        # If copy not specified but example is, default copy to the example text
        if copy_text is None and example:
            copy_text = example
        ex_html = ""
        if example:
            ex_color_class = f"color-{color}" if color != "blue" else ""
            ex_attr = ' data-reveal="1"' if reveal_per_item else ""
            # Without a reveal mode there is no event that would ever expand
            # the example (CSS hides it at opacity:0/max-height:0) — mark it
            # static so it renders visible. Shipped bug: the beginner video's
            # three retrospective prompts were permanently invisible.
            ex_static_class = "" if reveal_per_item else " static"
            ex_html = (
                f'  <div class="component-example {ex_color_class}{ex_static_class}"{ex_attr}>'
                f'{html_lib.escape(example)}</div>'
            )
        copy_btn = _copy_btn_html(copy_text) if copy_text else ""
        items_html.append(
            f'<div class="component-item">\n'
            f'  <span class="num highlight-{color}">{html_lib.escape(str(num))}</span>'
            f'<span class="name">{html_lib.escape(name)}</span>\n'
            f'  <div class="desc">{html_lib.escape(desc)}</div>\n'
            f'{ex_html}\n'
            f'{copy_btn}\n'
            f'</div>'
        )

    parts.append(f'<div class="{grid_class}"{container_attr}>\n' + "\n".join(items_html) + "\n</div>")
    return "\n".join(p for p in parts if p)


def render_recap(slide: dict) -> str:
    """Recap slide: ordered list with arrows."""
    parts = [_badge_html(slide.get("badge"))]
    if "heading" in slide:
        parts.append(f'<h2>{slide["heading"]}</h2>')

    arrows = slide.get("arrows", True)
    items = slide.get("items", [])
    list_inner = []
    for i, item in enumerate(items):
        strong = item.get("strong", "")
        color = item.get("color", "blue")
        body = item.get("body", "")
        list_inner.append(
            f'<p class="recap-item"><strong class="highlight-{color}">{html_lib.escape(strong)}</strong>'
            f' &mdash; {body}</p>'
        )
        if arrows and i < len(items) - 1:
            list_inner.append('<p class="arrow">&darr;</p>')

    parts.append('<div class="recap-list">\n' + "\n".join(list_inner) + "\n</div>")
    if "closing" in slide:
        parts.append(f'<p class="subtitle" style="margin-top:3rem;">{slide["closing"]}</p>')
    return "\n".join(p for p in parts if p)


def render_code(slide: dict) -> str:
    """Code slide: syntax-highlighted code block with optional copy-btn."""
    parts = [_badge_html(slide.get("badge"))]
    if "heading" in slide:
        parts.append(f'<h2>{slide["heading"]}</h2>')

    language = slide.get("language", "plaintext")
    code = slide.get("code", "")
    copy_enabled = slide.get("copy", False)

    code_block = (
        f'<div class="code-block">\n'
        f'<pre><code class="language-{language}">{html_lib.escape(code)}</code></pre>\n'
        f'{_copy_btn_html(code, label="Copy code") if copy_enabled else ""}\n'
        f'</div>'
    )
    parts.append(code_block)

    if "explanation" in slide:
        parts.append(f'<p class="subtitle" style="margin-top:1rem;">{slide["explanation"]}</p>')
    return "\n".join(p for p in parts if p)


def render_math(slide: dict) -> str:
    """Math slide: KaTeX-rendered formula with optional explanation."""
    parts = [_badge_html(slide.get("badge"))]
    if "heading" in slide:
        parts.append(f'<h2>{slide["heading"]}</h2>')

    formula = slide.get("formula", "")
    display = slide.get("display", True)
    if display:
        parts.append(f'<div class="math-display">$${formula}$$</div>')
    else:
        parts.append(f'<p class="math-display">${formula}$</p>')

    if "explanation" in slide:
        parts.append(f'<p class="math-explanation">{slide["explanation"]}</p>')
    return "\n".join(p for p in parts if p)


def render_diagram(slide: dict) -> str:
    """Diagram slide: Mermaid diagram or raw SVG."""
    parts = [_badge_html(slide.get("badge"))]
    if "heading" in slide:
        parts.append(f'<h2>{slide["heading"]}</h2>')

    if "mermaid" in slide:
        parts.append(
            f'<div class="diagram-container">\n'
            f'<div class="mermaid">\n{slide["mermaid"]}\n</div>\n'
            f'</div>'
        )
    elif "svg" in slide:
        parts.append(f'<div class="diagram-container">\n{slide["svg"]}\n</div>')

    return "\n".join(p for p in parts if p)


def render_table(slide: dict) -> str:
    """Table slide: column headers + rows."""
    parts = [_badge_html(slide.get("badge"))]
    if "heading" in slide:
        parts.append(f'<h2>{slide["heading"]}</h2>')

    columns = slide.get("columns", [])
    rows = slide.get("rows", [])
    head = "".join(f'<th>{html_lib.escape(str(c))}</th>' for c in columns)
    body_rows = []
    for row in rows:
        cells = "".join(f'<td>{html_lib.escape(str(c))}</td>' for c in row)
        body_rows.append(f'<tr>{cells}</tr>')

    parts.append(
        f'<table class="data-table">\n'
        f'<thead><tr>{head}</tr></thead>\n'
        f'<tbody>\n' + "\n".join(body_rows) + '\n</tbody>\n'
        f'</table>'
    )
    return "\n".join(p for p in parts if p)


def render_html_escape(slide: dict) -> str:
    """Escape hatch: raw HTML (v1 backward-compat)."""
    return slide.get("html", "")


LAYOUT_DISPATCH = {
    "title":       render_title,
    "hook":        render_hook,
    "compare":     render_compare,
    "example":     render_example,
    "iterations":  render_iterations,
    "enumeration": render_enumeration,
    "recap":       render_recap,
    "code":        render_code,
    "math":        render_math,
    "diagram":     render_diagram,
    "table":       render_table,
    "html":        render_html_escape,
}


def render_slide_inner(slide: dict, idx: int) -> str:
    """A slide's inner content (layout body + info button), no .slide wrapper.

    Separated from the wrapper so bilingual builds can swap a slide's
    innerHTML per language at runtime without touching the container
    (section gradient, data attrs, slide indexing all stay stable).
    """
    layout = slide.get("layout", "html")
    if layout not in LAYOUT_DISPATCH:
        raise SystemExit(f"Slide {idx+1}: unknown layout '{layout}'. "
                         f"Known: {', '.join(LAYOUT_DISPATCH.keys())}")
    body = LAYOUT_DISPATCH[layout](slide)
    info_btn = _info_btn_html(slide)
    return f'{body}\n{info_btn}'


def render_slide(slide: dict, idx: int) -> str:
    """Wrap a slide's layout output in the .slide container."""
    inner = render_slide_inner(slide, idx)

    section = slide.get("section", "default")
    section_attr = f' data-section="{html_lib.escape(section)}"'
    custom_color = slide.get("color")
    style_attr = ""
    if custom_color:
        style_attr = f' style="background: linear-gradient(135deg, #0a0a1a 0%, {custom_color} 100%);"'

    info_attr = ""
    if "info_panel" in slide:
        topic = slide["info_panel"].get("topic", "info")
        info_attr = f' data-info="{html_lib.escape(topic)}"'

    return (
        f'<div class="slide"{section_attr}{info_attr}{style_attr}>\n'
        f'{inner}\n'
        f'</div>'
    )


# ============================================================================
# Languages (v2.4 — bilingual/multilingual builds)
# ============================================================================

def parse_languages(spec: dict, top_voice: str) -> list[dict]:
    """Normalize the optional `languages:` block.

    Returns a list of {code, voice, ui} dicts; first entry is the default
    language (drives the MP4 + plain .mp3/.vtt filenames). Absent block →
    single pseudo-entry using the top-level voice, which keeps the legacy
    single-language path byte-identical.
    """
    raw = spec.get("languages")
    if not raw:
        return [{"code": None, "voice": top_voice, "ui": {}}]
    langs = []
    for entry in raw:
        code = entry.get("code")
        if not code:
            raise SystemExit("languages: every entry needs a `code` (e.g. en, de)")
        voice = entry.get("voice", top_voice)
        voice = VOICE_SHORTLIST.get(voice, voice)
        langs.append({"code": code, "voice": voice, "ui": entry.get("ui", {})})
    if len({l["code"] for l in langs}) != len(langs):
        raise SystemExit("languages: duplicate language codes")
    return langs


def resolve_lang(value, code: str, codes: set[str]):
    """Resolve per-language translation maps inside a YAML value.

    A dict whose keys are ALL language codes is a translation map — pick the
    requested language (falling back to the first declared code present).
    Any other dict/list recurses; scalars pass through. This lets authors
    localize any text field in place:  title: {en: "...", de: "..."}.
    """
    if isinstance(value, dict):
        keys = set(value.keys())
        if keys and keys <= codes:
            if code in value:
                return value[code]
            return next(iter(value.values()))
        return {k: resolve_lang(v, code, codes) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_lang(v, code, codes) for v in value]
    return value


# ============================================================================
# Reveal events
# ============================================================================

def build_slide_times(slides: list[dict], boundaries: list[float]) -> list[float]:
    """Slide i starts at boundary[sum-of-prior-sentence-counts]."""
    times: list[float] = []
    cursor = 0
    for s in slides:
        if cursor >= len(boundaries):
            times.append(boundaries[-1])
        else:
            times.append(boundaries[cursor])
        cursor += count_sentences(s.get("narration", ""))
    return times


def build_reveal_events(slides: list[dict], boundaries: list[float]) -> tuple[list[dict], list[dict]]:
    """For each slide with intra-slide reveal config, emit timed events.

    Returns (events, drops):
      - events: list of {slide_index, target_selector, at_seconds}
      - drops:  list of {slide_index, target_label, reason} for reveals
                that could not be scheduled because there was no boundary
                slot available (narration sentence count is too small for
                the configured reveal mode). DOM elements stay hidden in
                the rendered output.

    Reveal mode is set on the layout container (e.g. enumeration with
    reveal: per-item-at-sentence) — each item reveals at its own sentence
    boundary within the slide's narration.

    Boundary-tail rule (v2.1, see SKILL.md "Critical constraints on narration"):
      - per-step-at-sentence (iterations) needs N+1 sentences for N steps
        (sentence 1 = slide enter; sentences 2..N+1 = step reveals)
      - per-item-at-sentence (enumeration items) needs N+1 sentences
      - per-item-at-sentence-plus-1 (examples) needs 2N+1 sentences
        (sentence 1 = slide enter; 2..N+1 = items; 3..N+2 = examples)
      Drops are surfaced via the warning collected here, not via runtime
      error, so authors can iterate on narration without rebuild loops.
    """
    events = []
    drops: list[dict] = []
    sentence_cursor = 0  # global sentence index across all slides

    for idx, slide in enumerate(slides):
        slide_sentences = count_sentences(slide.get("narration", ""))

        # Iterations: per-step-at-sentence
        if slide.get("layout") == "iterations" and slide.get("reveal") == "per-step-at-sentence":
            for step_i, step in enumerate(slide.get("steps", [])):
                # step i reveals at sentence (cursor + step_i + 1) — first sentence is for slide enter
                target_sentence = sentence_cursor + step_i + 1
                if target_sentence < len(boundaries):
                    events.append({
                        "slide_index": idx,
                        "target_selector": f".iteration-step:nth-child({step_i + 1})",
                        "at_seconds": boundaries[target_sentence],
                    })
                else:
                    drops.append({
                        "slide_index": idx,
                        "target_label": f"step {step_i + 1} ({step.get('num', '?')})",
                        "reason": (
                            f"needs sentence #{target_sentence + 1} but "
                            f"only {len(boundaries)} boundaries available"
                        ),
                    })

        # Enumeration: per-item-at-sentence (and optional examples)
        elif slide.get("layout") == "enumeration":
            reveal_cfg = slide.get("reveal")
            if isinstance(reveal_cfg, str):
                mode_items = reveal_cfg
                mode_examples = None
            elif isinstance(reveal_cfg, dict):
                mode_items = reveal_cfg.get("mode")
                mode_examples = reveal_cfg.get("examples")
            else:
                mode_items = None
                mode_examples = None

            if mode_items == "at-sentence-indices":
                # v2.5: explicit slide-local sentence index per item, for
                # narration whose sentence structure is locked (e.g. migrating
                # an existing approved narration where each item spans several
                # sentences). Index 0 = the slide-enter sentence. Optional
                # examples_offset reveals each item's example N sentences
                # after its item.
                idxs = reveal_cfg.get("items") if isinstance(reveal_cfg, dict) else None
                ex_off = reveal_cfg.get("examples_offset") if isinstance(reveal_cfg, dict) else None
                items = slide.get("items", [])
                if not isinstance(idxs, list) or len(idxs) != len(items):
                    drops.append({
                        "slide_index": idx,
                        "target_label": "at-sentence-indices config",
                        "reason": f"needs one sentence index per item ({len(items)} items), got {idxs!r}",
                    })
                else:
                    for item_i, (item, off) in enumerate(zip(items, idxs)):
                        target_sentence = sentence_cursor + int(off)
                        if target_sentence < len(boundaries):
                            events.append({
                                "slide_index": idx,
                                "target_selector": f".component-item:nth-child({item_i + 1})",
                                "at_seconds": boundaries[target_sentence],
                            })
                        else:
                            drops.append({
                                "slide_index": idx,
                                "target_label": f"item {item_i + 1} ({item.get('name', '?')})",
                                "reason": (
                                    f"needs sentence #{target_sentence + 1} but "
                                    f"only {len(boundaries)} boundaries available"
                                ),
                            })
                        if ex_off is not None and item.get("example"):
                            ex_sentence = target_sentence + int(ex_off)
                            if ex_sentence < len(boundaries):
                                events.append({
                                    "slide_index": idx,
                                    "target_selector": f".component-item:nth-child({item_i + 1}) .component-example",
                                    "at_seconds": boundaries[ex_sentence],
                                })
                            else:
                                drops.append({
                                    "slide_index": idx,
                                    "target_label": f"example for item {item_i + 1} ({item.get('name', '?')})",
                                    "reason": (
                                        f"needs sentence #{ex_sentence + 1} but "
                                        f"only {len(boundaries)} boundaries available"
                                    ),
                                })
            elif mode_items in ("per-item-at-sentence", "per-item-at-sentence-plus-1"):
                items = slide.get("items", [])
                for item_i, item in enumerate(items):
                    target_sentence = sentence_cursor + item_i + 1
                    if target_sentence < len(boundaries):
                        events.append({
                            "slide_index": idx,
                            "target_selector": f".component-item:nth-child({item_i + 1})",
                            "at_seconds": boundaries[target_sentence],
                        })
                    else:
                        drops.append({
                            "slide_index": idx,
                            "target_label": f"item {item_i + 1} ({item.get('name', '?')})",
                            "reason": (
                                f"needs sentence #{target_sentence + 1} but "
                                f"only {len(boundaries)} boundaries available"
                            ),
                        })
                    # Examples: reveal at sentence + 1 if mode set
                    if mode_examples == "per-item-at-sentence-plus-1":
                        ex_sentence = target_sentence + 1
                        if ex_sentence < len(boundaries):
                            events.append({
                                "slide_index": idx,
                                "target_selector": f".component-item:nth-child({item_i + 1}) .component-example",
                                "at_seconds": boundaries[ex_sentence],
                            })
                        else:
                            drops.append({
                                "slide_index": idx,
                                "target_label": f"example for item {item_i + 1} ({item.get('name', '?')})",
                                "reason": (
                                    f"needs sentence #{ex_sentence + 1} but "
                                    f"only {len(boundaries)} boundaries available"
                                ),
                            })

        # Generic: any element with reveal_at: N (sentence index within slide)
        # Currently only structurally supported above; future layouts can register here.

        sentence_cursor += slide_sentences

    return events, drops


# ============================================================================
# Subtitle cues (v2.3 — accessibility / no-sound viewing)
# ============================================================================

def build_subtitle_cues(slides: list[dict], boundaries: list[float]) -> list[dict]:
    """Build sentence-by-sentence subtitle cues for HTML overlay rendering.

    Returns a list of {start, text} dicts, one per sentence, where start is
    the audio-time offset in seconds. The end of each cue is implicit — the
    overlay shows cue N until cue N+1 starts (or audio ends).

    Pulls sentences from each slide's narration in order, mapping them to
    edge-tts sentence boundaries. If local sentence count differs from
    boundary count, falls back to fewer cues with last-cue-extends behavior.
    """
    cues = []
    cursor = 0
    for slide in slides:
        narration = slide.get("narration", "").strip()
        if not narration:
            continue
        sentences = [s.strip() for s in SENT_SPLIT.split(narration) if s.strip()]
        for sent in sentences:
            if cursor < len(boundaries):
                cues.append({"start": boundaries[cursor], "text": sent})
                cursor += 1
            else:
                # Boundary array exhausted — append text to previous cue if any
                if cues:
                    cues[-1]["text"] = cues[-1]["text"] + " " + sent
    return cues


# ============================================================================
# Info panel data
# ============================================================================

def build_info_data(slides: list[dict]) -> dict:
    """Collect all info_panel HTML keyed by topic."""
    data = {}
    for slide in slides:
        panel = slide.get("info_panel")
        if not panel:
            continue
        topic = panel.get("topic", "info")
        html = panel.get("html", "")
        if topic in data:
            # Multiple slides can reference same topic; first wins, others ignored
            continue
        data[topic] = html
    return data


# ============================================================================
# HTML rendering
# ============================================================================

def render_html(template: str, *, title: str, audio_file: str,
                slides: list[dict], slide_times: list[float],
                reveal_events: list[dict], info_data: dict,
                subtitle_cues: list[dict], total_duration: float,
                langs_payload: dict | None = None,
                lang_code: str = "en") -> str:
    # v2.5: stamp the DEFAULT language on <html lang=...> — a German-default
    # page shipping lang="en" degrades screen readers/hyphenation until the
    # first JS language switch (KG audit finding, 2026-06-12).
    template = template.replace('<html lang="en">', f'<html lang="{lang_code}">', 1)
    blocks = [render_slide(s, i) for i, s in enumerate(slides)]
    slides_html = "\n\n".join(blocks)

    # Info panels are now embedded as data-only; the overlay div is in template
    info_panels_html = ""

    return (
        template
        .replace("{{TITLE}}", html_lib.escape(title))
        .replace("{{AUDIO_FILE}}", audio_file)
        .replace("{{SLIDES_HTML}}", slides_html)
        .replace("{{INFO_PANELS_HTML}}", info_panels_html)
        .replace("{{SLIDE_TIMES_JSON}}", json.dumps(slide_times))
        .replace("{{REVEAL_EVENTS_JSON}}", json.dumps(reveal_events))
        .replace("{{INFO_DATA_JSON}}", json.dumps(info_data))
        .replace("{{SUBTITLE_CUES_JSON}}", json.dumps(subtitle_cues))
        .replace("{{TOTAL_DURATION}}", f"{total_duration:.2f}")
        .replace("{{LANGS_JSON}}", json.dumps(langs_payload) if langs_payload else "null")
    )


# ============================================================================
# Captures + mux
# ============================================================================

async def capture(html_path: Path, duration: float, work_dir: Path,
                  width: int, height: int) -> Path:
    from playwright.async_api import async_playwright

    video_dir = work_dir / "capture"
    video_dir.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--autoplay-policy=no-user-gesture-required",
                "--mute-audio",
            ],
        )
        context = await browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=str(video_dir),
            record_video_size={"width": width, "height": height},
        )
        page = await context.new_page()
        url = html_path.absolute().as_uri() + "?capture=1"
        await page.goto(url)
        # v2.5: the page shows a magenta sync marker until ready, then starts
        # the timeline and sets __captureStarted. Waiting on the flag keeps the
        # full deck inside the recording even on slow CDN/page-load days.
        try:
            await page.wait_for_function("window.__captureStarted === true",
                                         timeout=120_000)
        except Exception:
            print("       WARN: capture-start flag never fired; "
                  "recording may have unsynced head")
        await page.wait_for_timeout(int((duration + 1.5) * 1000))
        await context.close()
        await browser.close()

    videos = sorted(video_dir.glob("*.webm"))
    if not videos:
        raise RuntimeError("Playwright recorded no video")
    return videos[-1]


def detect_sync_trim(video_webm: Path, work_dir: Path, window_s: float = 60.0,
                     fps: int = 10) -> float:
    """Find the end of the magenta sync-marker head; return trim offset (s).

    Returns 0.0 when no marker is found (template without marker, or marker
    gone before the first sampled frame).
    """
    try:
        from PIL import Image
    except ImportError:
        print("       WARN: Pillow not available — skipping sync trim")
        return 0.0
    probe_dir = work_dir / "syncprobe"
    probe_dir.mkdir(exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-t", str(window_s), "-i", str(video_webm),
         "-vf", f"fps={fps},scale=64:36", "-y",
         str(probe_dir / "f%05d.png")],
        check=True)
    last_magenta = -1
    frames = sorted(probe_dir.glob("f*.png"))
    for i, fp in enumerate(frames):
        img = Image.open(fp).convert("RGB").resize((8, 5))
        px = list(img.getdata())
        n_mag = sum(1 for r, g, b in px if r > 180 and b > 180 and g < 90)
        if n_mag >= len(px) * 0.9:
            last_magenta = i
    for fp in frames:
        fp.unlink()
    if last_magenta < 0:
        return 0.0
    return (last_magenta + 1) / fps


def mux(video_webm: Path, audio_mp3: Path, out_mp4: Path, vtt_path: Path | None = None,
        video_trim: float = 0.0) -> None:
    cmd = ["ffmpeg", "-y"]
    if video_trim > 0:
        cmd += ["-ss", f"{video_trim:.3f}"]
    cmd += ["-i", str(video_webm), "-i", str(audio_mp3)]
    if vtt_path is not None:
        cmd += ["-i", str(vtt_path)]
    cmd += ["-map", "0:v:0", "-map", "1:a:0"]
    if vtt_path is not None:
        cmd += ["-map", "2:s:0"]
    cmd += [
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
    ]
    if vtt_path is not None:
        cmd += ["-c:s", "mov_text", "-metadata:s:s:0", "language=eng"]
    cmd += ["-shortest", str(out_mp4)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise RuntimeError(f"ffmpeg failed (exit {result.returncode})")


# ============================================================================
# Captions (VTT)
# ============================================================================

def build_vtt(slides: list[dict], boundaries: list[float], total_duration: float) -> str:
    """Emit a basic VTT file: one cue per sentence, using sentence-boundary timestamps."""
    cues = ["WEBVTT", ""]
    cursor = 0
    for slide in slides:
        sentences = [s.strip() for s in SENT_SPLIT.split(slide.get("narration", "").strip()) if s.strip()]
        for sent in sentences:
            start = boundaries[cursor] if cursor < len(boundaries) else total_duration
            end = boundaries[cursor + 1] if cursor + 1 < len(boundaries) else total_duration
            cues.append(f"{_vtt_time(start)} --> {_vtt_time(end)}")
            cues.append(sent)
            cues.append("")
            cursor += 1
    return "\n".join(cues)


def _vtt_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


# ============================================================================
# Main
# ============================================================================

async def amain(args: argparse.Namespace) -> None:
    spec_path = Path(args.input).resolve()
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))

    title = spec.get("title", "Presentation")
    voice_raw = args.voice or spec.get("voice", "en-US-AriaNeural")
    voice = VOICE_SHORTLIST.get(voice_raw, voice_raw)  # resolve shortlist key if used

    output_cfg = spec.get("output", {})
    width = args.width or output_cfg.get("width", 1920)
    height = args.height or output_cfg.get("height", 1080)

    slides = spec.get("slides") or []
    if not slides:
        raise SystemExit("No slides in YAML")

    # Languages (v2.4): optional `languages:` block → one render+TTS pass per
    # language, single HTML with a runtime language toggle. Absent → legacy
    # single-language path, byte-identical output.
    languages = parse_languages(spec, voice)
    codes = {l["code"] for l in languages if l["code"]}
    multilang = len(languages) > 1

    per_lang: list[dict] = []
    for lang_entry in languages:
        code = lang_entry["code"]
        l_slides = [resolve_lang(s, code, codes) for s in slides] if codes else slides
        for i, s in enumerate(l_slides):
            narr = s.get("narration", "")
            if not isinstance(narr, str) or not narr.strip():
                where = f" [{code}]" if code else ""
                raise SystemExit(f"Slide {i+1}{where} has empty narration "
                                 "(for bilingual builds: narration: {en: ..., de: ...})")
            layout = s.get("layout", "html")
            if layout == "html" and not s.get("html", "").strip():
                raise SystemExit(f"Slide {i+1} has layout=html but empty html field")
        per_lang.append({**lang_entry, "slides": l_slides})

    if args.work_dir:
        work = Path(args.work_dir).resolve()
        work.mkdir(parents=True, exist_ok=True)
        keep_work = True
    else:
        work = Path(tempfile.mkdtemp(prefix="slidevid-"))
        keep_work = False
    print(f"[work] {work}")

    print(f"[1/4] edge-tts -> voiceover mp3" + (" (per language)" if multilang else f" ({per_lang[0]['voice']})"))
    for L in per_lang:
        code = L["code"]
        is_default = L is per_lang[0]
        # Default language keeps the unsuffixed name (legacy-identical);
        # additional languages get voiceover.<code>.mp3.
        suffix = "" if (is_default or not code) else f".{code}"
        L["suffix"] = suffix
        L["audio_name"] = f"voiceover{suffix}.mp3"
        L["mp3"] = work / L["audio_name"]
        full_narration = " ".join(s["narration"].strip() for s in L["slides"])
        boundaries = await run_tts(full_narration, L["voice"], L["mp3"])
        L["boundaries"] = boundaries
        L["duration"] = MP3(L["mp3"]).info.length
        label = f"[{code}] " if code else ""
        print(f"       {label}{len(boundaries)} sentence boundaries, {L['duration']:.2f}s audio ({L['voice']})")

        expected_sentences = sum(count_sentences(s["narration"]) for s in L["slides"])
        if expected_sentences != len(boundaries):
            print(
                f"       NOTE: {label}narration split into {expected_sentences} sentences locally "
                f"but edge-tts emitted {len(boundaries)} boundaries. "
                "Slide times may drift. Per-slide diagnostic:"
            )
            for i, s in enumerate(L["slides"]):
                n_local = count_sentences(s["narration"])
                pitfalls = detect_splitter_pitfalls(s["narration"])
                if pitfalls:
                    preview = s["narration"].strip().splitlines()[0][:60]
                    print(f"         slide {i+1}: {n_local} local sentences, "
                          f"trips: {'; '.join(pitfalls)}")
                    print(f"           narration: \"{preview}{'...' if len(s['narration']) > 60 else ''}\"")

        L["slide_times"] = build_slide_times(L["slides"], boundaries)
        L["reveal_events"], reveal_drops = build_reveal_events(L["slides"], boundaries)
        L["info_data"] = build_info_data(L["slides"])
        L["subtitle_cues"] = build_subtitle_cues(L["slides"], boundaries)

        if reveal_drops:
            print(
                f"       WARNING: {label}{len(reveal_drops)} reveal events could not be scheduled "
                f"(narration too short for configured reveal mode). Affected reveals stay "
                f"hidden in the rendered output:"
            )
            for d in reveal_drops:
                print(f"         slide {d['slide_index'] + 1}: {d['target_label']} — {d['reason']}")

    default = per_lang[0]
    mp3_path = default["mp3"]
    duration = default["duration"]
    slide_times = default["slide_times"]
    reveal_events = default["reveal_events"]

    (work / "boundaries.json").write_text(
        json.dumps({
            "boundaries": default["boundaries"],
            "slide_times": slide_times,
            "reveal_events": reveal_events,
            "languages": {
                (L["code"] or "default"): {
                    "boundaries": L["boundaries"],
                    "slide_times": L["slide_times"],
                } for L in per_lang
            } if multilang else None,
        }, indent=2),
        encoding="utf-8",
    )
    print(f"[2/4] slide times: {['%.1f' % t for t in slide_times]}")
    if reveal_events:
        print(f"       {len(reveal_events)} intra-slide reveal events")

    langs_payload = None
    if multilang:
        langs_payload = {
            "default": default["code"],
            "order": [L["code"] for L in per_lang],
            "langs": {
                L["code"]: {
                    "audio": L["audio_name"],
                    "slideTimes": L["slide_times"],
                    "totalDuration": L["duration"],
                    "revealEvents": L["reveal_events"],
                    "infoData": L["info_data"],
                    "subtitleCues": L["subtitle_cues"],
                    "slides": [render_slide_inner(s, i) for i, s in enumerate(L["slides"])],
                    "ui": L["ui"],
                } for L in per_lang
            },
        }

    title_resolved = resolve_lang(title, default["code"], codes) if codes else title
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = render_html(
        template,
        title=title_resolved,
        audio_file=default["audio_name"],
        slides=default["slides"],
        slide_times=slide_times,
        reveal_events=reveal_events,
        info_data=default["info_data"],
        subtitle_cues=default["subtitle_cues"],
        total_duration=duration,
        langs_payload=langs_payload,
        lang_code=default["code"] or "en",
    )
    html_path = work / "presentation.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"       html -> {html_path}")

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # --embed-captions implies --captions (need the .vtt to mux it)
    if args.embed_captions:
        args.captions = True

    vtt_path: Path | None = None
    if args.captions:
        # One .vtt per language; default language keeps the plain name
        # (and is the track muxed by --embed-captions).
        for L in per_lang:
            vtt_l = out_path.parent / (out_path.stem + L["suffix"] + ".vtt")
            vtt_l.write_text(build_vtt(L["slides"], L["boundaries"], L["duration"]), encoding="utf-8")
            print(f"       captions -> {vtt_l}")
        vtt_path = out_path.parent / (out_path.stem + ".vtt")

    def _copy_out_audio(html_text: str) -> tuple[str, list[Path]]:
        # Copy each language's mp3 next to the output and rewrite every
        # reference (the <audio src> AND the LANGS payload) to the new names.
        outs = []
        for L in per_lang:
            dst = out_path.parent / (out_path.stem + L["suffix"] + ".mp3")
            shutil.copy(L["mp3"], dst)
            html_text = html_text.replace(L["audio_name"], quote(dst.name))
            outs.append(dst)
        return html_text, outs

    if args.html_only:
        # Copy HTML + audio to output location (sibling files).
        out_html = out_path.with_suffix(".html")
        html_text = html_path.read_text(encoding="utf-8")
        html_text, audio_outs = _copy_out_audio(html_text)
        if args.inline_deps:
            print(f"       inlining CDN dependencies (cache: {CDN_CACHE_DIR})")
            html_text = inline_cdn_deps(html_text)
        out_html.write_text(html_text, encoding="utf-8")
        size_kb = out_html.stat().st_size // 1024
        audio_desc = " + ".join(a.name for a in audio_outs)
        print(f"\nOK (html-only): {out_html} ({size_kb} KB) + {audio_desc} ({duration:.1f}s, {len(slides)} slides)")
        if keep_work:
            print(f"     intermediates: {work}")
        return

    print(f"[3/4] capture ({width}x{height}, headless)")
    video_webm = await capture(html_path, duration, work, width, height)
    print(f"       webm -> {video_webm} ({video_webm.stat().st_size // 1024} KB)")

    trim = detect_sync_trim(video_webm, work)
    if trim > 0:
        print(f"       sync-marker head: {trim:.2f}s -> trimming video to align with audio")

    print(f"[4/4] mux -> {out_path}")
    mux(video_webm, mp3_path, out_path, vtt_path=vtt_path if args.embed_captions else None,
        video_trim=trim)

    # Also drop the standalone HTML + MP3(s) alongside the MP4 (multi-mode delivery).
    out_html = out_path.with_suffix(".html")
    html_text = html_path.read_text(encoding="utf-8")
    html_text, audio_outs = _copy_out_audio(html_text)
    if args.inline_deps:
        print(f"    inlining CDN dependencies (cache: {CDN_CACHE_DIR})")
        html_text = inline_cdn_deps(html_text)
    out_html.write_text(html_text, encoding="utf-8")

    print(f"\nOK: {out_path} ({duration:.1f}s, {len(slides)} slides"
          + (f", MP4 narration = {default['code']}" if multilang else "") + ")")
    print(f"    + {out_html}  (interactive HTML"
          + (f", languages: {', '.join(L['code'] for L in per_lang)}" if multilang else "") + ")")
    for a in audio_outs:
        print(f"    + {a}  (audio standalone)")
    if keep_work:
        print(f"    intermediates: {work}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a narrated slide video from YAML.")
    ap.add_argument("input", help="YAML script file")
    ap.add_argument("--output", "-o", default="video.mp4", help="Output MP4 path")
    ap.add_argument("--work-dir", default=None,
                    help="Directory for intermediates (default: temp, deleted)")
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--height", type=int, default=None)
    ap.add_argument("--voice", default=None,
                    help="Override voice (raw edge-tts name OR shortlist key: "
                         + ", ".join(VOICE_SHORTLIST.keys()) + ")")
    ap.add_argument("--html-only", action="store_true",
                    help="Skip Playwright capture + ffmpeg mux; emit HTML + MP3 only")
    ap.add_argument("--captions", action="store_true",
                    help="Also emit a .vtt captions file alongside output")
    ap.add_argument("--embed-captions", action="store_true",
                    help="Embed captions as a soft-sub track in MP4 (mov_text codec). "
                         "Single-file delivery, captions still toggleable in VLC/etc. "
                         "Implies --captions.")
    ap.add_argument("--inline-deps", action="store_true",
                    help="Inline CDN dependencies (GSAP, KaTeX, Mermaid, highlight.js) into the "
                         "output HTML for offline distribution. Adds ~1.5MB to HTML size; cached "
                         "in resources/cdn-cache/ after first fetch. Closes Run #22 C5-r finding.")
    args = ap.parse_args()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
