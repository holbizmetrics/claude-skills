# reel-video.skill — quickstart

A Claude Skill for authoring **art-directed short-form videos** (Greg Isenberg / Mark Kashef style reels) by composing pre-rendered "stage" containers (CRT, phone, browser, polaroid, paper, terminal) with real content (footage, screenshots) and programmatic GSAP overlays (chapter nav, node graphs, smooth transitions, blur/morph/decay).

Designed around one insight: **containers are animated, content is real.** Stages are reusable assets; the content inside them is your actual footage. Transitions between scenes are first-class — not cuts.

---

## Status (v0.3, 2026-05-06)

**What works today:**

- Authoring grammar — Claude reads `SKILL.md` and writes valid `script.yaml` from a topic or rough script
- Browser-runnable prototypes — every `prototypes/*-demo/` subdir contains a hand-coded HTML reference + a YAML-driven equivalent that produces visually identical animation via `gesture-interpreter.js`
- Wired gesture set — PLACE / CONNECT / ANNOTATE (with `bracket` / `ellipse` / `underline` / `elbow-arrow` shapes on single-id or array targets) + camera (zoom-in / zoom-out / static / hold) + transitions (`morph-from-previous` / `hold-from-previous` / cut) + chapter highlighting + pause + motion-blur on PLACE entrance

**What's not done yet:**

- `build.py` — YAML → headless Playwright capture → ffmpeg mux is **not yet wired**. Output today is a runnable HTML prototype, not an MP4.
- Stage asset library — the prototypes ship CSS-faux containers (CRT etc.); production-quality 3D-rendered stage PNGs are your responsibility for now
- `forced-alignment` word timing — schema is in place; backend wiring (Whisper-X / aeneas) is opt-in, not bundled
- **Gesture interpreter is a strict subset of the schema.** SKILL.md documents the full v1.0 vocabulary; the v0.3 interpreter wires the set above. Other gestures (`MOVE`, `RESIZE`, `MUTATE`, `FRAME`, `HANDOFF`, `BIND`, `FORK`, etc.) parse cleanly but log a `console.warn` and silently no-op. **Read SKILL.md's "Coverage today (v0.3)" section before authoring** — it tabulates what's wired vs schema-only so your YAML lands on real handlers.
- **DOM is hand-coded per prototype.** The interpreter animates pre-existing DOM elements; it does not build DOM from YAML. Authoring your own reel means reusing a prototype's HTML host or writing a new one with matching element ids. The DOM-builder layer lights up alongside `build.py`.

So: **invocation spec works for the wired subset, render pipeline is stubbed, DOM is hand-paired.** If you want MP4 output today, the path is "Claude authors YAML → you screen-record the running HTML prototype." Honest framing.

---

## Install

**Claude Code:** extract the zip into your skills directory.
- User-scoped: `~/.claude/skills/` (Linux/macOS) or `%USERPROFILE%\.claude\skills\` (Windows)
- Project-scoped: `.claude/skills/` in the repo where you want the skill available

**claude.ai:** upload `reel-video.skill.zip` directly via the Skills UI (Settings → Skills → Upload).

After install, ask Claude something like:
> "Use reel-video.skill to draft a 60-second reel about [your topic]"

Claude will read SKILL.md, propose a YAML script, and (after your approval) drop it where you want.

---

## Try a prototype

Open any `prototypes/*-demo/*.html` directly in a browser — they're standalone, no server needed. The `*-grammar.html` versions load YAML through `gesture-interpreter.js` and should render identically to the hand-coded `*.html` reference. Use these as the canonical "what does this gesture look like" reference when authoring your own scripts.

`prototypes/video-mock-grammar.html` is the most complete end-to-end example.

---

## Background

Architecture synthesizes three pre-existing components: timing primitive from `slide-video.skill` (edge-tts sentence boundaries), gesture algebra from [holbizmetrics/Instant-Presentation](https://github.com/holbizmetrics/Instant-Presentation) (33 primitives + cinematic axis: FRAME / HANDOFF / ANNOTATE), post-processing stack from `ai-dopters-visualizer` (Three.js + UnrealBloomPass + chromatic aberration + grain).

Source repo: `github.com/holbizmetrics/Private-Prompts` → `Claude AI/Skills/reel-video.skill/`.

Issues / feedback welcome via the source repo.
