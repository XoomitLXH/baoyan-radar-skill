# Baoyan Radar Platform

**Baoyan Radar Platform** 是一个面向 **保研 / 推免 / 夏令营 / 预推免 / 直博** 场景的 **local-first 情报监控与决策支持平台**。

它的目标不是提供一个一次性的爬虫脚本，而是沉淀一套可以持续扩展的保研平台基础设施：用于监控招生通知、收集经验信息、结合个人画像做匹配分析，并在本地工作台中完成筛选、跟进、备注、推送与日常管理。

项目默认遵循一条非常明确的设计原则：

> **公开代码与模板，私有数据留在本地。**

这意味着你可以把仓库公开到 GitHub，持续迭代产品能力，同时不必把真实个人画像、目标清单、Webhook、运行日志和状态数据库暴露出去。

---

## Overview

Baoyan Radar Platform 主要解决三类问题：

- **信息分散**：不同高校、学院、项目与经验来源分布在多个站点，难以长期跟踪
- **筛选成本高**：同一条通知对不同背景学生的价值不同，需要结合画像判断优先级
- **跟进链路断裂**：即使发现了信息，也缺少一个统一的本地工作台来持续管理状态

因此，这个项目更适合被理解为一个 **保研信息工作流平台**，而不是单点脚本：

- 用统一结构管理多源信息采集
- 用画像驱动的规则完成匹配与排序
- 用本地数据库和 dashboard 承接后续跟进
- 用定时任务和消息推送完成自动化运行

---

## Core Capabilities

### Multi-source monitoring

- 监控高校官网、学院页面、项目通知等正式来源
- 支持经验贴、面经、评价类页面等辅助来源扩展
- 自动抽取候选链接、去重并记录首次发现时间

### Profile-aware matching

- 基于个人画像进行匹配评分与优先级判断
- 支持关键词、来源、阈值等维度的精细化调优
- 提取截止时间、材料要求、考核方式等关键信息

### Mentor and lab intelligence

- 支持导师主页、实验室页面和研究方向页的匹配分析
- 辅助识别导师 / 实验室是否与当前画像方向匹配
- 支持生成联系导师时可参考的初稿内容

### Local dashboard workflow

- 提供本地 Web 工作台统一查看通知、经验信息与处理状态
- 支持筛选、标星、备注、状态流转和手动触发扫描
- 为后续继续平台化扩展提供前端基础

### Scheduling and notification

- 支持 macOS LaunchAgent 与 Windows Scheduled Task
- 支持通过 Feishu webhook 推送扫描结果
- 支持单条推送与汇总推送两种模式

---

## Why Local-First

这个项目选择 **local-first**，不是为了“保守”，而是因为保研场景天然包含大量私密信息：

- 个人排名、绩点、英语成绩
- 项目经历、论文、竞赛、科研方向
- 目标院校与偏好策略
- 消息通知地址与运行状态数据

因此，仓库默认采用下面的边界：

- **公开部分**：脚本、模板、预设、前端源码、文档、通用逻辑
- **私有部分**：真实画像、目标配置、Webhook、SQLite 数据库、运行日志、本地依赖产物

这让它既适合作为一个公开开源项目演进，也适合作为个人长期使用的本地平台。

---

## System Structure

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

模块职责大致如下：

- `scripts/`：核心扫描、配置初始化、调度安装与本地服务入口
- `dashboard/`：本地工作台前端源码
- `references/`：示例配置、预设源、说明文档
- `config/`：本地私有配置目录
- `state/`：本地数据库、日志与运行状态目录

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/XoomitLXH/baoyan-radar-skill.git
cd baoyan-radar-skill
```

### 2. Initialize local config

终端向导：

```bash
python3 scripts/setup_clone.py
```

或本地网页向导：

```bash
python3 scripts/setup_web.py
```

初始化完成后，系统通常会在本地生成：

- `config/profile.local.json`
- `config/targets.local.json`
- `state/radar.db`

这些文件承载的是你的私有画像、目标配置和运行状态，默认不应上传到 GitHub。

### 3. Run a single scan

```bash
python3 scripts/baoyan_radar.py once \
  --profile config/profile.local.json \
  --targets config/targets.local.json \
  --db state/radar.db
```

---

## Dashboard

项目已经内置一个本地工作台，用来把“发现信息”与“后续处理”放到同一个界面里。

### Build frontend

```bash
cd dashboard
npm install
npm run build
```

### Run dashboard

```bash
cd ..
python3 scripts/run_dashboard.py
```

默认访问地址：

- <http://127.0.0.1:8787/>

当前工作台已支持：

- 查看官方通知与经验参考
- 按类型、状态、来源、关键词筛选
- 标星、备注与状态流转
- 查看近期 DDL 与重点结果
- 在页面内直接触发扫描
- 读取最近扫描日志

---

## Daily Scheduling

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

---

## Privacy and Git Hygiene

如果你打算把这个项目公开到 GitHub，建议始终遵守下面这条规则：

> **只提交通用代码、模板、文档和前端源码；不要提交任何真实个人数据或本地运行状态。**

默认应视为本地私有内容的包括：

- `config/*.local.json`
- `state/`
- `.env`
- `dashboard/node_modules/`
- `dashboard/dist/`

换句话说：

- **可以提交**：脚本、模板、预设、说明文档、前端源码
- **不要提交**：真实画像、联系方式、飞书 webhook、个人目标清单、SQLite 数据库、运行日志、依赖目录和本地产物

---

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

---

## Packaging the Skill Safely

如果你希望继续把它作为 OpenClaw skill 分发，**不要直接在包含真实本地配置的工作目录里打包**。

原因很简单：打包工具不会自动按照你的公开 / 私有边界过滤 `config/` 和 `state/`，直接打包有机会把本地私有数据一起封进 `.skill` 文件。

更安全的流程是：

1. 先准备一个不含 `config/`、`state/`、`.env`、日志和数据库的净化副本
2. 再从净化副本执行打包

例如：

```bash
python3 /opt/homebrew/lib/node_modules/openclaw/skills/skill-creator/scripts/package_skill.py /path/to/sanitized/baoyan-radar ./dist
```

仓库中的 `dist/baoyan-radar.skill` 应当始终来自这种净化后的公开副本。

---

## Roadmap

当前版本已经具备一个可持续扩展的本地平台雏形，后续可以继续沿这些方向推进：

- 更系统的学校 / 学院 / 项目分类体系
- 更稳定的导师 / 实验室信息抽取与画像融合
- 更精确的截止时间识别与日历视图
- 面向不同学校的可配置来源模板体系
- 更完整的前端工作流与状态管理
- 与更多消息通知渠道集成

---

If this project is useful to you, feel free to star it.