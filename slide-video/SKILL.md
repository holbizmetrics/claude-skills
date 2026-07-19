---
name: slide-video
description: Build a narrated explainer video (MP4 + interactive HTML) from a topic, script, or outline. Use when the user asks for a slide video, explainer video, narrated presentation, video walkthrough, or wants to produce a voiceover-driven slideshow. Pipeline is edge-tts (free neural TTS with sentence boundaries) → GSAP-animated HTML → headless Playwright capture → ffmpeg mux. Claude authors the YAML; the skill runs the mechanics.
---

# slide-video — automated narrated explainer video (v2)

## When to invoke

Trigger on requests like:
- "Make me an explainer video about X"
- "Build a narrated presentation on Y"
- "Slide video", "voiceover walkthrough", "video about Z"
- "Like my prompting concepts video but for ..."

Do NOT invoke for: slide decks without narration (use a regular HTML template), live-demo videos (needs screen recording of a running app), or cases where the user just wants a script without video output.

## What it produces

A **bundle**:
- `out.mp4` — H.264/AAC video, 1920×1080 @ 30fps default, slides + voiceover muxed. With `--embed-captions`, also carries a `mov_text` soft-sub track (toggleable in VLC and most players).
- `out.html` — interactive standalone HTML with: Play/Pause toggle, Space-key play/pause anytime, ← → arrow keys to scrub slide AND audio, click-to-advance (left third = back, rest = forward), Fullscreen button, CC captions toggle, Sound/Mute, Slide-map dropdown for jump-to navigation, copy buttons with bracket-placeholder hints, info-panels for depth-on-demand, end-of-deck Restart overlay.
- `out.mp3` — audio standalone
- `out.vtt` — captions sidecar (optional, with `--captions`)

The HTML is **authoring-canonical**. The MP4 is a passive linearization. All interactivity lives in HTML and is hidden during capture (`body.capturing` class) so MP4 frames are clean.

## Workflow

### Step 1 — Author the YAML script

Given a topic or raw script, write a `script.yaml` file. The schema is **layout-driven**: each slide picks one of the named layouts below.

**Always show the user the draft YAML and get approval before running build.** YAML round-trip is cheap; a 5-minute render on a bad script is not.

#### Minimum slide

```yaml
title: "Your video title"
voice: conversational             # shortlist key, OR raw edge-tts name like "en-US-AriaNeural"
slides:
  - layout: title
    badge: { text: "PREMISE", color: green }
    title: "Three Ideas About <span class='highlight-green'>Attention</span>"
    subtitle: "Small shifts that change how you work."
    narration: "Let me tell you about three ideas. Each one pays for itself the first time you use it."
```

#### All available layouts

| Layout | Shape | Required fields | Optional |
|---|---|---|---|
| `title` | badge + h1 + subtitle + author | `title` | `badge`, `subtitle`, `author` |
| `hook` | h2 + subtitle | `heading` | `subtitle` |
| `compare` | 2 boxes labelled, optional column-stack | `bad`+`good` (red/green tone) OR `left`+`right` (neutral blue/orange); each pair-side needs `label` + `text` | `badge`, `heading`, `direction` (row/column); per-side `copy` |
| `example` | labelled box with optional ai-output sub-region | `body.label` + (`body.text` OR `body.output`) | `badge`, `heading`, `body.label_color`, `body.copy`, `body.output.{accent,text,copy}` |
| `iterations` | numbered steps each (num, finding, result) | `steps[]` | `badge`, `heading`, `color`, `reveal` |
| `enumeration` | n-cell grid each (num, name, desc, example, optional copy) | `items[]` | `badge`, `heading`, `intro` (raw HTML), `columns`, `color`, `reveal`; per-item `copy` slot auto-defaults to `example` text |
| `recap` | ordered items with optional arrow connectors | `items[]`, each `{strong, body, color}` | `badge`, `heading`, `arrows`, `closing` |
| `code` | syntax-highlighted code block | `code`, `language` | `badge`, `heading`, `copy`, `explanation` |
| `math` | KaTeX-rendered formula | `formula` | `badge`, `heading`, `display`, `explanation` |
| `diagram` | Mermaid diagram or raw SVG | `mermaid` OR `svg` | `badge`, `heading` |
| `table` | column headers + rows | `columns`, `rows` | `badge`, `heading` |
| `html` | raw HTML escape-hatch (v1 backward-compat) | `html` | — |

