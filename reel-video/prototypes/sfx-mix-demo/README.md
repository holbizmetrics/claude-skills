# SFX mix demo (F8 wiring reference)

Demonstrates the audio-mix step that `build.py` will need when the
`sfx:` field lands. Validated 2026-05-04 — produces a working mixed
audio file from a VO carrier + 2 SFX events scheduled at known
timestamps.

## What's in this folder

- `sfx_whoosh.wav` — 220ms band-pass-filtered pink noise (synthesized).
  Stand-in for a transition whoosh.
- `sfx_tap.wav` — 60ms 1.8 kHz sine (synthesized). Stand-in for a
  UI-element-arrival tap.
- `build_demo.ps1` / `build_demo.sh` — re-synthesize the SFX files and
  run the mix from a VO carrier of your choice.

## How to re-run

```powershell
# PowerShell
./build_demo.ps1 -VoCarrier "path\to\some\vo.wav" -Out "out\mix.wav"
```

```bash
# Bash
./build_demo.sh path/to/some/vo.wav out/mix.wav
```

The script regenerates the synthesized SFX files, then mixes them with
the supplied VO carrier at hard-coded timestamps (whoosh @ 2.0s, tap @
7.0s) so the output is ~10 seconds long.

## The wiring (annotated)

The mix is one ffmpeg call:

```
ffmpeg -i VO -i WHOOSH -i TAP \
  -filter_complex "
    [1:a]adelay=2000|2000[s1];        # whoosh, delayed to 2.0s on both channels
    [2:a]adelay=7000|7000[s2];        # tap, delayed to 7.0s
    [0:a][s1][s2]amix=
      inputs=3:
      duration=first:                 # mix is as long as the VO; SFX trimmed/padded
      dropout_transition=0:
      normalize=0                     # keep VO levels; don't auto-attenuate
    [a]
  " \
  -map "[a]" -ar 44100 -ac 2 OUT.wav
```

`adelay=Nms|Nms` shifts each SFX into its slot. `amix` merges the three
streams without re-normalising — VO stays at original gain, SFX gets
mixed in at whatever pre-volume the input file has. Per-SFX volume can
be tuned in two places: at synth time (`volume=` filter on the source)
or at mix time (`[s1]volume=0.5[s1v]` between `adelay` and `amix`).

## How `build.py` should consume the YAML

Given a scene like:

```yaml
- id: chapter-2
  stage: phone
  sfx:
    - src: ./assets/whoosh.mp3
      at_sentence: 0
      delay: 0.18
      volume: 0.55
    - src: ./assets/tap.mp3
      at_sentence: 2
      volume: 0.4
  narration: |
    First sentence is here.
    A second one follows.
    The tap fires here on sentence three.
```

…build.py walks the scene's sentence-boundary list (already produced
by edge-tts), maps `at_sentence: N` + `delay` to an absolute timestamp,
and emits one `[k:a]adelay=Tms|Tms,volume=V[sk]` chain per SFX cue,
plus one `amix=inputs=N+1:...` over them all. Same shape as this demo,
just generated rather than hand-written.

## Why synthesized SFX in the prototype

So this folder is self-contained — no licensed assets, no broken
relative paths if you grab the skill from another machine. Real
productions should drop in real SFX (Greg-style reels typically use
Splice / Soundsnap / GarageBand stock libraries).

The synthesized whoosh is intentionally subtle. Real production
whooshes layer multiple noise bands + a pitched element + a transient
tail; this is one band-pass on pink noise. It's enough to verify the
pipeline, not to ship as-is.
