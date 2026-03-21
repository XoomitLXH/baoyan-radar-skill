---
name: baoyan-radar
description: Personalized local-first Chinese recommendation-exemption admissions (保研/推免) radar and workflow platform for monitoring university notice pages, collecting experience sources, filtering summer camp / 预推免 / 推免直博 announcements against a student's profile, extracting deadlines and material requirements, pushing matched alerts, supporting mentor/lab fit analysis, and serving a local dashboard. Use when creating, configuring, running, or debugging a reusable admissions-intelligence system that must keep personal profile data in local private config instead of committing it to GitHub.
---

# Baoyan Radar Platform

Build a reusable 保研情报雷达 that can be published publicly while keeping each user's personal academic profile private.

Track both:

- official admissions notices from graduate-school / college websites
- community experience and evaluation pages such as Zhihu posts,经验贴,面经汇总, or lab-evaluation pages

## Core rule

Do not hard-code the student's personal information into tracked files.

Keep public repository content limited to:

- generic monitoring code
- example config templates
- extraction and scoring logic
- local state schema

Keep private local content in untracked files such as:

- `config/profile.local.json`
- `config/targets.local.json`
- `.env`
- `state/`

## Quick start

Fastest setup for a cloned repo:

Terminal wizard:

```bash
python3 scripts/setup_clone.py
```

Local web UI:

```bash
python3 scripts/setup_web.py
```

The setup flow will:

- collect the user's private profile locally, including detailed project and competition experience
- generate `config/profile.local.json`
- generate `config/targets.local.json` from built-in school presets after auto-positioning the user into matching tiers
- optionally install the daily scheduler for the current OS (macOS LaunchAgent or Windows Scheduled Task)
- optionally run one immediate test scan / push

Manual setup from examples is still supported:

```bash
mkdir -p config state
cp references/profile.example.json config/profile.local.json
cp references/targets.example.json config/targets.local.json
```

Run one scan:

```bash
python3 scripts/baoyan_radar.py once \
  --profile config/profile.local.json \
  --targets config/targets.local.json \
  --db state/radar.db
```

Run continuous monitoring:

```bash
python3 scripts/baoyan_radar.py run \
  --profile config/profile.local.json \
  --targets config/targets.local.json \
  --db state/radar.db \
  --interval-min 60
```

Install a daily scheduled run with the cross-platform wrapper:

```bash
python3 scripts/install_daily_schedule.py \
  --profile config/profile.local.json \
  --targets config/targets.local.json \
  --db state/radar.db \
  --hour 9 --minute 0 \
  --push-mode digest \
  --send-empty-digest
```

On macOS this creates a LaunchAgent. On Windows it creates a Scheduled Task.

Run the local dashboard after building the frontend:

```bash
cd dashboard
npm install
npm run build
cd ..
python3 scripts/run_dashboard.py
```

Default address: `http://127.0.0.1:8787/`

Use the dashboard when the user needs a local platform view for filtering notices, tracking statuses, adding notes, seeing recent deadlines, or triggering scans interactively.

Analyze a single notice page:

```bash
python3 scripts/baoyan_radar.py inspect \
  --url https://example.edu.cn/notice/123
```

Score a mentor or lab page against the student's profile:

```bash
python3 scripts/baoyan_radar.py score \
  --url https://example.edu.cn/lab/pi
```

Generate a first-draft outreach email from local profile plus a mentor page:

```bash
python3 scripts/baoyan_radar.py draft-email \
  --url https://example.edu.cn/lab/pi \
  --mentor-name 张老师
```

## What the bundled script does

### `once`

- load the private student profile and monitoring targets
- fetch target pages
- extract candidate links
- separately handle `official` and `experience` sources
- match admissions / experience keywords and profile keywords
- deduplicate by URL in SQLite
- summarize matched notices or experience pages
- optionally push matched summaries to Feishu webhook
- support either `item` push mode (one message per hit) or `digest` push mode (one daily summary)

### `run`

Repeat `once` forever with a configurable interval.

### `inspect`

Fetch one page and heuristically extract:

For `official` pages:

- school / college / project title
- absolute deadline text
- required materials
- assessment form
- profile-fit score

For `experience` pages:

- background / BG-like clues
- interview or machine-test notes
- suggestions and lab / school evaluation snippets
- profile-fit score

### `score`

Fetch one mentor or lab page and compute a transparent keyword-overlap fit score using:

- target disciplines
- research keywords
- project keywords
- student project summaries

### `draft-email`

Produce a structured, reusable 套磁信草稿 using the private profile plus the fetched page context.

## Privacy model

If the user wants to publish the project on GitHub, do this by default:

1. commit only example configs from `references/`
2. add `config/*.local.json`, `.env`, and `state/` to `.gitignore`
3. never commit real student name, rank, GPA, phone, email, Feishu webhook, or target list unless the user explicitly wants that

Community-source note:

- Prefer stable page URLs, collection pages, 专栏页, or manually curated post lists over fragile site-search result pages.
- Large platforms like Zhihu may change HTML or add anti-bot protections, so keep community sources configurable and expect occasional source-specific tuning.
- By default, `experience` sources are treated as single pages and do not follow page links. Set `follow_links: true` only for curated collection pages where link expansion is actually desired.

## Tuning guidance

Prefer adding more precise target-page metadata before making the matcher more complex.

Useful tuning levers:

- source-specific include keywords
- source-specific exclude keywords
- profile research keywords
- project keywords and short project summaries
- minimum fit score threshold
- monitoring interval

## References

Read these only when needed:

- `references/profile.example.json` for the private profile schema
- `references/targets.example.json` for target-page schema
- `references/presets.cn-cs.json` for built-in CS school/source presets used by the clone-setup wizard
- `references/quickstart.md` for clone-and-run onboarding
- `references/privacy-and-layout.md` for repository layout and Git hygiene
- `references/scheduler.md` for daily scheduling on macOS and Windows
- `references/preset-expansion.md` for how to keep expanding school / college / lab / mentor presets

## Files written by the script

- SQLite DB path passed via `--db`
- optional local logs if the user redirects output or runs under a scheduler

Keep state files local and untracked unless the user explicitly wants to archive them.
