# slide-video.skill — design (v2)

Public-facing design contract. Architectural decisions, render set, primitive vocabulary, scaffolds, exit criteria. Read alongside `SKILL.md` (which is the authoring contract).

## v2.4–v2.7 addendum (2026-05-08/09)

This block summarizes additions since the original v2 design. Patches were authored in a tight ship-pressure cycle on a real production artifact (a production beginner-course video) and folded back into the skill across four commits.

- **v2.4 (`d303bc0`):** template.html gains pause/resume on the Play button (was first-play-only); space-key toggles play/pause anytime; arrow keys scrub slide AND seek audio anytime (were blocked after autoplay started); click-to-advance on the slide canvas (left third = back, rest = forward, with UI-element guards); fullscreen button + nav-hint chrome. build.py URL-encodes audio src filenames (handles spaces).
- **v2.5 (`cb4563e`):** subtitle data plumbing (built-but-unwired in v2.3) gets a UI: CC button, captions overlay, `renderCaption()` looks up the cue whose `start <= currentTime` is most recent. New `--embed-captions` build.py flag muxes the .vtt as an MP4 `mov_text` soft-sub track for single-file delivery.
- **v2.6 (`5ee4db3`):** INHABIT-on-rendered-HTML cold-substrate audit surfaced three skill-level defects: `render_enumeration` was HTML-escaping the `intro` field (rendering `<em>` literally); enumeration items had no `copy:` slot despite being prime copy-paste candidates; compare layout's `bad`/`good` keys forced red/green coloring even on neutral mode comparisons. Fixed: intro passes raw HTML; enumeration items accept `copy:` (defaults to example text); compare also accepts neutral `left:`/`right:` keys with blue/orange styling. Plus info-btn lifted from low-contrast 32×32 dot to "ⓘ more" pill.
- **v2.7:** `playbackBase` rename (was `startWallClock` triple-purposed; KG #27 Definition Drift fix); bracket-placeholder hint banner auto-renders next to copy buttons whose text contains `[bracketed parts]`; fullscreen button relabels via `fullscreenchange` listener; end-of-deck overlay fires on `audio.ended` or arrow-past-last with a Restart button; volume/mute toggle (red when muted); slide-map dropdown listing each slide with badge + heading + info-panel indicator, click-to-jump with audio seek.

**Two design principles validated by this cycle:**

1. **Patch-fold is rebuild discipline, not paste discipline.** When folding hot-fixes from a deployed artifact back into the skill, audit the *delta* — what's added beyond the proven-working set needs its own justification. v2.4 added `nav-hint` and v2.5 added captions UI that the deployed manual-patch HTML didn't have; both were precursor-justified, not arbitrary.
2. **Capture-mode should hide everything interactive.** Every new HTML control gets a `body.capturing .X { display: none }` rule. MP4 frames stay clean.

Audit lineage: KG #26 (V1 content), KG #27 (v2.4/v2.5 cycle), INHABIT #28 (rendered HTML). Run docs live in the authoring lab's private records.

---

## 1. Architectural decisions

**HTML is authoring-canonical.** All learning material lives in HTML. Every render type (Markdown, KaTeX, Mermaid, SVG, tables, images, copy-buttons, info-btn deep-dives, collapsible details) is HTML-native. Editing is HTML-source-edit; MP4 and MP3 are derivatives.

**Both HTML and MP4 are first-class distribution artifacts.** Pick by hosting platform: Confluence/SharePoint/Stream prefer MP4 (plays inline); local file:// prefers HTML (interactive). MP3 ships as audio-only fallback.

**Two playback modes** (same `slideTimes[]`, different clock):
- Interactive: `<audio>.timeupdate` drives slide transitions and intra-slide reveals. User has play button, can scrub.
- Headless capture: `performance.now()` drives same transitions on wall-clock from `start()`. No audio in browser; ffmpeg muxes MP3 separately.

Mode flips via query param (`?capture=1`).

**Pipeline** (unchanged from v1):

```
YAML script
  ↓
edge-tts (TTS audio + sentence-boundary timestamps)
  ↓
HTML (canonical, GSAP-animated, audio-synced, two-mode playback)
  ├──→ MP3 (TTS output, copied)
  ├──→ MP4 (Playwright headless capture + ffmpeg mux)
  └──→ VTT (optional, derived from sentence boundaries)
```

GSAP for in-HTML animation. ffmpeg only at MP4 derivation.

---

## 2. Render set

Renders in HTML mode, captured-as-static in MP4 mode where applicable:

- Markdown
- KaTeX (math-mode LaTeX)
- Mermaid (architecture/sequence/flow diagrams)
- SVG (raw, inline)
- Images
- Tables
- Collapsible details (interactive in HTML; timed-reveal in MP4 via second sync tier)
- Custom HTML escape-hatch
- Syntax-highlighted code (highlight.js)

**Out of scope for v2:**
- Tone.js / generative audio (competes with TTS narration)
- Standalone audio elements (same)
- Full text-mode LaTeX (theorems, sections, environments) — KaTeX math-only is in
- Arbitrary JavaScript interactivity beyond the primitives' baked-in JS

---

## 3. Primitive vocabulary

**7 generic primitives** (general explainer-video — work for any AI-technique topic):

| Primitive | Shape |
|---|---|
| `title` | badge + h1 + subtitle + optional author |
| `hook` | h2 with highlighted span + optional subtitle |
| `compare` | 2 boxes L/R or stacked, labelled, optional copy-btn |
| `example` | labelled box with optional ai-output sub-region, colored accent, optional copy-btn |
| `iterations` | numbered steps each `(num, finding, result)`, optional intra-slide reveal |
| `enumeration` | n-cell grid each `(num, name, desc, optional example)`, optional intra-slide reveal |
| `recap` | ordered list of items with arrow connectors |

**4 extension primitives** (developer-audience and technical-explainer content):

| Primitive | Why | Library |
|---|---|---|
| `code` | Syntax-highlighted code blocks, copy-btn baked in | highlight.js (CDN) |
| `math` | Math-mode formulas, inline + display variants | KaTeX (CDN, ~250KB) |
| `diagram` | SVG slot + Mermaid layout (architecture, sequence, flow, state) | Mermaid (CDN) + raw-SVG escape |
| `table` | Multi-column data display | Markdown tables → styled HTML |

**Cross-cutting affordances** (work on any primitive):
- `copy-btn` on any text/code block (HTML interactive; visible-but-inert in MP4)
- `info-btn` deep-dive panel (per-slide opt-in; HTML interactive only — not in MP4)
- Color-as-config (per slide and per section, NOT hardcoded to specific section names)

**Escape hatch**: `layout: html` accepts raw HTML strings. Renders as-is in HTML mode; captured as visible-but-inert in MP4 mode (no JS interactivity in capture). Use for one-off cases the primitives don't cover. **If you need it twice, file a primitive request.**

---

## 4. Scaffolds (recipes, not frames)

The original "3 Prompting Concepts" video shipped two reusable structures:

**Per-concept template (3 slides):**
```
title → "what you say" (input demonstration) → "what AI returns" (output demonstration)
```

**Deck arc (~14 slides for 3 concepts):**
```
intro hook (2) → concept 1 (3) → concept 2 (3) → concept 3 (4: title + grid + before/after + insight) → recap with arrows (1) → CTA (1)
```

These are **named recipes**, not enforced shapes. Author can:
- Use a different concept count (1, 2, 4, 5)
- Skip the per-concept I/O triplet (e.g. for chain-of-thought: title → naive → CoT → comparison)
- Use a different arc (problem-first → solution → caveats; or any other)
- Compose primitives directly without invoking any scaffold

**Required**: at least one shipped example deck deviates from the canonical scaffolds, proving recipe-not-frame. (Without this, the scaffolds become prescription regardless of doc framing.) See `examples/scaffold-deviation.yaml`.

---

## 5. Layered pedagogical architecture

**Three-layer delivery** (HTML-native):

| Layer | Content | Mode |
|---|---|---|
| **Surface** | Linear pass through the slides | All modes (HTML / MP4 / MP3) |
| **Depth-on-demand** | Per-concept info-btn side panels | HTML only |
| **Companion reference** | Separate HTML covering broader concept set (optional, in `resources/`) | HTML standalone, ships alongside |

---

## 6. Sync tiers

**Slide-level**: `slideTimes[]` (one entry per slide), baked from edge-tts sentence boundaries.

**Intra-slide micro-reveals**: per-element timestamps for reveals within a slide. Authored at sentence-boundary granularity:

```yaml
- layout: enumeration
  reveal:
    mode: per-item-at-sentence
    examples: per-item-at-sentence-plus-1   # examples reveal one sentence after their item
  items:
    - { name: Role,    desc: "Who?", example: "..." }
    - { name: Task,    desc: "What?", example: "..." }
    # ...
```

`build.py` maps `reveal: per-item-at-sentence` to wall-clock seconds at render time using the boundary array. **No manual MP3 audition required by author.**

---

## 7. Voice + audio + captions

**Voice config in YAML** (root-level):
```yaml
voice: conversational           # shortlist key
# or raw edge-tts name:
voice: en-US-AriaNeural
```

**Curated shortlist** — see `SKILL.md` "Voice options" for the table. Defaults to `conversational` (en-US-AriaNeural).

**Captions**: optional `--captions` flag emits `.vtt` alongside `.mp4`, derived from sentence boundaries. Off by default.

---

## 8. Exit criteria

v2 is **done** when all 9 are checkable:

1. **7 generic primitives** render correctly in HTML and MP4: `title`, `hook`, `compare`, `example`, `iterations`, `enumeration`, `recap`
2. **4 extension primitives** render correctly: `code`, `math`, `diagram`, `table`
3. **Render-set parity** verified in interactive HTML mode (Markdown, KaTeX, Mermaid, SVG, images, tables, collapsible-with-timed-reveal)
4. **Two-mode playback** verified: interactive HTML and headless capture produce same slide timing on the same `slideTimes[]` (within ±0.1s)
5. **Sentence-boundary sync** stays within ±0.3s drift across a 15-min video
6. **Intra-slide micro-reveals** expressible as `reveal: per-item-at-sentence` in YAML — no manual wall-clock tuning
7. **Second-person YAML reproduction**: a person who hasn't seen the source artifact can author a YAML for a topic THEY pick (not in the validation set), produce a watchable MP4 from `SKILL.md` alone
8. **At least one shipped example deviates** from the canonical scaffolds (proves recipe-not-frame) — `examples/scaffold-deviation.yaml`
9. **3-video validation set** (e.g. starter / intermediate / advanced curriculum) renders cleanly through one skill version with **no schema patches between videos**

#9 is the actual generality test — the skill is general iff video 2 doesn't require modifying the schema video 1 used.

**Validation status at v2.0 ship:**
- Criteria 1, 2, 3, 4, 6, 8: validated at build time (primitives present, schema parses, examples render)
- Criteria 5, 7, 9: **validated during real curriculum authoring**, not at v2.0 ship time. v2.0 = "primitives + schema + examples + pipeline are in place; full validation pending the first real curriculum"

---

## 9. Deferred to v2.1+

- Partial re-render (single slide / single sentence without full Playwright pass)
- Full text-mode LaTeX (theorems, sections, environments) — MathJax-with-text-mode dependency
- Tone.js / standalone audio
- Mermaid pre-rendering at build time as default (CDN at view time is the v2 default)
- Concept-selection helper script (v2 leaves selection entirely to author)
- Voice consistency tooling across multi-video curricula
- Native captions/transcripts UI in HTML mode (VTT file is enough for v2)

---

## 10. Concept-selection mechanism

**Explicit non-mechanism**: concept-cuts are the author's decision, not the skill's.

The skill ships **starting-material resources** at `resources/`:
- `resources/prompt-concepts.html` — 10-concept prompting reference

If your topic has a starting-material file in `resources/`, draw concept-cuts from there. Otherwise, decide concepts on your own; the skill helps you express them, not pick them.

Generalizes: "concept-cuts are yours; the skill is expression, not curriculum."

---

## 11. Revision economics

v2 supports full re-render only (~1s wall-clock per 1s video; 15-min video = 15-min Playwright capture). Partial re-render (single-slide diff) deferred to v2.1.

For fast iteration: use `--html-only` to skip Playwright/ffmpeg entirely while drafting.

---

## 12. Status

- [x] Architectural decisions locked (HTML-canonical, two-mode, ffmpeg-post)
- [x] Render set defined
- [x] Primitive vocabulary defined (7 + 4 + escape-hatch)
- [x] Scaffolds defined as recipes (with override requirement)
- [x] Layered pedagogical architecture defined (3 layers)
- [x] Sync tiers defined (slide-level + sentence-boundary intra-slide)
- [x] Voice + captions defined (curated shortlist + opt-in VTT)
- [x] Exit criteria defined (9 items)
- [x] Out-of-scope defined
- [x] Concept-selection mechanism defined (non-mechanism: author's call)
- [x] **v2.0 build shipped** (this commit)
- [ ] Exit criteria 5, 7, 9 validated during first real curriculum authoring
- [ ] v2.1 patches based on real-authoring findings + RMPE pass on original creation chat

## 13. v2.4 — Bilingual builds (2026-06-11)

**Origin:** Prompt-2 of the first production video series asked for an EN/DE toggle on two
already-shipped videos. The pattern was hand-built and verified there first
(Playwright toggle test + whisper round-trip on the German track), then folded
back here as the `languages:` parameter. Reference conversions:
the two hand-built series-1 HTML files (beginner and
intermediate).

**Architecture (one HTML, n languages):**
- Per-language full pipeline pass: resolve `{code: ...}` translation maps →
  render slide innerHTML → TTS → own `slideTimes`/`revealEvents`/`subtitleCues`.
  No timing scaling across languages — every language gets exact boundaries
  from its own edge-tts run (German ≈ +25% vs English; never assume).
- Injected `LANGS` payload: `{default, order, langs: {code: {audio, slideTimes,
  totalDuration, revealEvents, infoData, subtitleCues, slides[], ui}}}`;
  `null` in single-language builds (legacy path byte-identical).
- Runtime `setLang()`: swaps slide innerHTML (containers stay → indexing,
  gradients, data-attrs stable), rebinds the five timing/data globals, rebuilds
  the slide-map (DOM-derived → localizes for free), re-runs hljs/mermaid, and
  jumps the new audio track to the current slide's start — text and narration
  switch together mid-video.
- MP4 = default language only (capture rides the default DOM). Re-order
  `languages:` and re-run for a second MP4.

**Two shipped-output bugs found by the conversion, fixed here:**
1. `_copy_btn_html` embedded `json.dumps(text)` (double-quoted) inside a
   double-quoted onclick attribute → attribute terminated at the first char,
   every copy button dead. Fix: attribute-escape the JSON
   (`html.escape(..., quote=True)`); browser decodes entities before JS parses.
2. Enumeration examples without a `reveal:` mode rendered at CSS
   `opacity:0; max-height:0` with no event ever showing them → permanently
   invisible content. Fix: `.component-example.static` emitted when no reveal
   mode; visible from slide-enter.

**Verified:** legacy example (`example.yaml --html-only`) unchanged-green;
`bilingual-en-de.yaml` Playwright smoke test — load clean, toggle swaps
text+audio mid-video to the new track's slide start, per-language `ui:` labels
apply, EN restores, static examples visible.

## 14. v2.5 — at-sentence-indices reveal (2026-06-12)

**Why:** Series-interface unification of the first production series: Teil 1+2 (hand-built)
regenerated through the generator so all three parts share one interface. Teil 1
slide 10 (the six-components grid — the artifact the enumeration layout was
reverse-engineered FROM) reveals each card at a sub-chunk boundary of a LOCKED,
operator-approved narration where every item spans 4–6 sentences. The existing
reveal modes assume one sentence per item; the narration could not be rewritten
without changing approved audio.

**What:** `reveal: {mode: at-sentence-indices, items: [i0..iN], examples_offset: k}`
on enumeration — explicit slide-local sentence index per item (0 = slide-enter
sentence), examples reveal k sentences after their item. Index lists are
localizable like any field, though parallel translations usually share one list
(series-1 Teil 1: `[0, 5, 10, 15, 19, 23]` fits both DE and EN exactly;
`examples_offset: 2` reproduces the original "+3.5s example expand" timing,
verified against the hand-tuned COMPONENT_EX_TIMES arrays).

**Bound:** config-length mismatch or out-of-range indices surface as drops
(build warning), never runtime errors — same contract as the v2.1 modes.

**Note on numbering:** the 2026-05 addendum block above used v2.4–v2.7 in an
older lineage; current lineage is SKILL.md's (v2.4 = bilingual 2026-06-11,
v2.5 = this).

Also in v2.5: **TTS seam-merge fix.** edge-tts splits long inputs into multiple
service requests at whitespace seams; a seam landing mid-sentence emits a
spurious extra SentenceBoundary (found on series-1 Teil 2: +2 boundaries in BOTH
languages → every later slide time shifted one sentence early). run_tts now
merges any boundary whose text does not end a sentence into its successor.
Surfaced because the regeneration diffed against hand-measured per-chunk
timings; older long single-pass builds may have carried small drift.

Also in v2.5: **capture sync-marker.** The Playwright recording starts at
page-load while the slide timeline starts when the page is ready; nothing
compensated for the gap, so MP4 A/V offset equaled page-load latency —
network-dependent and invisible on fast days (~1.5s, shipped in Teil 3's first
renders) but ~6s on a slow-CDN render. In capture mode the template now shows
a solid-magenta marker until load+fonts+settle, then starts the timeline;
build.py locates the last magenta frame and trims the video head at mux.
Deterministic alignment, independent of network weather.