#### Universal slide fields

These apply to any layout:
- `narration`: required. Grammatical sentences ending in `.`, `!`, or `?`. Each becomes a sync boundary. **The first sentence of a slide's narration is the moment the slide appears.** Later sentences in the same slide continue on that slide and can drive intra-slide reveals (see below).
- `section`: optional. Controls background gradient. Built-in section names: `intro`, `meta`, `iterations`, `structure`, `closing`, `tech`, `theory`, `arch`. Any other value (or omitted) falls back to the default gradient.
- `color`: optional. Two uses depending on layout:
  - **Slide-level inline gradient override**: a hex string like `#1e3a2f` applied as the slide background.
  - **Layout accent color** (in `iterations`, `enumeration`, `recap` items): one of `green`, `purple`, `blue`, `orange`, `red` — applied to numbers, badges, accents inside that layout. Used for color-as-semantic-anchor (one color per concept).
- `info_panel`: optional. Adds an `i` button bottom-left of the slide; clicking opens a side drawer with deep-dive HTML. **HTML-mode only — visible-but-inert in MP4.** YAML shape:
  ```yaml
  info_panel:
    topic: iterations           # internal key (any string)
    html: |
      <h3>Iterations — deeper</h3>
      <p><strong>What it is:</strong> ...</p>
      <p><strong>When to use:</strong> ...</p>
  ```

#### Cross-cutting affordances

- **Copy buttons**: layouts that display code/text examples accept `copy: "..."` (string copied to clipboard) or `copy: true` (auto-copies the displayed code, in `code` layout). Enumeration items also accept `copy:` per-item; auto-defaults to the item's `example` text if not specified. Implementation uses textarea + `execCommand('copy')` first (works on file:// origins), falls back to `navigator.clipboard.writeText`. If the copy text contains `[bracketed placeholders]`, a small italic hint "Replace [bracketed parts] before sending." renders next to the button — discoverability for HTML-only viewers who don't have the audio narration's bracket-convention explainer.
- **Color as semantic anchor**: most layouts accept a `color: green|purple|blue|orange|red` field controlling badge/highlight/accent color for the slide. Pick a color per concept and use it consistently across that concept's slides.
- **Intra-slide micro-reveals**: `iterations` and `enumeration` layouts support per-step / per-item reveal pinned to sentence boundaries — items appear one-by-one as narration mentions them, mapped automatically (no manual wall-clock tuning). YAML shape:
  ```yaml
  # iterations layout — each step appears at its own sentence boundary
  - layout: iterations
    reveal: per-step-at-sentence    # string form
    steps:
      - { num: "Iteration 1", finding: "...", result: "..." }
      - { num: "Iteration 3", finding: "...", result: "..." }
    narration: |
      Slide-enter sentence.
      First step appears here.
      Second step appears here.
  ```
  ```yaml
  # enumeration layout — items + optional examples reveal independently
  - layout: enumeration
    reveal:
      mode: per-item-at-sentence
      examples: per-item-at-sentence-plus-1   # examples lag items by one sentence
    items:
      - { num: 1, name: Role, desc: "Who?", example: "..." }
      - { num: 2, name: Task, desc: "What?", example: "..." }
    narration: "..."
  ```
  ```yaml
  # enumeration layout — explicit sentence indices (v2.5), for narration whose
  # sentence structure is LOCKED (e.g. migrating an approved narration where
  # each item spans several sentences). Index 0 = the slide-enter sentence.
  - layout: enumeration
    reveal:
      mode: at-sentence-indices
      items: [0, 5, 10, 15, 19, 23]   # slide-local sentence index per item (one per item, required)
      examples_offset: 2              # optional: each example reveals N sentences after its item
    items: [ ... six items ... ]
    narration: |
      The six are: One. Role. ... (5 sentences) Two. Task. ... (5 sentences) ...
  ```
  Use `per-item-at-sentence` when you author narration fresh (one sentence per
  item); use `at-sentence-indices` when the narration is fixed and you map the
  reveals onto its existing sentence grid. The index lists may be localized
  (`items: {en: [...], de: [...]}`) but usually translate 1:1.

