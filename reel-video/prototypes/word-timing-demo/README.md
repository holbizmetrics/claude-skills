# Word-timing demo (F4 wiring reference)

Demonstrates the per-word timing path: edge-tts produces audio + a
single `SentenceBoundary`; an interpolation step produces per-word
timestamps; the demo HTML plays the audio with a real-time
word-highlight overlay so you can ear-check sync quality.

## Why this exists

The F8 (SFX) and F9 (animated captions) commits both stated that
`build.py` would consume `WordBoundary` events from edge-tts. That
turned out to be false: edge-tts 7.2.8 emits only `SentenceBoundary`
across all five voices in the shortlist (Aria / Guy / Jenny / Emma /
Sonia, all silent on WordBoundary). F4 closure rebuilds on a
backend-agnostic schema so the YAML doesn't change between resolvers.

## Backends

| Backend | Status | Cost | Accuracy |
|---|---|---|---|
| `char-count-uniform-v1` | **Implemented (default)** | Zero deps. Distribute the sentence span across words by character count. | Approximate. Off by 100–300 ms on emphasis words. Fine for "spread events across the line" |
| `forced-alignment` | Slot (opt-in) | Heavy. Whisper-X or aeneas runtime; one-time model download. | Word-precise (~50 ms) |
| `edge-tts-wordboundary` | Currently broken upstream | Zero (would-be). | Word-precise (~50 ms) — re-enable when edge-tts emits WordBoundary again |

The schema is the same across all three. `build.py` picks per config / availability.

## Run it

```bash
# 1. Re-build the demo data (regenerates sample.mp3 + sample-timing.json)
python build_demo.py "Your sentence here." --voice en-US-AriaNeural --out-dir .

# 2. Open preview.html in a browser, click Play.
```

Watch the spoken word against the highlighted word in the table. With
`char-count-uniform-v1` you'll see drift on short words ("in", "ten") —
they're allocated less time than they actually take. The drift is real,
documented, and bounded.

## Schema (proposed)

`at_word` becomes a peer to `at_sentence` in the gesture common-fields
table. Either form lands a gesture / SFX / caption-style change at the
chosen instant:

```yaml
- gesture: PLACE
  element: highlight
  at_word: { sentence: 0, word: 3 }   # 4th word of 1st sentence
  delay: 0.05
```

If a YAML doesn't specify `at_word` anywhere, the build doesn't need a
word-timing resolver at all — F4 stays inert and free until used.

## What this demo proves

1. edge-tts 7.2.8 returns enough timing info (sentence offset+duration) to drive a v1 word interpolation.
2. The interpolation logic is short (~30 lines of Python) and easy to swap for a forced-alignment backend later.
3. Per-word visual highlights against real spoken audio *do* sync well enough at this default — the eye/ear test passes for non-emphasis-critical content.
4. The schema (`at_word: {sentence, word}`) is independent of the backend, so future improvements don't break authored YAML.
