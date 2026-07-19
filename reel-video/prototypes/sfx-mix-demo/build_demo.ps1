<#
Re-builds the SFX mix demo. Re-synthesizes the SFX files from scratch
and mixes them with a VO carrier of your choice.

Usage:
  .\build_demo.ps1 -VoCarrier "C:\path\to\some\vo.wav" -Out "C:\path\to\out\mix.wav"

If -VoCarrier points to a video file, audio is extracted from its
first audio stream automatically.
#>
param(
  [Parameter(Mandatory=$true)][string]$VoCarrier,
  [Parameter(Mandatory=$true)][string]$Out
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$work = Join-Path $env:TEMP "reel-sfx-build-$([Guid]::NewGuid().ToString('N').Substring(0,8))"
New-Item -ItemType Directory -Path $work -Force | Out-Null

# Step 1: extract / normalize the VO carrier to 10s @ 44.1k stereo
$voNorm = Join-Path $work 'vo_normalized.wav'
ffmpeg -y -hide_banner -nostats -ss 0 -i $VoCarrier -t 10 -vn -ac 2 -ar 44100 $voNorm | Out-Null

# Step 2: synthesize whoosh
$whoosh = Join-Path $here 'sfx_whoosh.wav'
ffmpeg -y -hide_banner -nostats -f lavfi -i "anoisesrc=color=pink:duration=0.22:sample_rate=44100" `
  -af "highpass=f=400,lowpass=f=3500,afade=t=in:d=0.04,afade=t=out:st=0.18:d=0.04,volume=0.7" `
  -ac 2 $whoosh | Out-Null

# Step 3: synthesize tap
$tap = Join-Path $here 'sfx_tap.wav'
ffmpeg -y -hide_banner -nostats -f lavfi -i "sine=frequency=1800:duration=0.06" `
  -af "afade=t=in:d=0.005,afade=t=out:st=0.05:d=0.01,volume=0.55" `
  -ac 2 $tap | Out-Null

# Step 4: mix VO + whoosh @ 2.0s + tap @ 7.0s
$outDir = Split-Path -Parent $Out
if ($outDir -and -not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
ffmpeg -y -hide_banner -nostats `
  -i $voNorm -i $whoosh -i $tap `
  -filter_complex "[1:a]adelay=2000|2000[s1];[2:a]adelay=7000|7000[s2];[0:a][s1][s2]amix=inputs=3:duration=first:dropout_transition=0:normalize=0[a]" `
  -map "[a]" -ar 44100 -ac 2 $Out | Out-Null

Remove-Item -Recurse -Force $work
Write-Host "Mixed: $Out"