#### Critical constraints on `narration`

- Must be grammatical sentences ending in `.`, `!`, or `?`. edge-tts splits on these to emit boundaries.
- The FIRST sentence of a slide's narration is the moment the slide appears. Later sentences in the same slide continue on that slide.
- Avoid abbreviations with periods (`e.g.`, `i.e.`, `Dr.`, `etc.`) — they trip the sentence splitter. Rewrite as `for example`, `that is`, `Doctor`, `and so on`. German narration has its own trap set: `z. B.`, `d. h.`, `bzw.`, `usw.`, `ca.` — write them out (`zum Beispiel`, `das heißt`, `beziehungsweise`, `und so weiter`, `etwa`).
- Empty `narration` breaks the sync. Every slide must have at least one sentence.

#### Bilingual / multilingual builds (v2.4)

Add a `languages:` block and any text field becomes localizable in place:

```yaml
languages:
  - code: en
    voice: multilingual-male          # first entry = default language (drives the MP4)
  - code: de
    voice: multilingual-male          # same voice key → same speaker identity in both tracks
    ui: { play: "&#9654; Mit Ton abspielen", resume: "&#9654; Weiter", copied: "Kopiert!" }

slides:
  - layout: title
    title:     { en: "Two Tips", de: "Zwei Tipps" }     # any text field: plain string OR {code: ...} map
    narration: { en: "Two quick tips.", de: "Zwei schnelle Tipps." }
```

What you get: ONE interactive HTML with a language button (top-right row) that switches **on-screen text and narration audio together** — mid-video, the new track jumps to the start of the current slide so text and voice stay in lockstep. One TTS pass runs per language, so every language gets its own exact `slideTimes` (no scaling guesswork). Outputs: `out.mp3` (default language), `out.<code>.mp3` per extra language, per-language `.vtt` with `--captions`. The MP4 carries the default language's narration only — render a second MP4 by reordering `languages:` if you need both.

Rules of thumb learned from the first bilingual conversion (a two-video production series, 2026-06-11):
- Plain strings are shared across languages — right for code blocks, formulas, proper names; wrong for anything a viewer reads.
- **German narration runs ~25% longer than English** for the same script (736s vs 591s on a 16-slide deck). Budget total runtime against the LONGEST language, and trim the German text first if you're over.
- Keep technique names untranslated when they function as vocabulary the viewer will meet elsewhere (Discovery/Execution, Meta-Prompting) — translate the explanation, not the term.
- Voice: a multilingual voice (`multilingual-male` = en-US-AndrewMultilingualNeural) keeps the same speaker across languages; native voices (`german-male`/`german-female`) have the more idiomatic accent. The agent cannot audition audio — generate a one-sentence sample in each candidate voice and let the operator's ear decide before committing a full build.

#### Authoring principles (the cognitive part of the job)

- Open with a hook, not a table of contents.
- One idea per slide. If you wrote two, split them.
- Speak numbers before you bullet them ("Three things:"). The voice carries continuity; the HTML holds the bullets.
- Read the script aloud before shipping. If it sounds like paper, rewrite it.
- Close with one action the viewer can do in sixty seconds.
- Concept selection is yours, not the skill's. If your topic is **prompting**, the bundled `resources/prompt-concepts.html` is starting material — pick concepts from it, don't copy a previous curriculum verbatim.

