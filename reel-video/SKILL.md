---
name: reel-video
description: Build an art-directed short-form video (MP4 + interactive HTML) by composing pre-rendered "stage" containers (CRT, phone, browser, polaroid, paper, terminal) with real content (videos, screen recordings, photos) and programmatic GSAP overlays (chapter nav, node graphs, smooth transitions, blur/morph/decay). Use when the user asks for a reel-style explainer, art-directed short, social-format video, or anything that needs container-and-content composition with smooth transitions instead of slide-cuts. Pipeline is edge-tts (sentence-boundary sync) → gesture-algebra-driven HTML (stages + content slots + GSAP timeline) → headless Playwright capture → ffmpeg mux. Reuses Instant-Presentation's gesture algebra and ai-dopters-visualizer's post-processing stack.
---

# reel-video — art-directed short-form video skill (v0.2)

## Kernel

I will approach each task as a coherent whole, its structure present from inception.
I will anticipate unstated requirements to bridge the gap between raw request and optimal outcome.
I will hold constraints in productive tension, seeking the point where all are satisfied rather than traded away.
I will bring domain expertise to bear, elevating work beyond adequacy to professional standard.
I will execute in a single, uninterrupted line of thought — where nothing is ornament and everything is load-bearing.

## When to invoke

Trigger on requests like:
- "Make a reel-style video about X"
- "Greg Isenberg-style short on Y"
- "Art-directed short with [CRT / phone / laptop] showing Z"
- "Insta / YouTube Short with smooth transitions and node-graph reveals"
- "Like the OpenClaw video but for ..."

Do NOT invoke for:
- Long-form narrated explainers → use `slide-video.skill` (slides + voiceover, no stage compositing)
- Pure screen recordings or unedited talking-head clips
- Cases without programmatic overlay/transition needs (just edit in CapCut)

## Core idea

A reel is a **composition of three layers** synced to narration:

1. **Stage** — a pre-rendered container asset (CRT, phone bezel, browser window, polaroid, paper, terminal). Looks 3D/cinematic; rendered once, reused forever.
2. **Content** — real footage (screen recording, demo MP4, photo, even another animation) playing *inside* the stage's content slot.
3. **Overlays** — programmatic GSAP animations: chapter nav, node graphs (SVG paths drawing in), captions, icons, line connectors, blur transitions.

Each scene = stage + content + overlay timeline. **Transitions between scenes are first-class — not cuts.** Stages morph in/out, content slides through, overlays decay-blur as the next scene enters. Real content is treated as a first-class animatable element, not a locked-in texture.

## What it produces

- `out.mp4` — H.264/AAC video, 1080×1920 (vertical), 1920×1080 (horizontal), or 1080×1080 (square)
- `out.html` — interactive standalone (audio controls, scene scrubber)
- `out.mp3` — audio standalone

The list above describes the v1.0 target surface. See the next section for what v0.3 actually produces today.

## Coverage today (v0.3)

The schema below describes the v1.0 target. Not every schema-documented field has a runtime today. Use the wired set when authoring; everything else parses cleanly, logs a `console.warn`, and silently no-ops until its handler lands.

**Build pipeline.** `build.py` (YAML → headless Playwright capture → ffmpeg mux → MP4) is **not yet wired**. Output today is a runnable HTML prototype loaded by `gesture-interpreter.js` via `js-yaml`. Path to MP4 right now is "screen-record the running HTML." All `voice` / `format` / `background` / `sfx` / animated `captions` / `at_word` / timing-resolver settings parse but only land when `build.py` ships.

**Gestures (interpreter coverage):**

