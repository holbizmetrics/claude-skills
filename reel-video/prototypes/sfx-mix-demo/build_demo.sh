#!/usr/bin/env bash
# Re-builds the SFX mix demo. Re-synthesizes the SFX files from scratch
# and mixes them with a VO carrier of your choice.
#
# Usage:
#   ./build_demo.sh path/to/some/vo.wav path/to/out/mix.wav
#
# If the first argument points to a video file, audio is extracted
# from its first audio stream automatically.

set -euo pipefail

VO_CARRIER="${1:?usage: $0 VO_CARRIER OUT}"
OUT="${2:?usage: $0 VO_CARRIER OUT}"

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Step 1: extract / normalize the VO carrier to 10s @ 44.1k stereo
ffmpeg -y -hide_banner -nostats -ss 0 -i "$VO_CARRIER" -t 10 -vn -ac 2 -ar 44100 "$WORK/vo_normalized.wav" >/dev/null

# Step 2: synthesize whoosh
ffmpeg -y -hide_banner -nostats -f lavfi -i "anoisesrc=color=pink:duration=0.22:sample_rate=44100" \
  -af "highpass=f=400,lowpass=f=3500,afade=t=in:d=0.04,afade=t=out:st=0.18:d=0.04,volume=0.7" \
  -ac 2 "$HERE/sfx_whoosh.wav" >/dev/null

# Step 3: synthesize tap
ffmpeg -y -hide_banner -nostats -f lavfi -i "sine=frequency=1800:duration=0.06" \
  -af "afade=t=in:d=0.005,afade=t=out:st=0.05:d=0.01,volume=0.55" \
  -ac 2 "$HERE/sfx_tap.wav" >/dev/null

# Step 4: mix VO + whoosh @ 2.0s + tap @ 7.0s
mkdir -p "$(dirname "$OUT")"
ffmpeg -y -hide_banner -nostats \
  -i "$WORK/vo_normalized.wav" -i "$HERE/sfx_whoosh.wav" -i "$HERE/sfx_tap.wav" \
  -filter_complex "[1:a]adelay=2000|2000[s1];[2:a]adelay=7000|7000[s2];[0:a][s1][s2]amix=inputs=3:duration=first:dropout_transition=0:normalize=0[a]" \
  -map "[a]" -ar 44100 -ac 2 "$OUT" >/dev/null

echo "Mixed: $OUT"
