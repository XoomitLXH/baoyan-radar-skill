# Repository layout and privacy

Recommended layout for a public GitHub repository:

```text
baoyan-radar/
├── SKILL.md
├── .gitignore
├── scripts/
│   └── baoyan_radar.py
├── references/
│   ├── profile.example.json
│   ├── targets.example.json
│   └── privacy-and-layout.md
├── config/
│   ├── profile.local.json      # untracked
│   └── targets.local.json      # untracked
└── state/
    └── radar.db                # untracked
```

## Public vs private

Commit:

- code
- example config
- schema docs
- test data with fake values

Do not commit:

- real profile data
- real target list if it reveals private strategy
- Feishu webhook URL
- exported results containing the user's info
- local SQLite state

## Suggested `.gitignore`

```gitignore
config/*.local.json
.env
state/
__pycache__/
*.pyc
```

## Practical rule

Treat `references/*.example.json` as public templates.
Treat `config/*.local.json` as the real private inputs.
