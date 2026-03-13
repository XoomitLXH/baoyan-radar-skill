# Quick start for cloned repos

After cloning the repository, the shortest path is either:

```bash
python3 scripts/setup_clone.py
```

or a local web UI:

```bash
python3 scripts/setup_web.py
```

The setup wizard writes only local private files:

- `config/profile.local.json`
- `config/targets.local.json`
- `state/radar.db`

These are ignored by Git and are not meant to be committed.

## What the wizard asks for

- personal academic profile
- research keywords
- Feishu webhook
- daily push time

The wizard then auto-selects preset schools based on the user's profile and inferred positioning.

## What the wizard can do automatically

- generate local config files
- install a daily scheduler for the current OS (macOS LaunchAgent or Windows Scheduled Task)
- run one immediate test scan / push
