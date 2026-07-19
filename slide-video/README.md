# slide-video.skill

Automated narrated explainer videos. YAML script in, MP4 out.

## Stack

- **edge-tts** — free Microsoft neural TTS. Emits sentence-boundary timestamps; those become the slide transition times. No API key.
- **GSAP** — slide animations (CDN).
- **Playwright (Chromium)** — headless viewport recording, silent.
- **ffmpeg** — mux silent webm + tts mp3 into final mp4.

## Install

```bash
pip install -r requirements.txt
playwright install chromium
```

ffmpeg in PATH. Windows: `winget install Gyan.FFmpeg`.

## Run

```bash
python build.py examples/example.yaml --output out.mp4
```

Add `--work-dir ./build` to keep intermediates (mp3, html, webm, boundaries.json).

## Authoring

Claude (PCL) writes the YAML. See `SKILL.md` for the contract and authoring principles. The `examples/example.yaml` is a working reference.

## Why sync works

edge-tts emits `SentenceBoundary` events during render — sentence-start timestamps in 100-ns units. These map directly to slide transitions. There is no audio analysis, no alignment algorithm. The TTS engine already knows where the sentences are.
