# Daily scheduling

Use a local scheduler so the public repository stays generic while the user's real profile and target list stay private.

## Cross-platform installer

Use the wrapper first:

```bash
python3 scripts/install_daily_schedule.py \
  --profile config/profile.local.json \
  --targets config/targets.local.json \
  --db state/radar.db \
  --hour 9 --minute 0 \
  --push-mode digest \
  --send-empty-digest
```

It auto-selects:

- macOS → LaunchAgent
- Windows → Scheduled Task (`schtasks`)

## macOS LaunchAgent

Install directly on macOS:

```bash
python3 scripts/install_daily_launch_agent.py \
  --profile config/profile.local.json \
  --targets config/targets.local.json \
  --db state/radar.db \
  --hour 9 --minute 0
```

Then load it:

```bash
launchctl unload ~/Library/LaunchAgents/ai.openclaw.baoyan-radar.daily.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/ai.openclaw.baoyan-radar.daily.plist
launchctl start ai.openclaw.baoyan-radar.daily   # optional test run
```

## Windows Scheduled Task

Install directly on Windows:

```bash
python scripts/install_windows_schtask.py ^
  --profile config/profile.local.json ^
  --targets config/targets.local.json ^
  --db state/radar.db ^
  --hour 9 --minute 0 ^
  --push-mode digest --send-empty-digest
```

Useful commands:

```bat
schtasks /Run /TN BaoyanRadarDaily
schtasks /Query /TN BaoyanRadarDaily
schtasks /Delete /TN BaoyanRadarDaily /F
```

## Recommended timing

For 保研通知监控, good default strategies are:

- once every morning for digest-style pushes
- or every 2-4 hours during summer-camp / 预推免 season if the user wants faster alerts

If the user says “每天定时推送”, prefer one daily run first, then increase frequency only if they ask.
