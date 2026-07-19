# pricing-101-mock — hand-coded reference (no grammar pair yet)

Hand-coded reference prototype demonstrating the editorial-illustration patterns
that the n=2 KG-iter-5 dissection on Greg Isenberg's "Pricing 101 (How to price
your product)" surfaced (2026-05-04).

**This is the second of two complex prototypes in the skill.** First is `video-mock.html`
(OpenClaw zoom-out reveal — n=1, fully grammar-paired). This is `pricing-101-mock.html`
(n=2, hand-coded only — grammar pair pending interpreter generalization).

## What it shows

Three scenes (~22s total) covering the editorial-illustration register:

1. **Tiled $-coin grid** (0–7s) — opening hook. 54 coins on a jittered grid in
   alternating green-mid / green-dark, value cycling through `$498 → $207 → $170 → $498`,
   gentle drift parallax. Demonstrates the **repeated-token / replicate-with-jitter**
   pattern (DESIGN.md item 10 / KG axis: editorial-primitive elevation).

2. **Bicolor split + Price bubble** (7–12s) — the page splits into a
   beige top half / green bottom half (vertical scaleY animation), then a paper-white
   bubble emerges from the seam containing italic-serif "Price". Demonstrates the
   **page-as-composition** pattern (DESIGN.md item 9, model-deep) — there is no
   stage container; the page itself is the artwork.

3. **Pie chart + elbow-arrow callout** (12–22s) — a near-full dark-green pie with
   coral 5% and green 1/10 accent slices, with a hand-drawn elbow-arrow callout
   pointing up to a label `the value you create` rendered in dark-serif with
   "value" in italic-script green. Demonstrates **mixed-typography in a single
   text element** (DESIGN.md item 12), **elbow-arrow callout** (DESIGN.md item 11
   `kind: elbow-arrow`), and **hand-drawn-aesthetic stroke style** (DESIGN.md
   item 13 `style: hand-drawn`).

## What it does NOT have

- **No grammar-driven counterpart** (no `pricing-101-mock.yaml` + grammar HTML).
  The current `gesture-interpreter.js` is hardcoded to OpenClaw's HTML structure
  (stages `#stage` / `#stage-2`, icon-pattern selectors, single-annotation
  `#annotation` element). Pricing-101-mock has none of those — it has bicolor
  panels, repeated coins, pie chart slices, elbow-arrow callout. Generalizing the
  interpreter to handle this is its own arc (DESIGN.md exit criterion #7).

- **No real edge-tts narration sync.** The timeline is hand-tuned wall-clock,
  not driven by sentence boundaries. When `build.py` lands, the YAML-grammar version
  would wire to edge-tts.

- **No real charts as data-driven primitives.** The pie chart is a single SVG
  with three pre-baked path elements; slices are revealed by tweening opacity/scale,
  not by data-driven sweep. Item 10 in DESIGN.md (editorial-illustration primitive
  elevation) is what would make pie charts a first-class element type.

- **Not n=3.** Per the KG-iter-5 verdict, n≥3 dissections are still required
  before the gap-list and the Path X vs Y architectural decision can be canonized.

## How to run

Serve from this directory (CDN-based GSAP, no other deps):

```bash
cd "<path to>/Skills/reel-video.skill/prototypes/pricing-101-mock"
python -m http.server 8767
```

Open `http://127.0.0.1:8767/pricing-101-mock.html`. Click ▶ Play.

(Or: if a server is already running on `prototypes/` root, navigate to
`pricing-101-mock/pricing-101-mock.html` from there.)

## Architectural note

This prototype was deliberately built **without** trying to use the existing
`gesture-interpreter.js` because that interpreter is OpenClaw-shaped. Forcing
Pricing-101-style content through it would have either (a) failed silently with
missing handlers, or (b) required preemptive interpreter generalization without
the Path X vs Y decision (page-as-composition lane parallel to stage-driven, vs
stages as one compositional unit among many). The honest move is hand-coded
reference now, grammar pair after the architectural call.

## Provenance

- KG-iter-5 dissection findings: `.prometheus/explore/EXPLORE-2026-05-04-kg-pricing-101-dissection.md` (in the PCL repo)
- Source video: Greg Isenberg, "Pricing 101 (How to price your product)" — 70.29s, 1080×1920
- Cold-substrate subagent's gap-list (verbatim): `.prometheus/explore/pricing-101-cold/cold-subagent-output.md`
