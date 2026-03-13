# 🎯 Baoyan Radar Skill

一个面向 **保研 / 推免 / 夏令营 / 预推免 / 直博** 的情报雷达项目。

它可以根据用户的**个人画像**，自动筛选高校官网通知、收集经验贴信息，并支持 **Feishu 推送**、**每日定时任务**、**导师匹配** 和 **套磁信草稿生成**。

## ✨ Features

- 🧠 **画像驱动**：根据排名、英语、研究方向、项目经历、竞赛经历自动定位目标层次
- 🏫 **情报监控**：抓取高校官网中的夏令营 / 预推免 / 直博相关通知
- 📝 **经验参考**：支持经验贴 / 面经 / 评价类页面的辅助收集
- 📬 **Feishu 推送**：命中新通知后可自动推送到飞书
- ⏰ **每日定时**：支持自动定时运行
- 💌 **导师辅助**：支持导师 / 实验室页面匹配度分析与套磁信草稿生成
- 🔒 **隐私优先**：个人信息只保存在本地，不进入 Git
- 💻 **跨平台**：适配 macOS 和 Windows 的定时任务安装流程

## 🚀 Quick Start

### 方式 1：终端向导

```bash
python3 scripts/setup_clone.py
```

### 方式 2：本地网页向导

```bash
python3 scripts/setup_web.py
```

配置完成后，系统会在本地生成：

- `config/profile.local.json`
- `config/targets.local.json`
- `state/radar.db`

这些文件都被 `.gitignore` 忽略，不会上传到 GitHub。

## ⏰ Daily Schedule

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

- 🍎 macOS → LaunchAgent
- 🪟 Windows → Scheduled Task (`schtasks`)

## 📦 Repo Structure

```text
baoyan-radar-skill/
├── SKILL.md
├── README.md
├── dist/
│   └── baoyan-radar.skill
├── scripts/
│   ├── baoyan_radar.py
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

## 🔐 Privacy

请不要把真实个人信息提交到仓库。

本项目默认把以下内容视为**本地私有文件**：

- `config/*.local.json`
- `state/`
- `.env`

也就是说：
- ✅ 可以提交模板、脚本、预设源
- ❌ 不要提交真实画像、飞书 webhook、抓取状态库

## 🧪 Common Commands

### 单次扫描

```bash
python3 scripts/baoyan_radar.py once \
  --profile config/profile.local.json \
  --targets config/targets.local.json \
  --db state/radar.db
```

### 分析导师 / 实验室页面

```bash
python3 scripts/baoyan_radar.py score \
  --url https://example.edu.cn/lab/pi \
  --profile config/profile.local.json
```

### 生成套磁信草稿

```bash
python3 scripts/baoyan_radar.py draft-email \
  --url https://example.edu.cn/lab/pi \
  --profile config/profile.local.json \
  --mentor-name 张老师
```

## 📌 Status

当前版本已支持：

- clone-and-run 本地初始化
- 学校预设源
- 自动定位学校层次
- 每日定时推送
- 导师匹配与套磁信基础能力

后续可继续扩展：

- 学院级预设源
- 实验室级预设源
- 导师级预设源
- 更强的经验贴去噪与筛选逻辑

---

如果这个项目对你有帮助，欢迎 ⭐️。