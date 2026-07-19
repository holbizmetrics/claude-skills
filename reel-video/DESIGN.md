# reel-video.skill — design (v0.2)

Public-facing design contract. Architectural decisions, validation methodology, exit criteria, deferred scope. Read alongside `SKILL.md` (the authoring contract).

---

## 1. Architectural decisions

**Containers are animated, content is real.** The "look 3D / cinematic" is bought ONCE per stage as a pre-rendered hero asset (CRT, phone mockup, browser frame, etc.). Per-reel content is plain programmatic overlay — text, icons, charts, video clips, captions — animated via GSAP timelines synced to edge-tts sentence boundaries. This collapses the asset-library cost: ~90% of each new reel is overlay authoring on a fixed stage library, not new 3D production. **The methodological hinge.**

**Reuse, do not invent substrate.** Three pre-existing components synthesized:
- Timing primitive — `slide-video.skill` (sibling in this repo): edge-tts + sentence-boundary sync.
- Gesture algebra — `holbizmetrics/Instant-Presentation`: 33 primitives + narrative cursor + scene state, empirically validated against 40,000 lines of CS50 lecture content. Cinematic axis (FRAME / HANDOFF / ANNOTATE + pacing / grouping / bind_to) added 2026-05-02 specifically for video output.
- Cinematic polish layer — `holbizmetrics/ai-dopters-visualizer`: Three.js + UnrealBloomPass + chromatic aberration + grain. Deferred; lights up with the first rendered stage.

This skill is the *integration*, not new substrate. The leverage is that the components already existed.

**Grammar-driven over hand-coded, with a regression-test pair.** Each prototype ships in two forms:
- *Hand-coded reference* (`prototypes/<demo>.html`) — the *target* visual.
- *Grammar-driven counterpart* (`prototypes/<demo>-grammar.html` + `<demo>.yaml` + interpreter) — must produce visually identical output running the YAML through the gesture interpreter.

The pair is the canonical regression test. Adding a new gesture or schema field requires extending the test pair; visual equivalence on the new YAML against a hand-coded reference is the gate.

**Backend-agnostic timing resolver.** edge-tts 7.2.8 emits `SentenceBoundary` only; `WordBoundary` is silent across the five-voice shortlist. Per-word timing comes from a resolver that backs into one of three swap-in implementations (`char-count-uniform-v1` default, `forced-alignment` opt-in, `edge-tts-wordboundary` re-enable when fixed upstream). Authored YAML schema (`at_word: {sentence, word}`) is identical across backends — switching resolvers does not invalidate authored content.

**Talking-head A-roll deferred to scope-expansion.** v0.2 explicitly excludes talking-head generation (`Constraints` section). F1+F3 (talking-head A-roll integration + anchored overlay) lift this constraint when authoring needs it; not just-the-next-F.

---

## 2. Stage catalog