#### Scaffolds (recipes, not frames)

The original "3 Prompting Concepts" video used these recurring shapes. They're **starting templates**, not enforced structures — feel free to deviate.

**Per-concept template (3 slides each):**
```
title (concept name) → "what you say" (compare layout, bad vs good) → "what AI returns" (example layout, ai-output)
```

**Deck arc (~14 slides for 3 concepts):**
```
intro hook (2) → concept 1 (3) → concept 2 (3) → concept 3 (4) → recap (1) → CTA (1)
```

**Use these when they fit. Skip or invert them when they don't.** A chain-of-thought video might want `title → naive → CoT → comparison`. A RAG video might want `problem → architecture → code → tuning`. The skill expresses your structure; it doesn't impose one.

### Step 2 — Run the build

```bash
python build.py path/to/script.yaml --output out.mp4
```

Optional flags:
- `--work-dir <path>` — keep intermediates (default: auto temp dir, deleted)
- `--width 1920 --height 1080` — output resolution (defaults shown)
- `--voice <key-or-name>` — override voice from YAML
- `--html-only` — skip Playwright capture + ffmpeg; emit HTML + MP3 only (fast iteration)
- `--captions` — also emit a `.vtt` captions file alongside the MP4
- `--embed-captions` — embed captions as a `mov_text` soft-sub track inside the MP4 for single-file delivery; captions remain toggleable in VLC/most players. Implies `--captions`.
- `--inline-deps` — inline CDN dependencies (GSAP, KaTeX, Mermaid, highlight.js) into the output HTML for offline distribution. Adds ~1.5MB; cached after first fetch.

The full pipeline (HTML + MP4 + MP3) takes ~1 second of render per 1 second of final video. `--html-only` finishes in seconds.

### Step 3 — Hand off

Report output paths + duration + slide count. If the user wants edits: modify YAML, rerun. The TTS round-trip is a few seconds; the slow part is Playwright recording (which `--html-only` skips entirely during iteration).

## Voice options

