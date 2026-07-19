"""
Build the word-timing-demo: synthesize a sentence with edge-tts and emit
both the audio file and a JSON file with the sentence-boundary metadata.

Usage:
    python build_demo.py "Your sentence here." [--voice en-US-AriaNeural]

Writes:
    sample.mp3            — synthesized audio
    sample-timing.json    — { sentence: str, offset_ms, duration_ms, words: [...] }

`words` is the interpolated per-word schedule (sentence-relative
character-count interpolation, the F4 v1 default backend). Each entry
is `{ word, start_ms, end_ms, idx }`.

This script is the build.py reference for the F4 timing path:
- edge-tts gives the audio + the sentence-level offset/duration
- interpolation produces per-word timestamps from the sentence span
- forced-alignment (Whisper-X / aeneas) is the opt-in upgrade slot;
  not implemented here.
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import edge_tts


def interpolate_word_times(sentence: str, sentence_offset_ms: float, sentence_duration_ms: float):
    """
    Distribute word start/end timestamps across a sentence's known
    (offset, duration) by character count. Uniform-pronunciation-per-char
    assumption — wrong by 100-300 ms on emphasis words, fine for general use.
    """
    # Tokenize words; keep terminal punctuation attached to the last word
    words = re.findall(r"\S+", sentence)
    if not words:
        return []

    # Character widths (treat each token as its raw length; punctuation is fine)
    widths = [len(w) for w in words]
    total = sum(widths)

    out = []
    cum = 0
    for i, w in enumerate(words):
        rel_start = (cum / total) * sentence_duration_ms
        cum += widths[i]
        rel_end = (cum / total) * sentence_duration_ms
        out.append({
            "idx": i,
            "word": w,
            "start_ms": round(sentence_offset_ms + rel_start, 1),
            "end_ms": round(sentence_offset_ms + rel_end, 1),
        })
    return out


async def synthesize(text: str, voice: str, audio_out: Path):
    boundaries = []
    communicate = edge_tts.Communicate(text, voice)
    with open(audio_out, "wb") as f:
        async for chunk in communicate.stream():
            t = chunk.get("type")
            if t == "audio":
                f.write(chunk["data"])
            elif t in ("SentenceBoundary",):
                boundaries.append({
                    "type": t,
                    "offset_ms": chunk["offset"] / 10_000,
                    "duration_ms": chunk["duration"] / 10_000,
                    "text": chunk.get("text", ""),
                })
    return boundaries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sentence", help="Sentence to synthesize")
    ap.add_argument("--voice", default="en-US-AriaNeural")
    ap.add_argument("--out-dir", default=".", help="Output directory (default: cwd)")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    audio = out_dir / "sample.mp3"
    timing = out_dir / "sample-timing.json"

    boundaries = asyncio.run(synthesize(args.sentence, args.voice, audio))

    if not boundaries:
        print("WARNING: no SentenceBoundary events emitted", file=sys.stderr)
        return 1

    # Use first sentence boundary; reels typically use one sentence per scene-segment anyway
    sb = boundaries[0]
    payload = {
        "sentence": args.sentence,
        "voice": args.voice,
        "sentence_offset_ms": sb["offset_ms"],
        "sentence_duration_ms": sb["duration_ms"],
        "all_sentence_boundaries": boundaries,
        "interpolation_backend": "char-count-uniform-v1",
        "words": interpolate_word_times(args.sentence, sb["offset_ms"], sb["duration_ms"]),
    }

    timing.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"audio:  {audio}")
    print(f"timing: {timing}")
    print(f"  sentence_offset_ms={payload['sentence_offset_ms']}, sentence_duration_ms={payload['sentence_duration_ms']}")
    print(f"  word count: {len(payload['words'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
