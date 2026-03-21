# Baoyan Radar Platform

Baoyan Radar Platform 是一个面向 **保研 / 推免 / 夏令营 / 预推免 / 直博** 的本地优先（local-first）情报与决策支持平台。

它把 **招生通知监控、经验信息收集、个人画像匹配、导师/实验室评估、定时任务、飞书推送** 和 **本地可视化工作台** 放到同一套工作流里，既适合个人使用，也适合继续扩展成更完整的保研信息平台。

这个仓库按“**公开代码，私有数据留本地**”的原则设计：可以公开协作、上传 GitHub、持续迭代产品能力，但不会默认上传你的真实画像、目标院校清单、Webhook、抓取状态库等本地数据。

## Positioning

Baoyan Radar Platform 的目标不是做一个简单的爬虫脚本，而是提供一套可持续演进的保研平台基础设施：

- **多源监控**：跟踪院校官网、学院页面、项目通知、经验贴及扩展来源
- **画像驱动筛选**：结合排名、研究方向、项目经历、竞赛经历等进行匹配
- **导师与实验室发现**：辅助定位导师主页、实验室页面与研究方向信息
- **工作流闭环**：支持扫描、去重、状态管理、备注、筛选和后续跟进
- **自动化运行**：支持本地定时任务与飞书消息推送
- **隐私隔离**：公开仓库只保存通用逻辑与模板，本地私有数据默认不入库

## Core Capabilities

### 1. Notice and source monitoring

- 监控高校官网中的夏令营、预推免、推免直博等通知
- 支持经验贴 / 面经 / 评价类页面的辅助收集
- 自动抽取候选链接、去重、记录扫描结果与首次发现时间

### 2. Profile-aware matching

- 根据个人画像对页面进行匹配评分
- 支持按来源、关键词、阈值进行精细化调优
- 支持提取截止时间、材料要求、考核方式等关键信息

### 3. Mentor and lab intelligence

- 支持导师主页、实验室页面和相关介绍页的匹配分析
- 支持生成导师联系方向的辅助草稿
- 便于后续扩展为更系统的导师/实验室信息库

### 4. Local dashboard

- 提供本地 Web 工作台统一查看通知、经验信息和处理状态
- 支持筛选、标星、备注、状态流转和手动触发扫描
- 可作为后续平台化 UI 的基础前端

### 5. Scheduling and notification

- 支持 macOS LaunchAgent 与 Windows Scheduled Task
- 支持命中新结果后通过 Feishu webhook 推送
- 支持单条推送和汇总推送两种模式

## Repository Layout

```text
baoyan-radar-skill/
├── SKILL.md
├── README.md
├── dist/
│   └── baoyan-radar.skill
├── dashboard/
│   ├── package.json
│   ├── tsconfig.json
│   ├── public/
│   │   ├── index.html
│   │   └── styles.css
│   ├── src/
│   │   └── app.ts
│   └── scripts/
│       └── copy-assets.mjs
├── scripts/
│   ├── baoyan_radar.py
│   ├── run_dashboard.py
│   ├── setup_clone.py
│   ├── setup_web.py
│   ├── install_daily_schedule.py
│   ├── install_daily_launch_agent.py
│   └── install_windows_schtask.py
├── references/
│   ├── profile.example.json
│   ├── targets.example.json
│   ├── presets.cn-cs.json
│   ├── scheduler.md
│   └── ...
├── config/
│   └── .gitkeep
└── state/
    └── .gitkeep
```

## Quick Start

### Option A. Terminal setup wizard

```bash
python3 scripts/setup_clone.py
```

### Option B. Local web setup wizard

```bash
python3 scripts/setup_web.py
```

初始化完成后，系统会在本地生成：

- `config/profile.local.json`
- `config/targets.local.json`
- `state/radar.db`

这些文件用于保存你的个人画像、目标配置和运行状态，默认不会上传到 GitHub。

## Dashboard

本项目已经包含一个本地可视化工作台，适合把保研通知、经验参考、处理状态、备注和扫描操作统一放到一个页面里管理。

### Build frontend

```bash
cd dashboard
npm install
npm run build
```

### Run dashboard

```bash
python3 scripts/run_dashboard.py
```

默认访问地址：

- <http://127.0.0.1:8787/>

当前工作台已支持：

- 查看官方通知与经验参考
- 按类型、状态、来源、关键词筛选
- 标星、备注、状态流转
- 查看近期 DDL 与重点结果
- 在页面内触发扫描
- 读取最近扫描日志

## Daily Schedule

统一安装入口：

```bash
python3 scripts/install_daily_schedule.py \
  --profile config/profile.local.json \
  --targets config/targets.local.json \
  --db state/radar.db \
  --hour 9 --minute 0 \
  --push-mode digest \
  --send-empty-digest
```

自动适配：

- macOS → LaunchAgent
- Windows → Scheduled Task (`schtasks`)

## Privacy and Git Hygiene

如果你要把这个项目公开到 GitHub，建议遵守下面这条默认规则：

> **只上传通用代码、模板和公开文档；不要上传任何真实个人数据或本地运行状态。**

本仓库默认将以下内容视为**本地私有文件**：

- `config/*.local.json`
- `state/`
- `.env`
- `dashboard/node_modules/`
- `dashboard/dist/`

也就是说：

- 可以提交：脚本、模板、预设、文档、前端源码
- 不要提交：真实画像、联系方式、飞书 webhook、个人目标清单、SQLite 状态库、运行日志、前端依赖目录

## Common Commands

### Run a single scan

```bash
python3 scripts/baoyan_radar.py once \
  --profile config/profile.local.json \
  --targets config/targets.local.json \
  --db state/radar.db
```

### Analyze a mentor or lab page

```bash
python3 scripts/baoyan_radar.py score \
  --url https://example.edu.cn/lab/pi \
  --profile config/profile.local.json
```

### Generate a first-draft outreach email

```bash
python3 scripts/baoyan_radar.py draft-email \
  --url https://example.edu.cn/lab/pi \
  --profile config/profile.local.json \
  --mentor-name 张老师
```

## Packaging the Skill

如果你希望继续以 OpenClaw skill 的形式分发，**不要直接在带有真实本地配置的工作目录里打包**。

原因是：打包工具不会自动按你的公开/私有边界过滤 `config/` 和 `state/`，直接打包存在把本地私有数据一起封进 `.skill` 的风险。

更安全的做法是：

1. 先准备一个不含 `config/`、`state/`、`.env`、本地日志和数据库的净化副本
2. 再从净化副本执行打包

例如：

```bash
python3 /opt/homebrew/lib/node_modules/openclaw/skills/skill-creator/scripts/package_skill.py /path/to/sanitized/baoyan-radar ./dist
```

当前仓库中的 `dist/baoyan-radar.skill` 应当始终来自这种净化后的公开副本。

## Roadmap

当前版本已经具备可用的本地平台雏形，后续可以继续沿这些方向扩展：

- 更系统的学校 / 学院 / 项目分类体系
- 更稳定的导师 / 实验室信息抽取与画像融合
- 更精确的截止时间识别与日历视图
- 面向不同学校的可配置来源模板体系
- 更完整的前端工作流与状态管理
- 与更多消息通知渠道集成

---

If this project is useful to you, feel free to star it.