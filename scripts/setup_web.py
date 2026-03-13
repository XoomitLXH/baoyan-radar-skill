#!/usr/bin/env python3
import argparse
import html
import json
import re
import subprocess
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List, Optional


def parse_csv(text: str) -> List[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


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

    if len(profile.get("research_keywords", []) or []) >= 2:
        score += 1
        reasons.append("研究方向比较明确")
    if len(profile.get("projects", []) or []) >= 1:
        score += 1
        reasons.append("有项目/科研经历")
    if len(profile.get("projects", []) or []) >= 2:
        score += 1
        reasons.append("有多段科研/项目经历")
    if len(profile.get("competitions", []) or []) >= 1:
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
    return {"score": score, "tiers": tiers, "schools": schools, "reasons": reasons}


def render_page(title: str, body: str) -> bytes:
    doc = f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 980px; margin: 24px auto; padding: 0 16px; line-height: 1.5; }}
    h1, h2 {{ margin: 0.4em 0; }}
    .card {{ border: 1px solid #ddd; border-radius: 12px; padding: 16px; margin: 16px 0; }}
    label {{ display: block; margin: 8px 0 4px; font-weight: 600; }}
    input[type=text], input[type=number], textarea {{ width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #ccc; border-radius: 8px; }}
    textarea {{ min-height: 80px; resize: vertical; }}
    .muted {{ color: #666; font-size: 0.95em; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }}
    button {{ border: 0; background: #111; color: white; padding: 12px 18px; border-radius: 10px; cursor: pointer; font-size: 15px; }}
    code, pre {{ background: #f6f8fa; border-radius: 8px; padding: 2px 6px; }}
    pre {{ padding: 12px; overflow: auto; }}
    .ok {{ color: #0a7a2f; font-weight: 700; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""
    return doc.encode("utf-8")


def make_handler(root: Path):
    preset = json.loads((root / "references" / "presets.cn-cs.json").read_text(encoding="utf-8"))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def _send_html(self, title: str, body: str, status: int = 200):
            data = render_page(title, body)
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path not in {"/", "/index.html"}:
                self._send_html("Not found", "<h1>404</h1>", status=404)
                return
            body = f"""
<h1>Baoyan Radar 本地配置向导</h1>
<p class=\"muted\">填写后只会写入本地 <code>config/*.local.json</code>，不会进入 Git。</p>
<form method=\"post\" action=\"/submit\">
  <div class=\"card\">
    <h2>1. 个人画像</h2>
    <div class=\"grid\">
      <div><label>姓名（可留空）</label><input type=\"text\" name=\"student_name\"></div>
      <div><label>本科院校</label><input type=\"text\" name=\"school\" required></div>
      <div><label>本科专业</label><input type=\"text\" name=\"major\"></div>
      <div><label>年级</label><input type=\"text\" name=\"year\"></div>
      <div><label>排名/名次</label><input type=\"text\" name=\"rank\"></div>
      <div><label>GPA（可留空）</label><input type=\"text\" name=\"gpa\"></div>
      <div><label>CET-6（可留空）</label><input type=\"text\" name=\"cet6\"></div>
      <div><label>Feishu webhook（可留空）</label><input type=\"text\" name=\"feishu_webhook\"></div>
    </div>
    <label>意向学科（逗号分隔）</label>
    <textarea name=\"target_disciplines\"></textarea>
    <label>研究方向关键词（逗号分隔）</label>
    <textarea name=\"research_keywords\"></textarea>
    <label>项目关键词（逗号分隔）</label>
    <textarea name=\"project_keywords\"></textarea>

    <h2>项目/科研经历（可写具体内容）</h2>
    <div class=\"grid\">
      <div><label>项目1名称</label><input type=\"text\" name=\"project1_name\"></div>
      <div><label>项目1角色</label><input type=\"text\" name=\"project1_role\"></div>
    </div>
    <label>项目1具体内容</label><textarea name=\"project1_summary\"></textarea>
    <label>项目1结果产出</label><input type=\"text\" name=\"project1_result\">
    <label>项目1关键词（逗号分隔）</label><input type=\"text\" name=\"project1_keywords\">

    <div class=\"grid\">
      <div><label>项目2名称</label><input type=\"text\" name=\"project2_name\"></div>
      <div><label>项目2角色</label><input type=\"text\" name=\"project2_role\"></div>
    </div>
    <label>项目2具体内容</label><textarea name=\"project2_summary\"></textarea>
    <label>项目2结果产出</label><input type=\"text\" name=\"project2_result\">
    <label>项目2关键词（逗号分隔）</label><input type=\"text\" name=\"project2_keywords\">

    <div class=\"grid\">
      <div><label>项目3名称</label><input type=\"text\" name=\"project3_name\"></div>
      <div><label>项目3角色</label><input type=\"text\" name=\"project3_role\"></div>
    </div>
    <label>项目3具体内容</label><textarea name=\"project3_summary\"></textarea>
    <label>项目3结果产出</label><input type=\"text\" name=\"project3_result\">
    <label>项目3关键词（逗号分隔）</label><input type=\"text\" name=\"project3_keywords\">

    <h2>竞赛经历（可写具体内容）</h2>
    <div class=\"grid\">
      <div><label>竞赛1名称</label><input type=\"text\" name=\"competition1_name\"></div>
      <div><label>竞赛1获奖/名次</label><input type=\"text\" name=\"competition1_award\"></div>
    </div>
    <label>竞赛1具体内容</label><textarea name=\"competition1_summary\"></textarea>
    <label>竞赛1关键词（逗号分隔）</label><input type=\"text\" name=\"competition1_keywords\">

    <div class=\"grid\">
      <div><label>竞赛2名称</label><input type=\"text\" name=\"competition2_name\"></div>
      <div><label>竞赛2获奖/名次</label><input type=\"text\" name=\"competition2_award\"></div>
    </div>
    <label>竞赛2具体内容</label><textarea name=\"competition2_summary\"></textarea>
    <label>竞赛2关键词（逗号分隔）</label><input type=\"text\" name=\"competition2_keywords\">

    <div class=\"grid\">
      <div><label>竞赛3名称</label><input type=\"text\" name=\"competition3_name\"></div>
      <div><label>竞赛3获奖/名次</label><input type=\"text\" name=\"competition3_award\"></div>
    </div>
    <label>竞赛3具体内容</label><textarea name=\"competition3_summary\"></textarea>
    <label>竞赛3关键词（逗号分隔）</label><input type=\"text\" name=\"competition3_keywords\">

    <label><input type=\"checkbox\" name=\"accept_direct_phd\" checked> 接受直博</label>
  </div>

  <div class=\"card\">
    <h2>2. 每天几点几分进行推送</h2>
    <div class=\"grid\">
      <div><label>每天几点（24 小时制）</label><input type=\"number\" name=\"hour\" value=\"9\" min=\"0\" max=\"23\"></div>
      <div><label>每天几分</label><input type=\"number\" name=\"minute\" value=\"0\" min=\"0\" max=\"59\"></div>
    </div>
    <label><input type=\"checkbox\" name=\"install_schedule\" checked> 现在安装每日定时任务（自动适配 macOS / Windows）</label>
    <label><input type=\"checkbox\" name=\"run_test\" checked> 现在立即执行一次测试扫描/推送</label>
    <label><input type=\"checkbox\" name=\"send_empty_digest\" checked> 即使没有新内容也发送日报</label>
  </div>

  <button type=\"submit\">生成本地配置并安装</button>
</form>
"""
            self._send_html("Baoyan Radar Setup", body)

        def do_POST(self):
            if self.path != "/submit":
                self._send_html("Not found", "<h1>404</h1>", status=404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8", errors="ignore")
            form = urllib.parse.parse_qs(raw)

            def get(name: str, default: str = "") -> str:
                return form.get(name, [default])[0].strip()

            def has(name: str) -> bool:
                return name in form

            projects = []
            for i in range(1, 4):
                name = get(f"project{i}_name")
                if not name:
                    continue
                projects.append({
                    "name": name,
                    "role": get(f"project{i}_role"),
                    "summary": get(f"project{i}_summary"),
                    "result": get(f"project{i}_result"),
                    "keywords": parse_csv(get(f"project{i}_keywords")),
                })

            competitions = []
            for i in range(1, 4):
                name = get(f"competition{i}_name")
                if not name:
                    continue
                competitions.append({
                    "name": name,
                    "award": get(f"competition{i}_award"),
                    "summary": get(f"competition{i}_summary"),
                    "keywords": parse_csv(get(f"competition{i}_keywords")),
                })

            profile = {
                "student_name": get("student_name"),
                "school": get("school"),
                "major": get("major"),
                "year": get("year"),
                "rank": get("rank"),
                "gpa": get("gpa"),
                "english": {"cet4": "", "cet6": get("cet6"), "toefl": "", "ielts": ""},
                "target_disciplines": parse_csv(get("target_disciplines")),
                "research_keywords": parse_csv(get("research_keywords")),
                "project_keywords": parse_csv(get("project_keywords")),
                "projects": projects,
                "competitions": competitions,
                "preferences": {
                    "accept_direct_phd": has("accept_direct_phd"),
                    "fit_threshold": 32,
                    "experience_fit_threshold": 18,
                    "official_max_past_days": 14,
                    "language": "zh-CN",
                },
                "contact": {"email": "", "phone": "", "feishu_webhook": get("feishu_webhook")},
            }

            positioning = infer_positioning(profile, preset)
            discipline_keywords = list(dict.fromkeys(profile["target_disciplines"] + profile["research_keywords"]))
            targets = {
                "global_include_keywords": preset.get("global_include_keywords", []),
                "global_exclude_keywords": preset.get("global_exclude_keywords", []),
                "global_experience_include_keywords": preset.get("global_experience_include_keywords", []),
                "global_experience_exclude_keywords": preset.get("global_experience_exclude_keywords", []),
                "sources": [],
            }
            for source in preset.get("sources", []):
                if source.get("tier") not in positioning["tiers"]:
                    continue
                item = dict(source)
                item["discipline_keywords"] = discipline_keywords
                targets["sources"].append(item)

            config_dir = root / "config"
            state_dir = root / "state"
            config_dir.mkdir(parents=True, exist_ok=True)
            state_dir.mkdir(parents=True, exist_ok=True)
            profile_path = config_dir / "profile.local.json"
            targets_path = config_dir / "targets.local.json"
            db_path = state_dir / "radar.db"
            profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
            targets_path.write_text(json.dumps(targets, ensure_ascii=False, indent=2), encoding="utf-8")

            command_logs = []
            background_note = ""
            if has("install_schedule"):
                cmd = [
                    sys.executable,
                    str(root / "scripts" / "install_daily_schedule.py"),
                    "--profile", str(profile_path),
                    "--targets", str(targets_path),
                    "--db", str(db_path),
                    "--hour", get("hour") or "9",
                    "--minute", get("minute") or "0",
                    "--push-mode", "digest",
                ]
                if has("send_empty_digest"):
                    cmd.append("--send-empty-digest")
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    command_logs.append(("安装定时任务", result.returncode, result.stdout + result.stderr))
                except subprocess.TimeoutExpired:
                    command_logs.append(("安装定时任务", 124, "安装定时任务耗时过长，请稍后在终端重试。"))

            if has("run_test"):
                cmd = [
                    sys.executable,
                    str(root / "scripts" / "baoyan_radar.py"),
                    "once",
                    "--profile", str(profile_path),
                    "--targets", str(targets_path),
                    "--db", str(db_path),
                ]
                if profile.get("contact", {}).get("feishu_webhook"):
                    cmd.extend(["--push-mode", "digest"])
                    if has("send_empty_digest"):
                        cmd.append("--send-empty-digest")
                else:
                    cmd.append("--print-only")
                log_path = state_dir / "setup-web-test.log"
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write("[baoyan-radar] background test started\n")
                with open(log_path, "a", encoding="utf-8") as f:
                    subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
                background_note = f"<p><strong>测试扫描</strong> 已改为后台启动，避免网页卡住。日志文件：<code>{html.escape(str(log_path))}</code></p>"

            logs_html = "".join(
                f"<h3>{html.escape(name)}（exit={code}）</h3><pre>{html.escape(output[:6000])}</pre>" for name, code, output in command_logs
            ) or "<p>未执行需要同步等待的命令。</p>"
            body = f"""
<h1 class="ok">已生成本地配置</h1>
<div class="card">
  <p><strong>profile</strong>: <code>{html.escape(str(profile_path))}</code></p>
  <p><strong>targets</strong>: <code>{html.escape(str(targets_path))}</code></p>
  <p><strong>监控源数量</strong>: {len(targets['sources'])} 个</p>
  {background_note}
</div>
<div class="card">
  <h2>命令执行结果</h2>
  {logs_html}
</div>
<div class="card">
  <h2>接下来</h2>
  <p>终端版入口：<code>python3 scripts/setup_clone.py</code></p>
  <p>网页版入口：<code>python3 scripts/setup_web.py</code></p>
  <p>后续可继续扩展：学院级 / 实验室级 / 导师预设源。</p>
</div>
"""
            self._send_html("配置完成", body)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Start a local web setup page for baoyan-radar")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    server = ThreadingHTTPServer((args.host, args.port), make_handler(root))
    url = f"http://{args.host}:{args.port}/"
    print(f"[OK] setup web UI running at {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