**v0.2 stages**: none first-class. Prototypes use CSS-faux mockups (the OpenClaw demo's CRT is HTML+CSS borders+gradients, not a rendered asset).

**Production stages** ship as pre-rendered hero PNGs under `assets/stages/`, one PNG per stage. Renderer choice (Spline, Blender, hand-drawn SVG, curated source) deferred to first-demo time — empirical authoring needs drive the choice.

**Themed primitives are NOT stages.** Mascots, fake-window mockups, branded icons, etc. ride the existing `PLACE` machinery via a top-level `assets:` map (or per-scene). No grammar change; no new stage type. Promotion to first-class stage only when authoring repeatedly needs the same primitive across reels — the empirical-need rule.

See SKILL.md "Themed primitives without a stage" for the worked PLACE+SVG pattern. F6+F7 in the n=1 OpenClaw gap-list landed via this pattern (commit `a5b1a9f`).

---

## 3. Gesture vocabulary

**Inherited from Instant-Presentation** (`core/gesture.js`, `core/gesture_interpreter.js`). 33 primitives + the cinematic axis added 2026-05-02:

| Group | Ops |
|---|---|
| Spatial | `PLACE`, `MOVE`, `CONNECT`, `STACK`, `SPLIT`, `MERGE`, `GROUP`, `UNGROUP` |
| Camera (cinematic axis) | `FRAME` (continuous-param: pan/zoom/focus/dolly via params, supersedes the v0.1-local CAMERA sub-ops) |
| Transition (cinematic axis) | `HANDOFF` (parametric: `kind` ∈ {hold, morph, dissolve, cut, wipe, slide}, supersedes v0.1-local TRANSITION sub-kinds) |
| Annotation (cinematic axis) | `ANNOTATE` (cursor / highlight / arrow overlay) |
| ... | ... (see IP `core/gesture.js`) |

**Common fields** (any gesture): `gesture`, `at_sentence` *or* `at_word`, `reveal`, `duration`, `easing`, `delay`.

**Cross-cutting modifiers** (from cinematic axis): `pacing` block (per-op or per-scene), `grouping` (collapse list-taking ops by group key), `bind_to` (anchor an overlay to another element).

**No reel-video-specific ops.** Anything that looks reel-video-specific must justify itself either as (a) a parameter on an existing IP op, or (b) a candidate for upstream contribution to IP, not a local extension. The S35+1 KG validator-mode iter-4 established this: priors-laden 5-op local proposal collapsed to 2 ops + 3 axes when run through cold-substrate falsification, and those 2+3 belonged upstream.

---

## 4. Scaffolds (recipes, not frames)

**v0.2 ships one scaffold**: the OpenClaw zoom-out reveal pattern (CRT close-up → zoom out → 5 icons appear with lines drawing in, all sentence-synced). One shot exercises stage + content + node-graph reveal + camera move + transition simultaneously. Lives in `prototypes/video-mock.{html,yaml}` + `prototypes/video-mock-grammar.html`.

Scaffolds are **named recipes**, not enforced shapes. Authors can deviate freely (different transition pattern, no zoom-out, captions-driven, talking-head-only when F1+F3 lands, etc.).

**KG-named falsifier still active**: n≥3 dissections of distinct Greg-style reels required before treating any scaffold list as canonical. Current n=1, OpenClaw-scoped. Different reels (TH-only, captions-heavy, no-mascot) may surface different dominant gaps and different scaffold patterns.

---

## 5. Sync tiers

| Tier | Field | Source |
|---|---|---|
| Scene-level | `scene.duration` | YAML-authored or computed from sentence boundaries |
| Sentence-level | `at_sentence: int \| start \| end` | edge-tts `SentenceBoundary` events |
| Per-word | `at_word: {sentence, word}` | timing resolver (see §6) |

`at_sentence` is sufficient for everything except emphasis-aligned cuts and animated captions; `at_word` is opt-in on top.

If a YAML never uses `at_word` (and uses no animated-caption style), `build.py` skips the per-word resolver entirely. F4 stays inert and free until used.

---

## 6. Timing resolver

The F4 closure (commit `a05a5c3`, 2026-05-04). edge-tts 7.2.8 does not emit `WordBoundary` events — verified across the five-voice shortlist (Aria / Guy / Jenny / Emma / Sonia). Earlier F8 + F9 SKILL.md copy claiming `build.py` walks `WordBoundary` events was false; F4 closes the gap by replacing all such references with the backend-agnostic resolver.

| Backend | Default? | Cost | Accuracy |
|---|---|---|---|
| `char-count-uniform-v1` | **Yes** | Zero deps | Off by 100–300 ms on emphasis words. Distributes the sentence's known span across words by character count. |
| `forced-alignment` | Opt-in | Heavy: Whisper-X or aeneas runtime + one-time model download | Word-precise (~50 ms). |
| `edge-tts-wordboundary` | Currently broken upstream | Zero (would-be) | Word-precise (~50 ms) — re-enable when edge-tts emits `WordBoundary` again. |

Schema (`at_word: {sentence, word}`) is identical across backends. `build.py` picks per project config / availability.

Working reference: `prototypes/word-timing-demo/` — real edge-tts audio + Python build script + preview.html with live word-highlight overlay against the timing table for ear-check.

---

## 7. Voice + audio + captions + SFX

**Voice**: edge-tts (inherited from slide-video.skill). Curated shortlist with `conversational` (en-US-AriaNeural) default. Same voice configuration semantics as slide-video.

**SFX layer** (F8, commit `c29d936`): per-cue audio overlays muxed into the final audio track via ffmpeg `amix` alongside narration. Authored at `at_sentence` or `at_word` granularity; per-cue gain, fade, loop. Mix uses `amix=normalize=0` so narration level is unaffected.

**Animated captions** (F9, commit `93ff946`): on-screen subtitle layer rendered into the video at composition time. Four styles: `word-pop` (default), `slide-up`, `karaoke`, `bounce`. Per-word transitions driven by the timing resolver (§6). Independent of the `--captions` build flag, which separately emits a `.vtt` sidecar for player-rendered subtitles.

**Background variety** (F5, commit `f241814`): `lined-notebook` + `dark-green` added to the `background` enum based on n=1 OpenClaw frames 7–8 (lined-notebook for floating UI annotation) and frame 22 (dark-green as closing-product mockup canvas).

---

## 8. Cinematic polish layer (deferred)

The Three.js + UnrealBloomPass + chromatic aberration + grain stack from `ai-dopters-visualizer` is the polish path for stage rendering at production time. Not active in v0.2 prototypes — they use plain CSS-faux stages with no post-processing.

Lights up when the first real stage asset lands. The polish layer is per-stage and runs at stage-render time, not per-frame at composition time — keeps the composition step (Playwright capture + ffmpeg mux) cheap.

---

## 9. Validation methodology

**Hand-coded + grammar-driven prototype pair** (see §1). Required for each new gesture vocabulary extension or schema addition: hand-code a target, grammar-drive the same output from YAML, verify visual equivalence by DOM inspection. v0.2 baseline validated on the OpenClaw zoom-out reveal pair (S35, 2026-05-01).

**n=1 OpenClaw dissection** (KG protocol run, S35-2026-05-04). 56.7 s reference reel, 1080 × 1920, 24 fps. ffmpeg scene-detect at threshold 0.1 → 23 keyframes. Verdict: **OVERCLAIM-DETECTED + PARTIAL** — surface 9 gaps reduced to ~5–6 structural after FAMILY-pruning + cross-checking against current SKILL.md ground truth. Substrate Result-Leakage undischargeable in same-instance (Claude-only-authored substrate); strong form pulled to weak form.

**KG-named falsifier still active**: n≥3 dissections of distinct Greg-style reels required before treating the gap-list (and any scaffold derived from it) as canonical. Different reels (TH-only, captions-heavy, no-mascot) may surface different dominant gaps. Until n≥3, the F-series order and scope reflect OpenClaw-specific constraints, not Greg-style reels writ large.

**Cross-substrate / second-instance review** pending. Same arxiv-readiness rule that's parked for slide-video and acoustic-dna: don't ship to canonical-status on a single in-substrate clean pass.

**Inheritance risk**: `slide-video.skill v2` has an unresolved reveal-sync drift bug (Mermaid async render + edge-tts leading-silence offset). reel-video.skill v0.2 sidesteps it via scene-level `duration` instead of sentence-boundary in the prototype interpreter. When `build.py` wires edge-tts properly, the same bug becomes load-bearing. Fix upstream OR explicitly accept inheritance is a named decision before authoring real content.

---

## 10. Exit criteria

v0.2 → v1.0 is **done** when:

### Original (v0.2 ship)

1. **F1 + F3** (talking-head A-roll integration + anchored overlay) shipped — removes the explicit "No talking-head generation" v0.2 constraint. Scope-expansion, not just-the-next-F.
2. **`build.py` shipped** — YAML → headless Playwright capture → ffmpeg mux end-to-end. Inheritable from slide-video.skill v2 with the reveal-sync drift bug decision (fix upstream OR document inheritance) taken.
3. **Stage asset pipeline** — at least one production-quality stage asset (real 3D-rendered, not CSS-faux). Renderer choice (Spline / Blender / hand-drawn) settled empirically by which stage demands it first.
4. **End-to-end OpenClaw reproduction** through `build.py` against the v0.2 schema unchanged — validates that the schema + interpreter + build pipeline compose to a watchable MP4.
5. **n ≥ 3 dissections** of distinct Greg-style reels — discharges the KG-named falsifier. Confirms the gap-list and scaffold pattern generalize beyond OpenClaw.
6. **Cross-substrate review** completed (non-Claude or human authoring against the SKILL.md cold) — discharges the same-instance same-session provenance caveat.
7. **`gesture-interpreter.js` covers full IP gesture vocabulary** — currently demo-only (PLACE / CONNECT / ANNOTATE + camera + hold/morph transitions). Production needs all 33 + cinematic axis, with handlers for FRAME / HANDOFF / ANNOTATE / pacing / grouping / bind_to wired in.
8. ~~**`camera.start: hold` validity rule** documented~~ — **CLOSED in S35+5 (2026-05-05).** SKILL.md Camera shape section now specifies: `hold` is well-defined only with `transition_in: hold-from-previous` / `morph-from-previous`; any other `transition_in` triggers `console.warn` from the interpreter and falls back to `static`. `camera.end: hold` is well-defined regardless of `transition_in` (means "no camera move this scene").

### From n=2 dissection (Pricing 101, KG-graded REFRAMED+PARTIAL Tier 2, 2026-05-04)

Items 9–15 surfaced from the KG-Loop iter-5 cold-substrate audit on Pricing 101. Convergent-overlap success signature confirmed (substrate result-leakage guard held). Each item tagged as **additive** (extends existing model) or **model-deep** (requires architectural decision). Whether all land in v1.0 depends on the **Path X vs Path Y decision** (see below).

9. **Page-as-composition primary axis** — *model-deep*. v0.2's "stage + content + overlays" abstraction is OpenClaw-shaped. Pricing 101 doesn't use a stage container in 70 seconds — every shot is direct compositing of editorial-illustration shapes + typography + multi-zone color geometry on the page itself. v1.0 needs first-class support for "the page is the composition," parallel to (or supplanting) the stage-driven lane.
10. **Editorial-illustration primitive elevation path** — *model-deep*. The schema's *primary visual currency* in editorial reels is illustration primitives (thermometer, pie, bar, capsule meter, Venn cluster, character-as-bar) — none of which are stage-shaped or real-content. v0.2 has PLACE+SVG as escape hatch but loses animatable-element advantages. v1.0 needs a schema mechanism for "elevate this category to first-class element type" without requiring stage-catalog promotion.
11. **Region/span annotations** — *additive*. **Schema documented in SKILL.md** (2026-05-04, S35+2): `target` accepts `<id>` / `{element, span}` / `[ids]`; `kind` enum extended to `arrow` (default) / `bracket` / `elbow-arrow` / `ellipse` / `underline`; `options.style: 'clean' | 'hand-drawn'`. **Split into 11a / 11b / 11c for staged landing.** **11a (group-bracket via array target) landed S35+5 (2026-05-05):** `computeFrameBBox` + `ensureOverlaySvg` + `drawGroupBracket` helpers added to `gesture-interpreter.js`; ANNOTATE handler dispatches on `Array.isArray(params.target)`. Regression test pair at `prototypes/group-bracket-demo/`. **11b (point-attached bracket / ellipse / elbow-arrow / underline shapes) landed S35+5:** `drawEllipse`, `drawUnderline`, `drawElbowArrow` helpers added; ANNOTATE dispatch extended to `kind ∈ {bracket, ellipse, underline, elbow-arrow}` on single-id targets; single-id + `kind: bracket` reuses `drawGroupBracket` on the single bbox. `elbow-arrow` accepts `options.labelOffset: {x, y}` for label placement; arrow tip lands on **edge-midpoint** of the bbox edge facing the label (vertical-bias heuristic: `|offset.y| > |offset.x| * 0.7` → top/bottom midpoint, else side midpoint). Edge-midpoint anchoring sidesteps `border-radius` rounded-corner gap that corner-exact anchoring suffered (any element with rounded corners — and the icons all have `border-radius: 36px` — leaves the bbox corner in background pixels, so a tip at the bbox corner looks detached). Regression test pair at `prototypes/annotate-shapes-demo/` covers all four kinds in one scene. v0.2 limitation: bbox uses element resting positions (data-tx/data-ty) — does not follow elements that move during the scene; revisit when MOVE handler lands. **11c (span resolution within element — `{element, span}` form) pending — last; touches per-element-type unit logic.** **Hand-drawn engine** for all 11a + 11b shapes (rough.js wiring) is the engine half of #13. **IP upstream candidate** — n=2 evidence (OpenClaw + Pricing 101 both surface the gap) supports promotion in a future KG validator-mode iteration.
12. **Inline rich-text caption styling** — *additive*. **Part 1 (per-word face / color / weight) landed S35+5 (2026-05-05).** SKILL.md `Caption emphasis (per-word rich-text)` subsection added: `emphasis` array now accepts either bare strings (F9 behavior, style-default tint) or per-word objects `{word, face?, color?, weight?}` overriding face / color / weight on top of the base style. Schema decision: object array (per the schema-shape decision in S35+5) over markdown-in-yaml — the rest of the schema is field-typed objects, B would've introduced a parser for one feature only and broken consistency. Per-word objects compose cleanly with the per-word timing resolver (`at_word`). Captions preview at `prototypes/captions-preview.html` updated to alternate two sentences — row 1 bare-string F9, row 2 per-word rich-text — across all four caption styles. **Part 2 (animated mark-on-text — strikethrough drawing across a phrase with one word kept un-struck) parked** — not in v0.2 schema; surfaces when build.py renderer ships and a real reel needs it. **IP upstream candidate.**
13. **Hand-drawn visual register as global axis** — *additive but systematic*. **Schema documented in SKILL.md** (2026-05-04, S35+2): top-level `style: 'clean' | 'hand-drawn'` field, default `clean`. Composes with item 11's ANNOTATE `options.style` (per-mark override), with the existing `chapter_nav.style`, with CONNECT stroke style, and with caption mark style. Per-primitive overrides always win; global is the default. **Cascade plumbing landed** (2026-05-05, S35+5): `resolveStyle(spec, primitiveStyle)` exposed on `GestureInterpreter`; `document.body.dataset.style` carries the global resolved value at run start; cascade-resolution sanity tests at `prototypes/style-cascade-demo/style-cascade.html`. **Hand-drawn rendering engine pending** — lights up alongside item 11's bracket / ellipse / underline shapes (rough.js wiring shared across CONNECT / ANNOTATE / chapter_nav / caption marks). Also: `chapter_nav.style` default flipped from "hand-drawn" to "inherits from global" to align with cascade (no behavior change for current prototypes since `video-mock.yaml` sets `chapter_nav.style: hand-drawn` explicitly). **IP upstream candidate.**
14. **Motion-blur as first-class entrance effect** — *additive*. **Schema documented in SKILL.md** (2026-05-04, S35+2): `motion_blur` lands as a structural axis (peer to `pacing` / `grouping` / `bind_to`), not just a PLACE field. Forms: `false` (default) / `true` (default amount) / `<px>` / `{ px, decay }`. Cuts across PLACE / MOVE / FRAME / HANDOFF — anywhere with transit motion. Distinct from `pacing.curve` (velocity profile) and `HANDOFF.kind: blur_decay` (scene-boundary effect). **Interpreter handler landed for PLACE** (2026-05-05, S35+5): `applyMotionBlur` helper + call-site on PLACE, regression test pair at `prototypes/motion-blur-demo/` covering all four schema forms. Helper ready for replication onto MOVE / FRAME / HANDOFF when those handlers land. **IP upstream candidate.**
15. **Sub-scene beat granularity** — *possibly model-deep, deferred decision*. v0.2's "scene" unit is one stage-content pairing. Editorial reels have continuous intra-page choreography where beats happen inside one composition without "scene boundaries" being meaningful. May reduce to extending pacing modifier OR may require a finer authorial unit. Investigate during v1.0 design.

### Path X vs Path Y decision

Items 9 and 10 are model-deep, not additive. v1.0 requires an explicit decision before items 9–10 can land:

- **Path X (extend):** Add a "page-as-composition" lane parallel to "stage + content + overlays." Both lanes coexist; authors pick per video. Stage-driven model unchanged; new model added as sibling.
- **Path Y (rethink):** Stages become one compositional unit among many. Page-as-composition becomes primary; stage-driven becomes a special case. Schema's mental model shifts from "stage hosts content" to "page composes elements (some of which are stages)."

**Decision deferred until n=3 dissection completes** (item 5). A third stylistic axis (talking-head-led OR list-format OR captions-heavy) may surface a Path Z that neither extends nor rethinks but suggests a different decomposition.

### Generality test (#5 emphasized)

#5 is the actual generality test — the skill is general iff the second and third reel's gap analyses don't require modifying the schema the first one used. **n=2 already shows v0.2 fails this for Pricing 101** (the model-deep items 9-10 *are* schema modifications). The interesting question is whether v1.0 design (post Path X/Y decision) holds at n=3.

### Validation status at v0.2 ship

- Criteria architectural / prototype: hand-coded + grammar-driven equivalence verified for OpenClaw scaffold; F2 / F4 / F5 / F6+F7 / F8 / F9 closed.
- Criteria 1–8: open. v0.2 = "schema + gesture algebra + prototype-pair pattern in place; full validation pending the first real reel through `build.py`."
- Criteria 9–15: surfaced via n=2 KG audit. Items 11-14 actionable now as additive features. Items 9-10 (model-deep) blocked on Path X/Y decision. Item 15 (possibly model-deep) deferred for v1.0 design investigation.

---

## 11. Deferred to v1+ / scope-expansion

- F1 + F3 talking-head A-roll integration (scope-expansion: removes "No talking-head generation" constraint).
- `build.py` production builder.
- Stage asset pipeline + first real stage rendering.
- Performance ceiling for parallel video elements + GSAP transforms + CSS filters in headless Chromium. Profile on first demo.
- Cross-repo dependency story for the IP gesture algebra (vendor-copy vs slim-subset vs extract-to-package). Punt until first demo lands; let empirical needs drive the choice.
- Cinematic polish layer activation (Three.js + UnrealBloomPass + chromatic aberration + grain) at stage-render time.
- `camera.start: hold` validity rule corner cases.
- Voice consistency tooling across multi-reel series (analogous to slide-video's deferred concept).
- Partial re-render (single scene without full Playwright pass).

---

## 12. Status

- [x] Architectural decisions locked (container/content split, grammar-driven, reuse-not-invent, backend-agnostic timing resolver, talking-head deferred)
- [x] Gesture vocabulary defined (IP 33 + cinematic axis FRAME / HANDOFF / ANNOTATE + pacing / grouping / bind_to)
- [x] Scaffold defined as recipe (OpenClaw zoom-out, deviation allowed)
- [x] Sync tiers defined (scene + sentence + per-word)
- [x] Timing resolver defined (three backends, schema-independent)
- [x] Voice + SFX + captions + background-variety defined
- [x] Validation methodology defined (prototype pair + n=1 OpenClaw + n≥3 KG falsifier + cross-substrate caveat)
- [x] Exit criteria defined (8 items)
- [x] **v0.2 SKILL.md TRIAD-cleared** (3 passes, S35)
- [x] **F2 / F4 / F5 / F6+F7 / F8 / F9 closed** (6 of 7 F-features; F1+F3 deferred as scope-expansion)
- [x] **IP cinematic axis upstreamed** (S35+1, IP `a92da61`; reel-video local v0.1 ops deprecated)
- [ ] F1 + F3 talking-head A-roll
- [ ] `build.py` shipped
- [ ] Stage asset pipeline + first production stage
- [ ] End-to-end OpenClaw reproduction through `build.py`
- [x] **n=2 dissection landed** (Pricing 101, KG-Loop iter-5, REFRAMED+PARTIAL Tier 2, 2026-05-04) — surfaced 7 new structural axes (items 9-15 above); Path X vs Y decision deferred
- [ ] n=3 dissection (third stylistic axis: talking-head-led OR list-format OR captions-heavy)
- [ ] **Path X vs Path Y decision** (architectural commitment for v1.0; gates items 9-10 landing)
- [ ] Cross-substrate / second-instance review
- [ ] `gesture-interpreter.js` full coverage (33 + cinematic axis handlers)
- [ ] Items 9-15 from n=2 audit (page-as-composition, editorial-primitive elevation, region/span annotations, inline rich-text styling, hand-drawn global, motion-blur entrance, sub-scene beat) — landings depend on Path X vs Y decision and n=3 evidence
