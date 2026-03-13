#!/usr/bin/env python3
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def prompt(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{text}{suffix}: ").strip()
    return value or default


def parse_csv(text: str) -> List[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def yn(text: str, default: bool = True) -> bool:
    default_text = "Y/n" if default else "y/N"
    value = input(f"{text} [{default_text}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "1", "true"}


def parse_rank_percentile(rank_text: str) -> Optional[float]:
    m = re.search(r"(\d+)\s*/\s*(\d+)", rank_text or "")
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    if a <= 0 or b <= 0 or a > b:
        return None
    return a / b


def infer_positioning(profile: dict, preset: dict) -> dict:
    score = 0
    reasons = []

    pct = parse_rank_percentile(profile.get("rank", ""))
    if pct is not None:
        if pct <= 0.03:
            score += 4
            reasons.append("排名处于前 3% 左右")
        elif pct <= 0.08:
            score += 3
            reasons.append("排名处于前 8% 左右")
        elif pct <= 0.15:
            score += 2
            reasons.append("排名处于前 15% 左右")
        elif pct <= 0.25:
            score += 1
            reasons.append("排名处于前 25% 左右")

    cet6_text = str((profile.get("english", {}) or {}).get("cet6", "")).strip()
    cet6_digits = re.sub(r"\D", "", cet6_text)
    if cet6_digits:
        cet6 = int(cet6_digits)
        if cet6 >= 500:
            score += 2
            reasons.append("英语成绩较强")
        elif cet6 >= 425:
            score += 1
            reasons.append("英语达到常见门槛")

    major = str(profile.get("major", ""))
    if any(k in major for k in ["计算机", "软件", "人工智能", "数据", "电子信息", "物联网"]):
        score += 1
        reasons.append("本科专业与目标方向相关")

    research_count = len(profile.get("research_keywords", []) or [])
    project_count = len(profile.get("projects", []) or [])
    competition_count = len(profile.get("competitions", []) or [])
    if research_count >= 2:
        score += 1
        reasons.append("研究方向比较明确")
    if project_count >= 1:
        score += 1
        reasons.append("有项目/科研经历")
    if project_count >= 2:
        score += 1
        reasons.append("有多段科研/项目经历")
    if competition_count >= 1:
        score += 1
        reasons.append("有竞赛经历")

    if bool((profile.get("preferences", {}) or {}).get("accept_direct_phd")):
        score += 1
        reasons.append("接受直博，选择范围更大")

    if score >= 7:
        tiers = ["超级冲", "冲", "稳"]
    elif score >= 4:
        tiers = ["冲", "稳"]
    else:
        tiers = ["稳"]

    schools = []
    seen = set()
    for source in preset.get("sources", []):
        if source.get("tier") in tiers and source.get("school") and source.get("school") not in seen:
            seen.add(source["school"])
            schools.append(source["school"])

    return {
        "score": score,
        "tiers": tiers,
        "schools": schools,
        "reasons": reasons,
    }


def build_profile() -> dict:
    print("\n=== Step 1/3: 填写个人画像（仅写入本地 config/*.local.json，不会进入 Git）===")
    student_name = prompt("姓名（可留空）")
    school = prompt("本科院校")
    major = prompt("本科专业", "")
    year = prompt("年级", "")
    rank = prompt("排名/名次", "")
    gpa = prompt("GPA（可留空）", "")
    cet6 = prompt("CET-6（可留空）", "")
    disciplines = parse_csv(prompt("意向学科（逗号分隔）", ""))
    research = parse_csv(prompt("研究方向关键词（逗号分隔）", ""))
    project_keywords = parse_csv(prompt("项目关键词（逗号分隔）", ""))
    projects = []
    print("\n可填写最多 3 段项目/科研经历；可以写具体内容，直接回车可跳过。")
    for i in range(1, 4):
        name = prompt(f"项目{i}名称（可留空）", "")
        if not name:
            continue
        summary = prompt(f"项目{i}具体内容（研究问题 / 方法 / 你的工作 / 结果）", "")
        role = prompt(f"项目{i}你的角色（可留空）", "")
        result = prompt(f"项目{i}结果产出（论文 / 专利 / demo / 指标 / 可留空）", "")
        kws = parse_csv(prompt(f"项目{i}关键词（逗号分隔）", ""))
        projects.append({"name": name, "summary": summary, "role": role, "result": result, "keywords": kws})

    competitions = []
    print("\n可填写最多 3 段竞赛经历；可以写具体内容，直接回车可跳过。")
    for i in range(1, 4):
        name = prompt(f"竞赛{i}名称（可留空）", "")
        if not name:
            continue
        award = prompt(f"竞赛{i}获奖/名次（可留空）", "")
        summary = prompt(f"竞赛{i}具体内容（赛题 / 你的工作 / 成绩 / 收获）", "")
        kws = parse_csv(prompt(f"竞赛{i}关键词（逗号分隔）", ""))
        competitions.append({"name": name, "award": award, "summary": summary, "keywords": kws})
    accept_direct = yn("是否接受直博", True)
    webhook = prompt("Feishu webhook（用于推送；可先留空）", "")
    return {
        "student_name": student_name,
        "school": school,
        "major": major,
        "year": year,
        "rank": rank,
        "gpa": gpa,
        "english": {"cet4": "", "cet6": cet6, "toefl": "", "ielts": ""},
        "target_disciplines": disciplines,
        "research_keywords": research,
        "project_keywords": project_keywords,
        "projects": projects,
        "competitions": competitions,
        "preferences": {
            "accept_direct_phd": accept_direct,
            "fit_threshold": 32,
            "experience_fit_threshold": 18,
            "official_max_past_days": 14,
            "language": "zh-CN",
        },
        "contact": {"email": "", "phone": "", "feishu_webhook": webhook},
    }


def build_targets(preset: dict, tiers: list[str], discipline_keywords: list[str]) -> dict:
    sources = []
    for source in preset.get("sources", []):
        if source.get("tier") not in tiers:
            continue
        item = dict(source)
        item["discipline_keywords"] = discipline_keywords
        sources.append(item)
    return {
        "global_include_keywords": preset.get("global_include_keywords", []),
        "global_exclude_keywords": preset.get("global_exclude_keywords", []),
        "global_experience_include_keywords": preset.get("global_experience_include_keywords", []),
        "global_experience_exclude_keywords": preset.get("global_experience_exclude_keywords", []),
        "sources": sources,
    }


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    config_dir = root / "config"
    state_dir = root / "state"
    refs_dir = root / "references"
    config_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    preset = json.loads((refs_dir / "presets.cn-cs.json").read_text(encoding="utf-8"))
    profile = build_profile()

    print("\n=== Step 2/3: 根据画像自动定位预设学校 ===")
    positioning = infer_positioning(profile, preset)
    discipline_keywords = list(dict.fromkeys(profile.get("target_disciplines", []) + profile.get("research_keywords", [])))
    targets = build_targets(preset, positioning["tiers"], discipline_keywords)

    profile_path = config_dir / "profile.local.json"
    targets_path = config_dir / "targets.local.json"
    db_path = state_dir / "radar.db"
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    targets_path.write_text(json.dumps(targets, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"定位结论：{' / '.join(positioning['tiers'])}")
    if positioning["reasons"]:
        print("定位依据：")
        for reason in positioning["reasons"]:
            print(f"- {reason}")
    print("纳入的预设学校：")
    print("、".join(positioning["schools"]))
    print(f"\n[OK] 已写入 {profile_path}")
    print(f"[OK] 已写入 {targets_path}")
    print(f"[OK] 已预置 {len(targets['sources'])} 个监控源")

    print("\n=== Step 3/3: 设置每天几点几分进行推送（24 小时制）===")
    hour = prompt("每天几点进行推送（0-23）", "9")
    minute = prompt("每天几分进行推送（0-59）", "0")

    install_now = yn("是否现在安装每日定时任务（自动适配 macOS / Windows）", True)
    if install_now:
        cmd = [
            sys.executable,
            str(root / "scripts" / "install_daily_schedule.py"),
            "--profile", str(profile_path),
            "--targets", str(targets_path),
            "--db", str(db_path),
            "--hour", str(hour),
            "--minute", str(minute),
            "--push-mode", "digest",
            "--send-empty-digest",
        ]
        subprocess.run(cmd, check=True)
        plist = Path.home() / "Library" / "LaunchAgents" / "ai.openclaw.baoyan-radar.daily.plist"
        print("下一步可执行：")
        print(f"  launchctl unload {plist} 2>/dev/null || true")
        print(f"  launchctl load {plist}")

    test_now = yn("是否现在立即执行一次测试扫描/推送", True)
    if test_now:
        cmd = [
            sys.executable,
            str(root / "scripts" / "baoyan_radar.py"),
            "once",
            "--profile", str(profile_path),
            "--targets", str(targets_path),
            "--db", str(db_path),
        ]
        if profile.get("contact", {}).get("feishu_webhook"):
            cmd.extend(["--push-mode", "digest", "--send-empty-digest"])
        else:
            cmd.append("--print-only")
        subprocess.run(cmd, check=False)

    print("\n完成。以后别人 clone 后，直接运行：")
    print("  python3 scripts/setup_clone.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
