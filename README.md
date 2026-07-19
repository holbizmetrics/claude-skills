# claude-skills

Self-authored [Claude Code skills](https://code.claude.com/docs/en/skills) by
[holbizmetrics](https://github.com/holbizmetrics), one folder per skill. Install by copying a
skill folder into `~/.claude/skills/`.

| Skill | What it does |
|---|---|
| [reel-video](reel-video/) | Art-directed short-form video (MP4 + interactive HTML): pre-rendered stage containers (CRT, phone, browser, polaroid, paper, terminal) + real content + GSAP overlay timeline, edge-tts sentence-sync narration, Playwright capture, ffmpeg mux. |
| [slide-video](slide-video/) | YAML in → narrated slide video out: single-file interactive HTML (play/pause, scrubbing, captions, EN/DE bilingual toggle, copy buttons, mermaid/KaTeX) + MP4/MP3 via edge-tts and Playwright capture. |

More skills incoming (music-video) as they're cleaned for publication.

## Layout

Each skill ships its authoring contract (`SKILL.md`), design doc (`DESIGN.md`) where one
exists, its build tooling, and examples. Skills are collected here while they're small;
one that grows independent life graduates to its own repo with a pointer left behind.