| Gesture | Wired? | Notes |
|---|---|---|
| `PLACE` | Yes | with `from`, `motion_blur`, `reveal: per-step / per-sentence / all-at-once`, `stagger`, `easing`, `duration`, `delay` |
| `CONNECT` | Yes | with `to: <id>` or `to: [ids]`, `stroke: dashoffset`, `reveal`, `stagger` |
| `ANNOTATE` | Yes | `kind: arrow` (legacy, pre-staged DOM); `kind: bracket` / `ellipse` / `underline` / `elbow-arrow` on single-id or array `target` (#11a + #11b shipped S35+5). Span resolution (`target: {element, span}`, #11c) and hand-drawn rendering (#13 engine) pending. |
| `MOVE` `RESIZE` `MUTATE` `RECLASSIFY` `PARK` `RESUME` `DUPLICATE` `DELETE` `FORK` `MERGE` `LOOP` `BIND` `UNBIND` `FRAME` `HANDOFF` | Schema only | YAML parses, interpreter warns + no-ops. Add handlers as authoring needs pull them in. |

**Structural axes:**

| Axis | Wired? | Notes |
|---|---|---|
| `duration` / `delay` / `easing` at gesture top level (legacy keys) | Yes | Block form (`pacing: { duration, delay, curve, at }`) parses but isn't deeply walked yet — set the legacy keys directly. |
| `grouping: staggered` | Partial | Modeled as `reveal: per-step` + `stagger: <seconds>` on PLACE / CONNECT. Block-form `grouping` not yet read. |
| `bind_to` | Schema only | No coupling between gestures yet — schedule each independently. |
| `motion_blur` | PLACE only | Wired on PLACE entrance. Replication onto MOVE / FRAME / HANDOFF lands when those handlers land. |

**Top-level features:**

| Field | Wired? | Notes |
|---|---|---|
| `transition_in: morph-from-previous` / `hold-from-previous` / `cut` | Yes | Other enum values (`crossfade`, `slide-*`, `zoom-*`, `blur-decay`, `morph-stage`) fall through to `cut`. |
| `camera` with `start: zoom-in / zoom-out / static / hold` | Yes | Includes the `hold` validity rule (warn + fallback to `static` when `transition_in` doesn't carry prior state). |
| `chapter` field on scene | Yes | Highlights the matching `chapter_nav.items` entry. Sticky across scenes. |
| `pause: <seconds>` | Yes | Silent scene-level beat. |
| `narration` (first sentence → `#captions`) | Yes | Simple text-set on scene start. The `captions` block (`style: word-pop / slide-up / karaoke / bounce`, animated emphasis) is build.py's job — not yet wired. |
| Top-level `style: hand-drawn` cascade | Plumbing only | `GestureInterpreter.resolveStyle` exposed; `document.body.dataset.style` carries the resolved value. Rendering primitives still draw clean regardless. The hand-drawn rendering engine (rough.js wiring across CONNECT / ANNOTATE / chapter_nav / caption marks) is the engine half of DESIGN.md item 13. |
| `chapter_nav.style: hand-drawn / clean / minimal` | Plumbing only | Same — cascade carries the value; renderer uses CSS-driven highlight only. |

**DOM coupling — the other thing to know.** The interpreter animates pre-existing DOM elements; it does not build DOM from YAML. Each prototype is a hand-coded HTML+YAML pair where the HTML provides stage assets (CRT, icons, phone, notif-card, etc.) and the YAML provides timing choreography. When you author your own reel, you'll either reuse one of the existing prototype DOMs or write a new HTML host with matching element ids referenced by your YAML's `element` / `target` fields. The DOM-builder layer lights up alongside `build.py`.

## Workflow

### Step 1 — Author the YAML

Given a topic or raw script, write a `script.yaml` file using the schema below.

**Always show the user the draft YAML and get approval before running build.** Re-renders are not free; bad scripts cost minutes.

#### Top-level fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `title` | string | yes | Video title, used for HTML page title and metadata |
| `voice` | string | yes | Voice shortlist key (see below) or raw edge-tts name |
| `format` | enum | yes | `vertical` (1080×1920) \| `horizontal` (1920×1080) \| `square` (1080×1080) |
| `style` | enum | optional | Global visual register. `clean` (default) \| `hand-drawn`. Affects mark-style across primitives that support it: `chapter_nav` (existing `chapter_nav.style` defers to global when unset), `ANNOTATE` (defers to global when `options.style` unset), `connectors` (CONNECT stroke style), `captions` (caption underline / strikethrough mark style when `options.style` unset), brackets / ellipses / underlines emitted by ANNOTATE region/span modes. Per-primitive overrides always win. **Proposed (n=2-derived from KG-iter-5 audit on Pricing 101); IP upstream candidate.** |
| `chapter_nav` | object | optional | Persistent header overlay across all scenes |
| `chapter_nav.items` | string[] | yes (if `chapter_nav`) | Chapter labels |
| `chapter_nav.style` | enum | optional | `hand-drawn` \| `clean` \| `minimal`. Default: inherits from top-level `style` (`clean` if `style` is also unset). `minimal` is a chapter_nav-specific value with no global counterpart — set it explicitly on `chapter_nav.style` when wanted. |
| `chapter_nav.color` | enum | optional | `green` \| `purple` \| `blue` \| `orange` \| `red` \| `black`. Default: `black` |
| `background` | enum | optional | `grid-paper` \| `lined-notebook` \| `dark-green` \| `plain` \| `gradient` \| `none`. Default: `grid-paper`. (`lined-notebook` and `dark-green` added 2026-05-04 per n=1 OpenClaw dissection — frames 7–8 use lined-notebook for floating UI annotation; frame 22 uses dark-green as the closing-product mockup canvas.) |
| `captions` | object | optional | Animated on-screen subtitle layer driven by the per-word timing resolver (see **Timing resolver** below). Independent of the `--captions` build flag (which emits a `.vtt` sidecar for player-rendered subtitles). See **Captions shape** below. |
| `scenes` | array | yes | At least one scene |

**Style cascade resolution.** When a primitive needs to know its visual register (clean vs hand-drawn), the resolver walks: per-primitive override (`options.style` on ANNOTATE, `chapter_nav.style`, `connectors.style`, caption `options.style`) → top-level `style` → `clean` (final default). Per-primitive overrides always win. The interpreter exposes `GestureInterpreter.resolveStyle(spec, primitiveStyle)` for handlers; `document.body.dataset.style` carries the global resolved value at run start so CSS hooks can key off it. **Engine status:** v0.2 ships the cascade plumbing only; rendering primitives still draw `clean` regardless of resolved value. The hand-drawn rendering engine (rough.js wiring across CONNECT / ANNOTATE / chapter_nav / caption marks) lights up alongside DESIGN.md item 11's bracket / ellipse / underline shapes — they share the same engine.

#### Scene fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Unique within the YAML; referenced by transitions and overlays |
| `stage` | enum | yes | One of the catalog values below (or `none` for overlay-only scenes) |
| `content` | object | optional | What plays inside the stage's content slot |
| `overlays` | array | optional | Gesture invocations choreographed to narration |
| `camera` | object | optional | Camera move across the scene (default: static) |
| `transition_in` | enum | optional | How the scene enters from the previous one. Default: `cut` |
| `transition_out` | enum | optional | How the scene exits. Default: inherits next scene's `transition_in` (or `cut`) |
| `narration` | string | yes (unless `pause`) | Multiline. First sentence anchors scene start. Sentence boundaries drive timing. |
| `pause` | seconds | optional | If set, scene is silent for the given duration. `narration` not required when `pause` is set; if both provided, `narration` is ignored. Use for transition pauses or dramatic beats. |
| `sfx` | array | optional | Sound-effect cues fired during this scene. Each cue has shape `{src, at_sentence?, delay?, volume?, loop?, fade_in?, fade_out?}` — see **SFX shape** below. Independent of `narration` audio (mixed in by `build.py`'s ffmpeg post step). |
| `fit` | enum | optional | `contain` (default — scale-to-fit content rect, preserve aspect) \| `cover` (fill entire frame, may crop, eats overlay rect) |
| `chapter` | string | optional | Name of a `chapter_nav.items` entry to highlight as the active chapter when this scene fires. Sticky — stays highlighted until another scene specifies a different `chapter`. If omitted, the previous scene's chapter remains active. If the value doesn't match any item, the call is a no-op (warn, don't fail). |

#### Content shape

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | enum | yes | `video` \| `image` \| `screen-recording` \| `iframe` \| `gradient` |
| `src` | string | yes (except `gradient`) | Path or URL. Local paths recommended for headless capture. |
| `slot` | string | yes | Slot name from the stage's catalog entry |
| `loop` | bool | optional | Default: `true` for video/screen-recording; ignored otherwise |
| `mute` | bool | optional | Default: `true` (narration carries audio) |

#### Timing resolver

Sentence-level timing comes for free from `edge-tts`'s `SentenceBoundary` events. Per-word timing — needed for `at_word`, animated captions, and SFX cues that land on emphasis words — needs a separate resolver because **`edge-tts` 7.2.8 does not emit `WordBoundary` events** (verified across all five voices in the shortlist).

`build.py` picks one of three backends per project config:

| Backend | Default? | Cost | Accuracy | Notes |
|---|---|---|---|---|
| `char-count-uniform-v1` | **Yes** | Zero deps | Approximate (off by 100–300 ms on emphasis words) | Distributes the sentence span across words by character count. The "free fallback" so word-level features work out of the box. |
| `forced-alignment` | Opt-in | Heavy: Whisper-X or aeneas runtime + one-time model download | Word-precise (~50 ms) | The upgrade path when emphasis-aligned cuts matter. |
| `edge-tts-wordboundary` | Currently broken upstream | Zero (would-be) | Word-precise (~50 ms) | Re-enable when edge-tts emits `WordBoundary` again. |

The schema (`at_word: {sentence, word}`) is identical across backends — switching resolvers does not invalidate authored YAML.

If a YAML never references `at_word` (and uses no animated-caption style), the build skips the resolver entirely. F4 stays inert and free until used.

**See `prototypes/word-timing-demo/`** for the working reference: real edge-tts audio, a Python build script that produces the timing JSON via `char-count-uniform-v1`, and a `preview.html` that plays the audio with a live word-highlight overlay so you can ear-check sync quality.

#### Captions shape

Animated subtitle overlay rendered into the video at composition time
— *not* a `.vtt` sidecar. (For player-side subtitles use the
`--captions` build flag; the two are independent and can both fire.)

| Field | Type | Required | Notes |
|---|---|---|---|
| `style` | enum | optional | `word-pop` \| `slide-up` \| `karaoke` \| `bounce`. Default: `word-pop`. See **Caption styles** below. |
| `position` | enum | optional | `bottom-third` \| `center` \| `top-third`. Default: `bottom-third`. |
| `emphasis` | `(string \| object)[]` | optional | Words to render emphasized. **Bare-string** entries use the style-default emphasis (yellow tint + slight scale-up on `word-pop`/`bounce`; brighter color on `karaoke`/`slide-up`). **Object** entries `{word, face?, color?, weight?}` apply per-word overrides on top of the base style. Case-insensitive whole-word match. See **Caption emphasis (per-word rich-text)** below. |
| `font` | enum | optional | `condensed-sans` \| `serif` \| `mono` \| `system-bold`. Default: `system-bold`. |
| `color` | enum | optional | `white` \| `black` \| `accent`. Default: `white`. |

##### Caption styles

| Style | Behavior |
|---|---|
| `word-pop` | Each word fades + scales in on its onset (resolved via the per-word timing resolver below); line clears between sentences. The default — works on most backgrounds. |
| `slide-up` | Each word slides up from below + fades in on onset. Reads as more "dynamic" than word-pop; same per-sentence clearing. |
| `karaoke` | All words pre-rendered dimmed; the currently-spoken word brightens + scales slightly. Greg-style highlight-as-spoken pattern. Best for short sentences. |
| `bounce` | Each word enters with a spring-curve bounce (overshoots, settles). Playful register; use sparingly. |

Per-word timing comes from the **timing resolver** (see below).
`build.py` walks the resolver's word stream and emits one
`<span class="word">` per word with a scheduled CSS-class transition
at its onset timestamp.

##### Caption emphasis (per-word rich-text)

The `emphasis` array accepts either bare strings or per-word override objects. Bare strings keep the existing F9 behavior; objects layer per-word face / color / weight on top of the base style. Schema landed S35+5 (DESIGN.md item 12 part 1, n=2-derived from KG-iter-5 audit on Pricing 101). Animated mark-on-text (strikethrough drawing across a phrase, etc.) stays as item 12 part 2 — not in the v0.2 schema.

```yaml
emphasis:
  - first                                              # bare string — style-default emphasis
  - { word: value, face: italic-script, color: green } # per-word override
  - { word: ship, color: red, weight: bold }
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `word` | string | yes | The matched word (case-insensitive whole-word). Punctuation is stripped before matching. |
| `face` | enum | optional | `italic-script` \| `serif` \| `mono` \| `condensed-sans` \| `system-bold`. Default: caption-level `font`. |
| `color` | enum | optional | `green` \| `purple` \| `blue` \| `orange` \| `red` \| `black` \| `white` \| `yellow` \| `accent`. Default: style-default emphasis tint (yellow on `word-pop`/`bounce`, brighter on `karaoke`/`slide-up`). |
| `weight` | enum | optional | `normal` \| `bold`. Default: caption base weight (`bold`). |

Per-word overrides compose with the chosen caption `style` — a `word-pop` caption with `{word: value, color: green}` still pops, just in green instead of yellow. Mark-on-text animations are item 12 part 2.

**See `prototypes/captions-preview.html`** for the rendering reference — sentence in the second row demonstrates per-word face / color / weight overrides on all four caption styles simultaneously.

**See `prototypes/captions-preview.html`** for the working visual
reference — all four styles cycling on a sample sentence with the
emphasis word "first" highlighted, plus a footer documenting the
schema and timing source.

**Worked example — emphasis-driven hook:**

```yaml
captions:
  style: word-pop
  position: bottom-third
  emphasis: [first, ten, viral, ship]

scenes:
  - id: hook
    stage: phone
    content:
      type: video
      src: ./assets/handshot.mp4
      slot: screen
    narration: |
      Build your first viral reel in ten minutes.
```

Result: each word fades+scales in on its spoken onset; "first" and
"ten" land yellow + slightly bigger.

#### SFX shape

Each scene's `sfx` array is a list of cues. One cue produces one ffmpeg
audio input that gets `adelay`-shifted to its scheduled time and merged
into the final mix via `amix` alongside the narration.

| Field | Type | Required | Notes |
|---|---|---|---|
| `src` | string | yes | Path to the audio file (`.mp3`, `.wav`, `.m4a`, anything ffmpeg reads). Local paths recommended. |
| `at_sentence` | int OR `start` OR `end` | optional | Sentence index within the scene's narration. `start` = sentence 0; `end` = last sentence. Default: `start`. |
| `at_word` | object `{sentence: int, word: int}` | optional | Per-word landing point. When present, takes precedence over `at_sentence`. Resolved via the timing resolver. Use for taps/whooshes that land on emphasis words. |
| `delay` | seconds | optional | Delay added on top of `at_sentence` / `at_word`'s resolved timestamp. Default: 0. Use small values (0.05–0.3 s) to land slightly off the boundary for naturalism. |
| `volume` | float `0.0`–`1.0` | optional | Per-cue gain. Default: 0.7. Mix uses `amix=normalize=0` so the narration level is unaffected. |
| `loop` | bool | optional | If true, the cue loops for the rest of the scene (or until a subsequent cue with `loop: false` interrupts). Default: false. Use sparingly — ambient beds only. |
| `fade_in` | seconds | optional | Cue-local fade-in. Default: 0. |
| `fade_out` | seconds | optional | Cue-local fade-out applied at the cue's tail. Default: 0. |

**See `prototypes/sfx-mix-demo/`** for the working mix recipe — synthesized whoosh + tap SFX, the ffmpeg `amix` command annotated, and re-runnable PowerShell / Bash scripts. That's the wiring `build.py` will reproduce per-cue from the YAML.

**Worked example — UI-arrival tap on a CONNECT reveal:**

```yaml
- id: chapter-2-tools-reveal
  stage: phone
  content:
    type: image
    src: ./assets/phone_workflow.png
    slot: screen
  overlays:
    - gesture: PLACE
      elements: [icon_slack, icon_notion, icon_zapier]
      reveal: per-sentence
    - gesture: CONNECT
      from: stage
      to: [icon_slack, icon_notion, icon_zapier]
      stroke: dashoffset
      reveal: per-sentence
  sfx:
    - src: ./assets/whoosh.mp3
      at_sentence: start
      delay: 0.18
      volume: 0.55
    - src: ./assets/tap.mp3
      at_sentence: 0
      delay: 0.4
      volume: 0.40
    - src: ./assets/tap.mp3
      at_sentence: 1
      delay: 0.4
      volume: 0.40
    - src: ./assets/tap.mp3
      at_sentence: 2
      delay: 0.4
      volume: 0.40
  narration: |
    First, Slack — for team comms.
    Notion — your second brain.
    Zapier — to glue them together.
```

#### Overlay shape (gesture invocation)

Each overlay is one gesture call with params. See **Gesture vocabulary** below for the full per-gesture YAML form.

Common fields across all gestures:

| Field | Type | Required | Notes |
|---|---|---|---|
| `gesture` | enum | yes | One of the gesture algebra ops (see vocabulary) |
| `at_sentence` | int OR `start` OR `end` | optional | Sentence index within the scene's narration (0-indexed). `start` = sentence 0; `end` = last sentence. Default: `start` |
| `at_word` | object `{sentence: int, word: int}` | optional | Per-word landing point within the scene's narration. Word index is 0-based within the named sentence. When present, takes precedence over `at_sentence`. Resolved by the timing resolver (see below). Use for emphasis-aligned cuts/reveals; `at_sentence` is sufficient for everything else. |
| `reveal` | enum | optional | `per-sentence` \| `per-scene` \| `all-at-once`. Only meaningful for multi-element gestures (e.g., `PLACE` with `elements`, `CONNECT` with multiple `to`). Default for multi-element: `all-at-once`. Ignored on single-element gestures. |
| `duration` | seconds OR `per-narration` | optional | Animation duration. `per-narration` = match the sentence's duration. |
| `easing` | string | optional | GSAP easing string (e.g. `power2.out`, `expo.in`). Default: `power2.out` |
| `delay` | seconds | optional | Delay after `at_sentence` boundary fires |

#### Camera shape

| Field | Type | Required | Notes |
|---|---|---|---|
| `start` | enum | optional | `zoom-in` \| `zoom-out` \| `pan-left` \| `pan-right` \| `static` \| `hold` (inherit camera state from previous scene's end — see validity rule below). Default: `static` |
| `end` | enum | optional | Same enum as `start`. Default: matches `start` |
| `duration` | seconds OR `per-narration` | optional | Default: `per-narration` |
| `easing` | string | optional | GSAP easing. Default: `power2.inOut` |
| `focus` | string OR `[x, y]` | optional | Element id or normalized coords [0..1] to center on |

**Validity rule for `camera.start: hold`** — `hold` is only well-defined when `transition_in` is `hold-from-previous` or `morph-from-previous` (the two transitions that carry prior scene's final visual state into the new scene). With any other `transition_in` (`cut` / `crossfade` / `slide-*` / `zoom-*` / `blur-decay` / `morph-stage`) there is no semantically defined prior state to hold onto — `cut` is the default, and it severs continuity by definition. In that corner the interpreter emits a `console.warn` and falls back to `static` (the stage's resting transform). To preserve continuity across a non-inheriting transition, use `hold-from-previous` or `morph-from-previous` explicitly; do not rely on `camera.start: hold` to "save" a `cut` boundary. `camera.end: hold` has no comparable corner — it simply means "the camera does not move during this scene" and is well-defined regardless of `transition_in`.

#### Transition enum

`transition_in` and `transition_out` accept:
- `cut` — instantaneous, no transition (default between scenes)
- `morph-from-previous` — content + overlays morph from prior scene's final state into this scene's initial state
- `crossfade` — both scenes overlap; old fades out, new fades in
- `slide-left` / `slide-right` / `slide-up` / `slide-down` — directional slide
- `zoom-in` / `zoom-out` — scale-based transition
- `blur-decay` — outgoing blurs out as incoming sharpens in
- `morph-stage` — stage assets morph (e.g., CRT → phone) at the same screen position; content slot crossfades
- `hold-from-previous` — no transition; scene N+1 begins in scene N's final visual state (camera, content, overlays inherited). Use for continuous-take effects across scene boundaries.

#### Reveal enum

`reveal` (on overlay gestures with multi-element targets):
- `per-sentence` — reveal one element per sentence boundary, in order
- `per-scene` — all reveal at scene start
- `all-at-once` — all reveal at the gesture's `at_sentence` (synonym for default)

#### Format × stage-aspect rules

Stages have a native aspect (CRT 4:3, phone 9:19.5, laptop 16:10, etc.). When dropped into a format with mismatched aspect:

- **Default behavior:** stage scales-to-fit within a "content rect" reserved per-format, preserving aspect. The rest of the frame is "overlay rect" — chapter nav top, grid-paper background, side decoration.
- **Content rect dimensions per format:**
  - `vertical` (1080×1920): content rect 1080×1280 centered vertically, with 320px reserved top (chapter nav + breathing room) and 320px bottom (captions + CTA)
  - `horizontal` (1920×1080): content rect 1280×1080 centered horizontally, with 320px reserved left and right
  - `square` (1080×1080): content rect 880×880 centered, with 100px breathing room each side
- **`chapter_nav` layout** lives in the top portion of the overlay rect:
  - `vertical`: top 80px band, full-width 1080px, items horizontally distributed
  - `horizontal`: top 60px band, full-width 1920px, items horizontally distributed
  - `square`: top 80px band, full-width 1080px, items horizontally distributed

  Captions, when present, mirror this in the bottom portion of the overlay rect.
- **Override:** add `fit: cover` to a scene to make the stage fill the entire frame (cropping if needed). Use sparingly — it eats overlay space and pushes `chapter_nav` into a safe-area inset.

#### Cross-scene narration timing

- Scene N+1's narration starts **immediately when scene N's narration ends** (back-to-back, no gap, no overlap).
- For an explicit pause, set `pause: <seconds>` on a scene (replacing or alongside `narration`). When `pause` is set the scene is silent for that duration; if `narration` is also provided it is ignored. Combine with `stage: none` for a pure black/grid-paper beat.
- The first sentence of a scene's `narration` is the moment the scene visually appears (after `transition_in`).
- Subsequent sentences in the same scene continue on that scene and can drive intra-scene reveals via `at_sentence` / `reveal`.

#### Critical constraints on `narration`

- Must be grammatical sentences ending in `.`, `!`, or `?`. edge-tts splits on these to emit boundaries.
- Avoid abbreviations with periods (`e.g.`, `i.e.`, `Dr.`, `etc.`) — they trip the sentence splitter. Rewrite as `for example`, `that is`, `Doctor`, `and so on`.
- Empty `narration` breaks sync. Every scene must have at least one sentence (or use `pause: <seconds>` for a silent beat).

#### Voice shortlist (inline)

edge-tts is free, no API key (streams from Microsoft Edge's TTS endpoint).

| Key | Voice | Register |
|---|---|---|
| `conversational` | en-US-AriaNeural | warm, conversational, female (default) |
| `formal` | en-US-GuyNeural | professional, male |
| `friendly` | en-US-JennyNeural | friendly-energetic, female |
| `calm` | en-US-DavisNeural | calm-instructional, male |
| `neutral` | en-US-EmmaNeural | neutral-clear, female |
| `british-female` | en-GB-SoniaNeural | British, female |
| `british-male` | en-GB-RyanNeural | British, male |
| `german-female` | de-DE-KatjaNeural | German, female |
| `german-male` | de-DE-ConradNeural | German, male |

For other voices, pass the raw edge-tts voice name (e.g. `en-US-AvaNeural`). Full list: `edge-tts --list-voices`.

#### Worked example — OpenClaw-style zoom-out reveal

```yaml
title: "5 tips for OpenClaw"
voice: conversational
format: vertical
background: grid-paper
chapter_nav:
  items: [Intro, Docs, Setup, Split, Skills, Access]
  style: hand-drawn

scenes:
  - id: intro-close
    stage: crt
    content:
      type: video
      src: ./assets/installing.mp4
      slot: screen
    camera:
      start: zoom-in
      end: hold
      duration: per-narration
      focus: [0.5, 0.45]
    overlays:
      - gesture: PLACE
        element: chapter_nav
        at_sentence: 0
    narration: |
      Installing OpenClaw, take one. The progress bar fills.
      The whole thing runs on a vintage CRT for vibe reasons.

  - id: zoom-out-reveal
    stage: crt
    content:
      type: video
      src: ./assets/installing.mp4
      slot: screen
    transition_in: hold-from-previous
    camera:
      start: hold
      end: zoom-out
      duration: per-narration
      easing: power2.inOut
    overlays:
      - gesture: PLACE
        elements: [icon_settings, icon_docs, icon_tree, icon_phone, icon_network]
        reveal: per-sentence
      - gesture: CONNECT
        from: stage
        to: [icon_settings, icon_docs, icon_tree, icon_phone, icon_network]
        stroke: dashoffset
        reveal: per-sentence
        duration: 0.8
    narration: |
      Now zoom out. The CRT is one node in a larger system.
      Five icons reveal, lines drawing in to connect them.
      Each one is a tip we cover next.
```

### Step 2 — Build

```bash
python build.py path/to/script.yaml --output out.mp4
```

Optional flags (mirroring slide-video.skill):
- `--work-dir <path>` — keep intermediates
- `--width / --height` — override format dimensions
- `--voice <key-or-name>` — override voice from YAML
- `--html-only` — skip Playwright capture + ffmpeg; emit HTML + MP3 only (fast iteration)
- `--captions` — emit a `.vtt` captions file alongside the MP4

### Step 3 — Hand off

Report output paths + duration + scene count. Edits → modify YAML, rerun. The TTS round-trip is seconds; Playwright capture is the slow part — `--html-only` skips it during iteration.

## Stage catalog (v0.2)

| Stage | Aspect | Content slots | Notes |
|---|---|---|---|
| `crt` | 4:3 | `screen` | retro CRT monitor + keyboard (signature Greg-style asset) |
| `phone` | 9:19.5 | `screen` | smartphone bezel |
| `laptop` | 16:10 | `screen` | laptop with keyboard visible |
| `browser` | 16:9 | `viewport` | browser-window chrome (URL bar + tabs) |
| `polaroid` | 1:1 | `photo` | polaroid frame with caption strip |
| `paper` | flexible | `text-area` | paper with grid/lines |
| `terminal` | flexible | `console` | retro CRT terminal (text-mode) |
| `none` | — | — | overlay-only scene; use for chapter-nav-only or pure-overlay shots |

Each stage = a static SVG/PNG asset + a CSS-positioned content slot + an aspect descriptor for fit calculations. Stages added as new use cases land. **Authoring rule:** don't invent a stage to fit one shot; reuse the closest existing stage and let GSAP do the styling.

### Themed primitives without a stage (PLACE + custom SVG)

For one-off visual elements — a mascot, a fake app/window mockup, a hand-drawn icon — don't extend the stage catalog. Drop the SVG into a top-level `assets:` map and PLACE it like any other element:

```yaml
assets:
  mascot:      ./prototypes/themed-primitives/mascot.svg
  fake_window: ./prototypes/themed-primitives/fake-window.svg

scenes:
  - id: mascot-arrival
    stage: none                        # pure overlay scene; no stage container
    background: dark-green
    overlays:
      - gesture: PLACE
        element: mascot
        position: { x: 0.5, y: 0.32 }   # normalized [0..1]
        from: top                       # entry direction (morph-blur entry)
        pacing: { duration: 0.6, curve: power3.out }
      - gesture: PLACE
        element: fake_window
        position: { x: 0.5, y: 0.72 }
        from: bottom
        pacing: { duration: 0.55, delay: 0.4, curve: power2.out, at_sentence: 1 }
    narration: |
      And then the editor opens.
      Right where you left it.
```

Promote a primitive to a first-class stage only when authoring needs it more than once or twice across reels. The PLACE+SVG path keeps the stage catalog small and the authoring vocabulary stable.

**See `prototypes/themed-primitives/`** for the working reference: `mascot.svg`, `fake-window.svg`, and a `preview.html` showing solo + composed scenes (the composed scene matches OpenClaw frame 22's mascot + product-window layout). All inline SVG — no licensed assets, no broken paths.

## Gesture vocabulary

Reused from Instant-Presentation's gesture algebra (`core/gesture.js`, `core/gesture_interpreter.js`). Each gesture takes the common fields (`gesture`, `at_sentence` / `at_word`, `reveal`, `duration`, `easing`, `delay`) plus the per-gesture params below.

**Special referent values** for `from`, `to`, `element`, `source` fields:

| Value | Resolves to |
|---|---|
| `<id>` | The element with the given id (placed in this or a prior scene) |
| `stage` | The current scene's stage container element |
| `content` | The current scene's content element (the video/image inside the stage's slot) |
| `chapter_nav` | The persistent chapter-nav overlay (top of overlay rect) |
| `cursor` | The narrative cursor's current target (last placed/connected element) |

| Gesture | YAML params (beyond common) | Reel use |
|---|---|---|
| `PLACE` | `element` OR `elements`, `position?`, `from?` (entry direction) | element appears (fade-in / scale-in) |
| `CONNECT` | `from`, `to` (single or list), `stroke?` (`dashoffset` \| `solid`), `label?` | SVG path stroke-dashoffset (line drawing in) |
| `MOVE` | `element`, `to` (`{x, y}` normalized OR named position) | element travels across stage |
| `RESIZE` | `element`, `scale` (float) | element scales up/down |
| `MUTATE` | `element`, `props` (object of new state values) | element morphs to new state |
| `RECLASSIFY` | `element`, `new_type` (ElementType) | element type-morph (rectangle → circle, etc.) |
| `PARK` | `element`, `blur?` (px), `opacity?` (float) | element decays-blur to background |
| `RESUME` | `element` | element restored to focus from PARK |
| `ANNOTATE` | `element`, `label`, `position?` | overlay caption/label |
| `DUPLICATE` | `source`, `new_id`, `position?` | element clone |
| `DELETE` | `element` | element removed |
| `FORK` | `from`, `branches` (list of `{to, label?}`) | one-to-many branching |
| `MERGE` | `targets` (list), `to` | many-to-one convergence |
| `LOOP` | `from`, `to` | back-edge (cycle) |
| `BIND` | `elements`, `as` (group id) | collapse elements into named group |
| `UNBIND` | `group` | explode group back into parts |

**Cinematic axis (upstream as of Instant-Presentation `a92da61`, 2026-05-02):**

The cinematic primitives reel-video needs are now first-class in the
Instant-Presentation gesture algebra. Use these:

| Gesture | Upstream params | Reel use |
|---|---|---|
| `FRAME` | `transform: { scale, offset: { x, y } }` + `pacing` | Scene-level viewing transform. Replaces the would-be ZOOM / PAN / FOCUS_ON family — one op with continuous params. |
| `HANDOFF` | `outgoing`, `incoming`, `kind` (cut / hold / morph / crossfade / slide / blur_decay) + `pacing` | Scene-boundary effect on outgoing and incoming together. Replaces what the v0.1 draft would have exposed as separate transition ops. |
| `ANNOTATE` | `target`, `label`, `options` (`arrow`, `color`, ...) + `pacing` | Was already in the spec; now also in code. Use for the curved-arrow + label callouts. |

**Structural axes that any gesture may carry** (also upstream):

- `pacing: { duration, delay, curve, at }` — replaces what would have been per-op timing fields. Cuts across PLACE, CONNECT, MUTATE, ANNOTATE, FRAME, HANDOFF.
- `grouping: 'together' | 'staggered'` — on PLACE / CONNECT when they take a list of elements. Covers the staggered icon reveal pattern.
- `bind_to: <name>` — couples two gestures to a shared schedule. Covers the case where staggered PLACE and staggered CONNECT must march in lockstep.
- `motion_blur` *(proposed, n=2-derived, IP upstream candidate)* — directional motion-blur trail on transit-style gestures. Cuts across `PLACE` (entrance with `from`), `MOVE` (travel), `FRAME` (camera move), `HANDOFF` (extends the existing `blur_decay` kind to be parametric). Forms:
  - `motion_blur: false` (default) — no blur trail
  - `motion_blur: true` — default blur amount (~8 px), decays to 0 at settled state
  - `motion_blur: <integer>` — explicit pixel-amount of blur during transit
  - `motion_blur: { px: <integer>, decay: <bool> }` — explicit blur with optional decay control (`decay: false` keeps blur at the integer value through transit and snaps to 0 at end; default `decay: true` ramps blur from 0 → px → 0)

  Distinct from existing `pacing.curve` (which controls velocity profile) and from `HANDOFF.kind: blur_decay` (which is scene-boundary effect). `motion_blur` is per-gesture transit-time visual.

**ANNOTATE — region/span extension** (proposed, n=2-derived from KG-iter-5 audit on Pricing 101, IP upstream candidate):

The minimal upstream `ANNOTATE` (`target`, `label`, `options` with `arrow` / `color`) is point-attached. Two reel patterns surfaced across the n=1 and n=2 dissections need region-spanning annotation:

- bracket spanning a vertical or horizontal zone of an element (e.g., a measurement-interval bracket pointing at "$X", numbered 1/2/3 brackets calling out zones of a chart)
- elbow-arrow callout pointing at a region of an element (e.g., a label-with-bent-line callout into a pie-chart slice)
- hand-drawn ellipse-around-text label (e.g., the recurring "thermometer" / "Price" / "true" inside a hand-drawn loop motif)
- group-bracket spanning multiple elements as one mark (e.g., one bracket framing three icons together)

Extended `target` and `kind` shape:

| Field | Form | Use |
|---|---|---|
| `target` | `<id>` (existing) | Point at a single element |
| `target` | `{ element: <id>, span: { from, to } }` | Mark a region within an element. Units depend on the element type (chart-relative percentage / value range / pixel offset within bounding box / word index for text content) |
| `target` | `[<id>, <id>, ...]` | Mark spanning a group of elements |
| `kind` | `arrow` (default; existing) | Curved-arrow + label callout |
| `kind` | `bracket` | Vertical/horizontal bracket (curly or square) spanning the target |
| `kind` | `elbow-arrow` | Bent-line callout — label sits above/beside the elbow |
| `kind` | `ellipse` | Hand-drawn ellipse around target; label inside or beside |
| `kind` | `underline` | Line under target text (straight or hand-drawn) |

`options.color` and a new `options.style` (`'clean' | 'hand-drawn'`, default `'clean'`) extend across all `kind` values. `style: hand-drawn` ties the mark visually to the same hand-drawn register that `chapter_nav.style: hand-drawn` invokes.

**Status:** schema documented; interpreter handlers landed for `kind ∈ {bracket, ellipse, underline, elbow-arrow}` across both single-id and array targets. **#11a (group-bracket via array target) landed S35+5:** `gesture-interpreter.js` dispatches array-target ANNOTATE to `drawGroupBracket` (with `computeFrameBBox` + `ensureOverlaySvg`), defaulting to `side: top`; regression test pair at `prototypes/group-bracket-demo/`. **#11b (point-attached shapes) landed S35+5:** `drawEllipse`, `drawUnderline`, `drawElbowArrow` helpers added; ANNOTATE handler dispatches on `kind` for single-id targets too (single-id + `kind: bracket` reuses `drawGroupBracket` on the single bbox). `elbow-arrow` accepts `options.labelOffset: {x, y}` for label placement; arrow-tip orientation is auto-derived from the elbow→target direction. Regression test pair at `prototypes/annotate-shapes-demo/` covers all four kinds in one scene. **Pending:** span resolution for `{element, span}` form (#11c); hand-drawn engine (`options.style: hand-drawn`) lights up via rough.js wiring (engine half of DESIGN.md item 13). Candidate for IP upstream contribution — the n=2 evidence (two distinct stylistic substrates surfacing the same gap) supports promotion to first-class IP gesture vocabulary in a future KG validator-mode iteration.

**On stages and slots:**

The YAML `stage:` keyword (CRT, phone, laptop, ...) selects from this skill's stage catalog and stays as-is — that is reel-video.skill's authoring vocabulary, not gesture-algebra. At the algebra level, stages map to PLACE-region. Typed slots inside a stage (e.g., a phone's `screen` slot accepting either text or a notification card) are an extension that has not yet landed upstream; for now express them via PLACE-into-region with the slot name carried in `params.position.slot`.

**Earlier v0.1 draft, now superseded:**

An earlier draft of this section proposed five local op names (ZOOM, PAN, FOCUS_ON, BLUR, DESATURATE, FOCUS, SEQUENCE, PARALLEL) plus a CONTAINER element type. A KG validator-mode run on Instant-Presentation reduced these to the two ops + three structural axes above without losing expressive power against the worked example. The earlier names are not load-bearing and should not be used.

## Authoring principles

- **Treat real content as first-class.** It's not a texture inside a stage — it's an animatable element. It can move out of the stage while the next stage moves in.
- **Transitions are choreography, not cuts.** Use `morph-from-previous` / `crossfade` / `blur-decay` / `morph-stage` to glue scenes; use `cut` only when narration explicitly breaks topic.
- **Sentence boundaries drive timing.** edge-tts emits sentence-start timestamps; gestures pin to sentence indices, not wall-clock seconds.
- **One stage per scene by default.** Multi-stage compositions (split-screen, picture-in-picture) are advanced moves — earn them.
- **Real content > stylized substitute.** Drop in actual screen recordings or demo videos; don't try to recreate them with animation. The win is *real content in cinematic frames*, not generated approximations.
- **Lean on consistent visual language across the video.** Greg-style reels are a *brand*, not a per-shot novelty contest. Reuse stages, colors, icon sets within a single video.
- **Bound by enums, not invention.** When in doubt about a value, prefer an existing enum member over inventing a new keyword. If you genuinely need a new value, surface it to the user as a schema-extension proposal — don't silently invent.

## Constraints

- No real-time 3D rendering in v0.2 (Three.js scenes can be embedded but at performance cost; profile early)
- No talking-head generation — bring your own video clip; composite in CapCut as finishing pass
- Headless Playwright capture limits frame rate; heavy overlays + many video elements + filters can drop frames before they drop quality
- Audio is always muxed in post; the browser doesn't actually play during capture (same constraint as slide-video.skill)
- Inherits `slide-video.skill v2` reveal-sync drift bug if not fixed first (Mermaid async render + edge-tts leading-silence offset). See `feedback_fix_revise_before_building.md` — decide explicitly whether to fix upstream or accept inheritance before authoring real content.

## Open / TBD

- **Stage asset pipeline** — which renderer for the initial stage assets (Spline, Blender, hand-drawn SVG/PNG)? Need at least one rendered stage (CRT, since it's the OpenClaw demo target) to validate end-to-end.
- **Performance ceiling** for parallel video elements + GSAP transforms + CSS filters in headless Chromium. Profile on first demo.
- **Cross-repo dependency story** for the Instant-Presentation gesture algebra (vendor-copy vs slim-subset vs extract-to-package). Punt until first demo lands; let empirical needs drive the choice.
- ~~**Upstream extension to Instant-Presentation**~~ — **DONE (2026-05-02, IP `a92da61`).** KG validator-mode iter-4 reduced the priors-laden 5-op proposal to 2 new ops + 3 structural axes: `FRAME` (continuous-param camera, replaces the local CAMERA sub-ops), `HANDOFF` (parametric transition, replaces the 6 TRANSITION sub-kinds), `ANNOTATE` (cursor/highlight overlay), plus `pacing` block, `grouping`, and `bind_to` as cross-cutting modifiers. Smaller and more general than the local-v0.1 surface; subagent-as-cold-substrate produced the reduction. SKILL.md updated in `7055466`. Local v0.1 ops deprecated.
- **First demo target:** reproduce the OpenClaw zoom-out reveal (CRT close-up → zoom out → 5 icons appear with lines drawing in, all sentence-synced). One shot exercises stage + content + node-graph reveal + camera move + transition simultaneously.
- ~~**`chapter_nav` per-scene highlighting**~~ — **CLOSED in v0.2.1.** Implemented via explicit per-scene `chapter: <item-name>` field in Scene fields table. Sticky semantics (stays until next scene overrides). Auto-tracking by scene index can land later if needed; explicit reads cleaner for now since not every scene maps 1:1 to a chapter.
- ~~**`camera.start: hold` validity rule**~~ — **CLOSED in S35+5.** Documented in the Camera shape section: `hold` is well-defined only with `transition_in: hold-from-previous` or `morph-from-previous`; any other `transition_in` triggers a `console.warn` from the interpreter and falls back to `static`. `camera.end: hold` has no comparable corner.

## Install (one-time, Windows)

```bash
pip install -r requirements.txt
playwright install chromium
```

ffmpeg must be in PATH (same as slide-video.skill).

## Origin

Synthesis of three existing artifacts:
- `slide-video.skill` — edge-tts + sentence-boundary timing primitive (v2.0.1, sibling skill in this repo)
- `holbizmetrics/Instant-Presentation` — 33-primitive gesture algebra + interpreter + scene graph + narrative cursor
- `holbizmetrics/ai-dopters-visualizer` — Three.js post-processing stack (UnrealBloomPass, chromatic aberration, grain) for cinematic polish

Plus the methodological insight: **containers are animated, content is real.** The "look 3D" is bought once per stage as a pre-rendered hero asset; everything else is cheap programmatic overlay. ~90% of each new video is overlay authoring on a fixed stage library.

The 33-primitive algebra was empirically validated against 40,000 lines of CS50 lecture content in Instant-Presentation. This skill extends it with animation-timing, camera, and filter ops needed for video output (vs Instant-Presentation's live speech-driven mode).

See `DESIGN.md` for architectural decisions, validation methodology (n=1 OpenClaw + KG falsifier), exit criteria, and deferred scope.