edge-tts is free and needs no API key (streams from Microsoft Edge's TTS endpoint).

**Curated shortlist** (use these keys in YAML or `--voice`):

| Key | Voice | Register |
|---|---|---|
| `conversational` | en-US-AriaNeural | warm, conversational, female (default) |
| `formal` | en-US-GuyNeural | professional, male |
| `friendly` | en-US-JennyNeural | friendly-energetic, female |
| `calm` | en-US-DavisNeural | calm-instructional, male |
| `neutral` | en-US-EmmaNeural | neutral-clear, female |
| `british-female` | en-GB-SoniaNeural | British, female |
| `british-male` | en-GB-RyanNeural | British, male |
| `german-female` | de-DE-KatjaNeural | German, female (native accent) |
| `german-male` | de-DE-ConradNeural | German, male (native accent) |
| `multilingual-male` | en-US-AndrewMultilingualNeural | speaks EN+DE+more; same speaker across languages |
| `multilingual-female` | en-US-AvaMultilingualNeural | speaks EN+DE+more; same speaker across languages |
| `german-multilingual-male` | de-DE-FlorianMultilingualNeural | German-rooted multilingual, male |
| `german-multilingual-female` | de-DE-SeraphinaMultilingualNeural | German-rooted multilingual, female |

For other voices, pass the raw edge-tts voice name (e.g. `en-US-AvaNeural`). Full list: `edge-tts --list-voices`.

**Multilingual vs native for bilingual builds:** multilingual voices keep one speaker identity across both audio tracks (the video "sounds like the same person" in EN and DE); native voices win on accent quality. Quality is an ear-call the agent can't make — synthesize a one-sentence sample per candidate and have the operator pick before running the full build.

## Install (one-time, Windows)

```bash
pip install -r requirements.txt
playwright install chromium
```

ffmpeg must be in PATH. On Windows: `winget install Gyan.FFmpeg` or `scoop install ffmpeg`.

## Caveats

- edge-tts requires internet (streams from Microsoft Edge's TTS service).
- Playwright runs headless with audio muted; we record silent video and mux the TTS mp3 afterward. Audio is always present in the output — it does not depend on the browser playing it during capture.
- Slide transitions in capture mode are wall-clock driven (`performance.now()`); in interactive HTML mode they're audio-driven (`<audio>.timeupdate`). Same `slideTimes[]` array, two clock sources.
- If a slide has more narration sentences than expected, later sentences stay on the same slide. For multi-sentence reveals on one slide, use `reveal: per-step-at-sentence` (iterations) or `reveal: per-item-at-sentence` (enumeration) so visuals reveal alongside narration.
- `info_panel` and `copy` buttons are HTML-only — they appear visible-but-inert in the MP4 (no clicks during headless capture). That's expected and correct.

## Examples shipped

- `examples/example.yaml` — minimum example, html-escape-hatch (carries over from v1).
- `examples/rag-explainer.yaml` — RAG explainer using `code`, `diagram`, `math` extension primitives. Validates the skill on a non-prompting topic.
- `examples/scaffold-deviation.yaml` — deliberately deviates from the canonical scaffold (different deck arc + per-concept shape) to demonstrate that scaffolds are recipes, not frames.
- `examples/info-panels-and-reveals.yaml` — exercises `info_panel` deep-dive drawers + `reveal: per-step-at-sentence` + `reveal: per-item-at-sentence` together. Use as the reference for those v2-specific features.
- `examples/bilingual-en-de.yaml` — exercises the v2.4 `languages:` block: per-field `{en:, de:}` translation maps, per-language `ui:` labels, shared-voice multilingual TTS. Use as the reference for bilingual builds.

## Resources

- `resources/prompt-concepts.html` — bundled prompting-concepts reference (10 concepts) for use as starting material if your topic is prompting. **Pick concepts from here, don't copy the original curriculum verbatim.** Concept selection is yours.

## Origin

Reverse-engineered from a hand-built "3 Prompting Concepts" presentation. The sync mechanism is edge-tts's `SentenceBoundary` events — the TTS engine emits exact sentence-start timestamps as it renders, and those become the `slideTimes[]` array baked into the HTML. No audio analysis, no alignment algorithms — the right tool does it for free.

v2 generalizes the v1 abstraction: ports the load-bearing primitives that were in the original artifact (compare, iterations, enumeration, copy-btn, info-panel) and adds extension primitives (code, math, diagram, table) for technical-explainer content.

v2.4 (2026-06-11) adds bilingual builds (`languages:` block — one HTML, runtime EN/DE toggle that switches text and audio together; pattern proven by hand-converting the two series-1 videos first) and fixes two shipped-output bugs found in that conversion: copy-button `onclick` quoting (json.dumps double quotes terminated the double-quoted attribute — every copy button dead in affected outputs) and enumeration examples without a `reveal:` mode being permanently invisible (CSS hid them at opacity 0 with no event to ever show them). If you have older rendered HTML outputs in circulation, both bugs are worth a rebuild.

v2.5 (2026-06-12) adds the `at-sentence-indices` reveal mode (enumeration): explicit slide-local sentence index per item + optional `examples_offset`, for migrating locked/approved narrations whose items span multiple sentences each. Added while regenerating series-1 videos 1+2 through the generator (series-interface unification) — the hand-built slide-10 reveal could not be expressed by the one-sentence-per-item modes.

The skill is model-agnostic: any Claude (or other authoring model) writes the YAML; `build.py` does the mechanics. Nothing in the pipeline depends on a specific model.

See `DESIGN.md` for architectural decisions, render set, primitive vocabulary, scaffolds-as-recipes, and exit criteria.
