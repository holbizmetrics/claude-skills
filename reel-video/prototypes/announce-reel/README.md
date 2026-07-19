# announce-reel — meta dogfood prototype

A ~16-second reel about reel-video.skill, authored *using* the skill — the YAML was written by reading SKILL.md as the executable spec. Demonstrates that the v0.3 invocation grammar produces working choreography end-to-end.

## How to view

Open `announce-grammar.html` directly in any browser. No server, no build step. The page boots `gesture-interpreter.js` (loaded from the parent `prototypes/` dir), parses the inline YAML, and animates the timeline.

## What it exercises

Stays inside the v0.3 wired-gesture set per SKILL.md "Coverage today":

- **Gestures:** `PLACE` (with `elements`, `reveal: per-step`, `stagger`), `CONNECT` (line-draws via `stroke: dashoffset`), `ANNOTATE` (legacy curved-arrow `kind`)
- **Camera:** `zoom-in` → `hold` → `zoom-out`
- **Transitions:** `hold-from-previous` (continuity), `morph-from-previous` (CRT → phone)
- **Top-level:** `chapter` highlighting (sticky across scenes), `pause` (silent beats), `narration` (first-sentence → caption)

8 scenes, 6 chapters, 5 sentences of narration. No schema-only gestures referenced (no `MOVE` / `FRAME` / `HANDOFF` / etc.) — every YAML statement lands on a real handler.

## DOM coupling — why this prototype reuses video-mock

The interpreter animates pre-existing DOM; it does not build DOM from YAML. This prototype's HTML stage (CRT + 5 icons + phone + notif-card + annotation containers) is a **straight reuse** of `video-mock-grammar.html`'s DOM, with only narration / chapter labels / content text / notif body / annotation label changed. That keeps the dogfood honest: the YAML drives choreography, not asset construction. The DOM-builder layer lights up alongside `build.py`.

If you want a different visual stage for your own reel, write a new HTML host with matching element ids referenced by your YAML's `element` / `target` fields.

## Files

- `announce.yaml` — canonical YAML spec (the artifact author Claude would propose)
- `announce-grammar.html` — runnable host (announce.yaml inlined for `file://` compatibility)
- `README.md` — this file

## What it's missing (honest scope)

- **No audio.** `build.py` would render `narration` via edge-tts and mux it; not yet wired. Captions update at scene start via interpreter, but no voice plays.
- **No MP4.** Output is the running HTML timeline; screen-record the page to capture as video.
- **No real footage in content slots.** `content.value: "Authoring"` paints text on the CRT screen and the notif-card carries hardcoded text. In a real Greg-style reel, this slot would hold an actual screen recording or demo MP4.

That's the v0.3 surface honestly framed. Roadmap items (`build.py`, MP4 output, real-footage slots) close those gaps.
