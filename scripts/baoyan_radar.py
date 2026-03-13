#!/usr/bin/env python3
import argparse
import datetime as dt
import html
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

USER_AGENT = "Mozilla/5.0 (compatible; baoyan-radar/0.2; +https://github.com/)"
DEFAULT_TIMEOUT = 20
MAX_LINKS_PER_SOURCE = 80


@dataclass
class FetchResult:
    url: str
    final_url: str
    title: str
    text: str
    html: str


def load_json(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_url(url: str, timeout: int = DEFAULT_TIMEOUT) -> FetchResult:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        final_url = resp.geturl()
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        try:
            body = raw.decode(charset, errors="ignore")
        except LookupError:
            body = raw.decode("utf-8", errors="ignore")
    title = extract_title(body)
    text = html_to_text(body)
    return FetchResult(url=url, final_url=final_url, title=title, text=text, html=body)


def extract_title(content: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", content, flags=re.I | re.S)
    if not m:
        return ""
    return normalize_space(html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))))


def html_to_text(content: str) -> str:
    content = re.sub(r"<script.*?>.*?</script>", " ", content, flags=re.I | re.S)
    content = re.sub(r"<style.*?>.*?</style>", " ", content, flags=re.I | re.S)
    content = re.sub(r"<br\s*/?>", "\n", content, flags=re.I)
    content = re.sub(r"</p>", "\n", content, flags=re.I)
    content = re.sub(r"</div>", "\n", content, flags=re.I)
    content = re.sub(r"<[^>]+>", " ", content)
    content = html.unescape(content)
    return normalize_space(content, preserve_newlines=True)


def normalize_space(text: str, preserve_newlines: bool = False) -> str:
    text = text.replace("\xa0", " ").replace("\u3000", " ")
    if preserve_newlines:
        text = re.sub(r"\r", "", text)
        text = re.sub(r"\n\s*\n+", "\n", text)
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
        return "\n".join([line for line in lines if line]).strip()
    return re.sub(r"\s+", " ", text).strip()


def extract_links(html_content: str, base_url: str) -> List[Tuple[str, str]]:
    links: List[Tuple[str, str]] = []
    pattern = re.compile(r"<a\b[^>]*href=[\"']?([^\"' >]+)[\"']?[^>]*>(.*?)</a>", re.I | re.S)
    for href, anchor_html in pattern.findall(html_content):
        href = href.strip()
        if not href or href.startswith("javascript:") or href.startswith("#"):
            continue
        full = urllib.parse.urljoin(base_url, href)
        anchor_text = normalize_space(re.sub(r"<[^>]+>", " ", html.unescape(anchor_html)))
        links.append((full, anchor_text))
    seen = set()
    deduped = []
    for url, text in links:
        if url in seen:
            continue
        seen.add(url)
        deduped.append((url, text))
    return deduped


def sentence_windows(text: str, keywords: List[str], window: int = 80, limit: int = 5) -> List[str]:
    hits = []
    compact = text.replace("\n", " ")
    for kw in keywords:
        for m in re.finditer(re.escape(kw), compact, flags=re.I):
            start = max(0, m.start() - window)
            end = min(len(compact), m.end() + window)
            snippet = normalize_space(compact[start:end])
            if snippet and snippet not in hits:
                hits.append(snippet)
            if len(hits) >= limit:
                return hits
    return hits


def dedupe_list(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        item = str(item).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def all_profile_keywords(profile: Dict) -> List[str]:
    out = []
    for key in ("target_disciplines", "research_keywords", "project_keywords"):
        out.extend(profile.get(key, []) or [])
    for project in profile.get("projects", []) or []:
        out.extend(project.get("keywords", []) or [])
        summary = project.get("summary", "")
        if summary and not summary.startswith("待补充"):
            out.extend([part for part in re.split(r"[，。；,; ]+", summary) if len(part) >= 2][:8])
    return dedupe_list(out)


def source_content_kind(source: Dict) -> str:
    kind = str(source.get("content_kind", "official")).strip().lower()
    return kind if kind in {"official", "experience"} else "official"


def merged_include_keywords(targets: Dict, source: Dict) -> List[str]:
    kind = source_content_kind(source)
    if kind == "experience":
        global_key = "global_experience_include_keywords"
    else:
        global_key = "global_include_keywords"
    kws = []
    kws.extend(targets.get(global_key, []) or [])
    kws.extend(source.get("include_keywords", []) or [])
    return dedupe_list(kws)


def merged_exclude_keywords(targets: Dict, source: Dict) -> List[str]:
    kind = source_content_kind(source)
    if kind == "experience":
        global_key = "global_experience_exclude_keywords"
    else:
        global_key = "global_exclude_keywords"
    kws = []
    kws.extend(targets.get(global_key, []) or [])
    kws.extend(source.get("exclude_keywords", []) or [])
    return dedupe_list(kws)


def keyword_hits(text: str, keywords: List[str]) -> List[str]:
    hay = text.lower()
    hits = []
    for kw in keywords:
        kw_s = kw.strip()
        if kw_s and kw_s.lower() in hay:
            hits.append(kw_s)
    return dedupe_list(hits)


def compute_fit_score(text: str, profile: Dict, source: Optional[Dict] = None) -> Dict:
    title_and_text = text
    profile_kws = all_profile_keywords(profile)
    source_disciplines = (source or {}).get("discipline_keywords", []) or []
    profile_hits = keyword_hits(title_and_text, profile_kws)
    discipline_hits = keyword_hits(title_and_text, source_disciplines)
    project_hit_count = 0
    project_names = []
    for project in profile.get("projects", []) or []:
        project_keywords = dedupe_list(project.get("keywords", []) or [])
        ph = keyword_hits(title_and_text, project_keywords)
        if ph:
            project_hit_count += 1
            project_names.append(project.get("name", "未命名项目"))
    score = min(100, len(profile_hits) * 8 + len(discipline_hits) * 6 + project_hit_count * 12)
    return {
        "score": score,
        "profile_hits": profile_hits,
        "discipline_hits": discipline_hits,
        "project_hit_count": project_hit_count,
        "project_names": project_names,
    }


def looks_like_notice(candidate_text: str, include_keywords: List[str], exclude_keywords: List[str]) -> bool:
    if exclude_keywords and keyword_hits(candidate_text, exclude_keywords):
        return False
    return bool(keyword_hits(candidate_text, include_keywords))


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        conn.commit()


def init_db(path: str) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notices (
            url TEXT PRIMARY KEY,
            source_name TEXT,
            title TEXT,
            first_seen_at TEXT,
            fit_score INTEGER,
            deadline_text TEXT,
            content_kind TEXT,
            source_tier TEXT
        )
        """
    )
    ensure_column(conn, "notices", "content_kind", "TEXT")
    ensure_column(conn, "notices", "source_tier", "TEXT")
    conn.commit()
    return conn


def already_seen(conn: sqlite3.Connection, url: str) -> bool:
    row = conn.execute("SELECT 1 FROM notices WHERE url = ? LIMIT 1", (url,)).fetchone()
    return bool(row)


def mark_seen(conn: sqlite3.Connection, item: Dict, source: Dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO notices
        (url, source_name, title, first_seen_at, fit_score, deadline_text, content_kind, source_tier)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item.get("url", ""),
            source.get("name", "未命名来源"),
            item.get("title", "未命名标题"),
            dt.datetime.now().isoformat(timespec="seconds"),
            int(item.get("fit", {}).get("score", 0)),
            item.get("deadline", {}).get("deadline_text", ""),
            item.get("content_kind", source_content_kind(source)),
            source.get("tier", ""),
        ),
    )
    conn.commit()


def parse_date_candidates(text: str) -> List[dt.date]:
    today = dt.date.today()
    found: List[dt.date] = []
    patterns = [
        r"(20\d{2})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})日?",
        r"(\d{1,2})[月\-/](\d{1,2})日?",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            try:
                if len(m.groups()) == 3:
                    year, month, day = map(int, m.groups())
                else:
                    year = today.year
                    month, day = map(int, m.groups())
                found.append(dt.date(year, month, day))
            except ValueError:
                continue
    deduped = []
    seen = set()
    for d in found:
        if d in seen:
            continue
        seen.add(d)
        deduped.append(d)
    return deduped


def choose_best_date(dates: List[dt.date]) -> Optional[dt.date]:
    if not dates:
        return None
    today = dt.date.today()
    future = [d for d in dates if d >= today]
    if future:
        return min(future)
    recent_past = [d for d in dates if (today - d).days <= 30]
    if recent_past:
        return max(recent_past)
    return max(dates)


def extract_deadline(text: str) -> Dict:
    lines = text.split("\n")
    candidates = [line for line in lines if any(k in line for k in ["截止", "报名时间", "申请时间", "申请截止", "提交时间", "截止时间", "截止日期", "报名截止"])]
    deadline_text = candidates[0] if candidates else ""
    parsed_dates = parse_date_candidates(deadline_text or text[:2500])
    chosen = choose_best_date(parsed_dates)
    if chosen:
        parsed_date = chosen.isoformat()
        days_left = (chosen - dt.date.today()).days
    else:
        parsed_date = None
        days_left = None
    return {
        "deadline_text": deadline_text,
        "parsed_date": parsed_date,
        "days_left": days_left,
    }


def extract_lines_by_keywords(text: str, keys: List[str], max_items: int = 5, min_len: int = 6) -> List[str]:
    lines = text.split("\n")
    matched = []
    for line in lines:
        if any(k.lower() in line.lower() for k in keys):
            cleaned = normalize_space(line)
            if len(cleaned) >= min_len and cleaned not in matched:
                matched.append(cleaned)
        if len(matched) >= max_items:
            break
    return matched


def extract_materials(text: str) -> List[str]:
    return extract_lines_by_keywords(
        text,
        ["材料", "提交", "上传", "附件", "申请表", "简历", "成绩单", "推荐信", "个人陈述", "英语成绩", "证明"],
        max_items=6,
    )


def extract_assessment(text: str) -> List[str]:
    return extract_lines_by_keywords(
        text,
        ["考核", "面试", "笔试", "机试", "审核", "入营", "录取", "考察", "夏令营活动", "综合面试"],
        max_items=4,
    )


def extract_experience_signals(text: str) -> Dict:
    background = extract_lines_by_keywords(
        text,
        ["排名", "rk", "绩点", "GPA", "六级", "CET", "英语", "本科", "双非", "211", "985", "专业", "直博"],
        max_items=4,
        min_len=8,
    )
    interview = extract_lines_by_keywords(
        text,
        ["面试", "机试", "笔试", "英语", "自我介绍", "项目", "问了", "论文", "八股", "导师", "老师"],
        max_items=5,
        min_len=8,
    )
    advice = extract_lines_by_keywords(
        text,
        ["建议", "准备", "注意", "联系导师", "套磁", "入营", "offer", "经验", "避雷", "流程", "时间线"],
        max_items=5,
        min_len=8,
    )
    evaluation = extract_lines_by_keywords(
        text,
        ["评价", "氛围", "实验室", "老师", "组会", "实习", "发论文", "压力", "自由", "方向"],
        max_items=4,
        min_len=8,
    )
    return {
        "background": background,
        "interview": interview,
        "advice": advice,
        "evaluation": evaluation,
    }


def build_base_item(page: FetchResult, profile: Dict, source: Dict) -> Dict:
    return {
        "url": page.final_url,
        "title": page.title or "未识别标题",
        "content_kind": source_content_kind(source),
        "source_name": source.get("name", "未命名来源"),
        "platform": source.get("platform", "官网" if source_content_kind(source) == "official" else "社区"),
        "school": source.get("school", ""),
        "tier": source.get("tier", ""),
        "fit": compute_fit_score(page.title + "\n" + page.text, profile or {}, source),
    }


def extract_notice_summary(page: FetchResult, profile: Optional[Dict] = None, source: Optional[Dict] = None) -> Dict:
    src = source or {}
    item = build_base_item(page, profile or {}, src)
    text = page.text
    item.update(
        {
            "deadline": extract_deadline(text),
            "materials": extract_materials(text),
            "assessment": extract_assessment(text),
            "matched_snippets": sentence_windows(text, item["fit"].get("profile_hits", [])[:5]),
        }
    )
    return item


def extract_experience_summary(page: FetchResult, profile: Optional[Dict] = None, source: Optional[Dict] = None) -> Dict:
    src = source or {}
    item = build_base_item(page, profile or {}, src)
    signals = extract_experience_signals(page.text)
    item.update(
        {
            "deadline": {"deadline_text": "", "parsed_date": None, "days_left": None},
            "materials": [],
            "assessment": [],
            "experience": signals,
            "matched_snippets": sentence_windows(page.text, item["fit"].get("profile_hits", [])[:5]),
        }
    )
    return item


def summarize_page(page: FetchResult, profile: Dict, source: Dict) -> Dict:
    if source_content_kind(source) == "experience":
        return extract_experience_summary(page, profile, source)
    return extract_notice_summary(page, profile, source)


def format_notice_message(item: Dict) -> str:
    if item.get("content_kind") == "experience":
        exp = item.get("experience", {}) or {}
        background = exp.get("background") or ["未稳定提取到明显背景信息，建议人工复核原文"]
        interview = (exp.get("interview") or exp.get("evaluation") or ["未稳定提取到明显面经/评价，建议人工复核原文"])
        advice = exp.get("advice") or ["未稳定提取到明确建议，建议人工复核原文"]
        school_line = f"学校：{item.get('school')}\n" if item.get("school") else ""
        tier_line = f"档位：{item.get('tier')}\n" if item.get("tier") else ""
        return (
            f"【保研经验参考】\n"
            f"来源：{item.get('platform', '社区')} / {item.get('source_name', '未命名来源')}\n"
            f"{school_line}{tier_line}"
            f"标题：{item['title']}\n"
            f"匹配度：{item['fit']['score']}\n"
            f"背景参考：\n- " + "\n- ".join(background[:3]) + "\n"
            f"面经/评价：\n- " + "\n- ".join(interview[:3]) + "\n"
            f"经验建议：\n- " + "\n- ".join(advice[:3]) + "\n"
            f"链接：{item['url']}"
        )

    deadline = item.get("deadline", {})
    ddl = deadline.get("deadline_text") or "未明确写出"
    days = deadline.get("days_left")
    ddl_extra = f"（距DDL {days} 天）" if isinstance(days, int) else ""
    materials = item.get("materials") or ["未稳定提取到，建议人工复核原文"]
    assessment = item.get("assessment") or ["未稳定提取到，建议人工复核原文"]
    school_line = f"学校：{item.get('school')}\n" if item.get("school") else ""
    tier_line = f"档位：{item.get('tier')}\n" if item.get("tier") else ""
    return (
        f"【保研官方情报】\n"
        f"来源：{item.get('platform', '官网')} / {item.get('source_name', '未命名来源')}\n"
        f"{school_line}{tier_line}"
        f"项目：{item['title']}\n"
        f"匹配度：{item['fit']['score']}\n"
        f"DDL：{ddl}{ddl_extra}\n"
        f"材料：\n- " + "\n- ".join(materials[:4]) + "\n"
        f"考核：\n- " + "\n- ".join(assessment[:3]) + "\n"
        f"链接：{item['url']}"
    )


def build_digest_message(items: List[Dict], profile: Optional[Dict] = None) -> str:
    today = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    official = [item for item in items if item.get("content_kind") == "official"]
    experience = [item for item in items if item.get("content_kind") == "experience"]
    lines = [
        f"【保研雷达日报】{today}",
        f"官方新情报：{len(official)} 条",
        f"经验参考：{len(experience)} 条",
    ]
    if profile:
        school = profile.get("school", "")
        major = profile.get("major", "")
        if school or major:
            lines.append(f"画像：{school}{major}")
    if not items:
        lines.append("今天没有发现新的高匹配官方通知或经验参考。")
        return "\n".join(lines)

    if official:
        lines.append("")
        lines.append("【官方情报 Top】")
        for idx, item in enumerate(official[:5], start=1):
            ddl = item.get("deadline", {}).get("deadline_text") or "未明确DDL"
            days = item.get("deadline", {}).get("days_left")
            ddl_suffix = f" / 距DDL {days}天" if isinstance(days, int) else ""
            lines.append(
                f"{idx}. [{item.get('tier', '-')}] {item.get('school', '')} {item.get('title', '')} | 匹配度 {item.get('fit', {}).get('score', 0)} | {ddl}{ddl_suffix}"
            )
            lines.append(f"   {item.get('url', '')}")
    if experience:
        lines.append("")
        lines.append("【经验参考 Top】")
        for idx, item in enumerate(experience[:5], start=1):
            advice = (item.get("experience", {}) or {}).get("advice", [])
            tip = advice[0] if advice else "建议点开原文查看细节"
            lines.append(
                f"{idx}. [{item.get('tier', '-')}] {item.get('school', '')} {item.get('title', '')} | 匹配度 {item.get('fit', {}).get('score', 0)}"
            )
            lines.append(f"   提示：{tip[:120]}")
            lines.append(f"   {item.get('url', '')}")
    return "\n".join(lines)


def post_feishu_webhook(webhook: str, message: str) -> None:
    payload = json.dumps({"msg_type": "text", "content": {"text": message}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": USER_AGENT},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
        resp.read()


def discover_candidates(source: Dict, targets: Dict) -> List[Tuple[str, str]]:
    page = fetch_url(source["url"])
    include_keywords = merged_include_keywords(targets, source)
    exclude_keywords = merged_exclude_keywords(targets, source)

    # Experience sources are usually single posts/pages.
    # Default to analyzing the source page itself only, unless explicitly configured to follow links.
    if source_content_kind(source) == "experience" and not source.get("follow_links", False):
        blob = page.title + "\n" + page.text[:5000]
        if looks_like_notice(blob, include_keywords, exclude_keywords):
            return [(page.final_url, page.title)]
        return []

    links = extract_links(page.html, page.final_url)
    candidates: List[Tuple[str, str]] = []
    for url, anchor_text in links[:MAX_LINKS_PER_SOURCE]:
        blob = f"{url} {anchor_text}"
        if looks_like_notice(blob, include_keywords, exclude_keywords):
            candidates.append((url, anchor_text))
    if looks_like_notice(page.title + "\n" + page.text[:3000], include_keywords, exclude_keywords):
        candidates.insert(0, (page.final_url, page.title))
    return dedupe_pairs(candidates)


def dedupe_pairs(pairs: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    seen = set()
    out = []
    for url, text in pairs:
        if url in seen:
            continue
        seen.add(url)
        out.append((url, text))
    return out


def threshold_for_source(profile: Dict, source: Dict) -> int:
    prefs = profile.get("preferences", {}) or {}
    if source_content_kind(source) == "experience":
        return int(source.get("fit_threshold", prefs.get("experience_fit_threshold", 22)))
    return int(source.get("fit_threshold", prefs.get("fit_threshold", 35)))


def is_stale(item: Dict, profile: Dict, source: Dict) -> bool:
    if source_content_kind(source) != "official":
        return False
    days = item.get("deadline", {}).get("days_left")
    max_past = int(profile.get("preferences", {}).get("official_max_past_days", 14))
    return isinstance(days, int) and days < -max_past


def run_once(
    profile_path: str,
    targets_path: str,
    db_path: str,
    push: bool = True,
    push_mode: str = "item",
    send_empty_digest: bool = False,
) -> List[Dict]:
    profile = load_json(profile_path)
    targets = load_json(targets_path)
    webhook = profile.get("contact", {}).get("feishu_webhook", "").strip()
    conn = init_db(db_path)
    matched_items: List[Dict] = []
    for source in targets.get("sources", []) or []:
        try:
            candidates = discover_candidates(source, targets)
        except Exception as e:
            print(f"[WARN] source failed: {source.get('name', source.get('url'))}: {e}", file=sys.stderr)
            continue
        for url, _anchor_text in candidates:
            if already_seen(conn, url):
                continue
            try:
                page = fetch_url(url)
            except Exception as e:
                print(f"[WARN] candidate fetch failed: {url}: {e}", file=sys.stderr)
                continue
            item = summarize_page(page, profile, source)
            page_text = page.title + "\n" + page.text
            if keyword_hits(page_text, merged_exclude_keywords(targets, source)):
                mark_seen(conn, item, source)
                continue
            if not keyword_hits(page_text, merged_include_keywords(targets, source)):
                continue
            if item["fit"]["score"] < threshold_for_source(profile, source):
                continue
            if is_stale(item, profile, source):
                mark_seen(conn, item, source)
                continue
            matched_items.append(item)
            mark_seen(conn, item, source)
            if push and webhook and push_mode == "item":
                try:
                    post_feishu_webhook(webhook, format_notice_message(item))
                except Exception as e:
                    print(f"[WARN] Feishu push failed: {e}", file=sys.stderr)
    if push and webhook and push_mode == "digest" and (matched_items or send_empty_digest):
        try:
            post_feishu_webhook(webhook, build_digest_message(matched_items, profile))
        except Exception as e:
            print(f"[WARN] Feishu digest push failed: {e}", file=sys.stderr)
    return matched_items


def inspect_url(url: str, profile_path: Optional[str] = None, content_kind: str = "official") -> Dict:
    profile = load_json(profile_path) if profile_path else {}
    page = fetch_url(url)
    source = {"content_kind": content_kind, "name": "inspect", "platform": "manual"}
    return summarize_page(page, profile, source)


def score_url(url: str, profile_path: str) -> Dict:
    profile = load_json(profile_path)
    page = fetch_url(url)
    fit = compute_fit_score(page.title + "\n" + page.text, profile)
    return {
        "url": page.final_url,
        "title": page.title,
        "score": fit["score"],
        "profile_hits": fit["profile_hits"],
        "project_names": fit["project_names"],
        "matched_snippets": sentence_windows(page.text, fit["profile_hits"][:5]),
    }


def draft_email(url: str, profile_path: str, mentor_name: Optional[str]) -> str:
    profile = load_json(profile_path)
    scored = score_url(url, profile_path)
    salutation = f"尊敬的{mentor_name}老师：" if mentor_name else "尊敬的老师："
    projects = profile.get("projects", []) or []
    top_projects = []
    for p in projects:
        kws = p.get("keywords", []) or []
        if any(kw in scored["profile_hits"] for kw in kws):
            top_projects.append(p)
    if not top_projects:
        top_projects = projects[:2]
    project_lines = []
    for p in top_projects[:2]:
        line = f"我曾参与「{p.get('name', '项目')}」，主要内容为：{p.get('summary', '此处补充项目内容')}"
        project_lines.append(line)
    keyword_phrase = "、".join(scored["profile_hits"][:4]) if scored["profile_hits"] else "相关方向"
    school = profile.get("school", "某高校")
    major = profile.get("major", "相关专业")
    rank = profile.get("rank", "")
    english = profile.get("english", {})
    cet6 = english.get("cet6") or english.get("toefl") or english.get("ielts") or ""
    body = [
        salutation,
        "",
        f"您好！我是{school}{major}学生，当前成绩情况为{rank or '可在此补充排名/绩点'}。近期阅读了您的主页/实验室介绍后，发现您在{keyword_phrase}等方向上的工作与我的兴趣和已有积累较为契合，因此冒昧来信，希望有机会进一步向您请教，并争取参与贵组的推免/夏令营相关选拔。",
        "",
        "与您方向相关的个人经历简述如下：",
        *[f"- {line}" for line in project_lines],
        "",
        f"从目前公开页面信息来看，我关注到您课题组/研究方向涉及：{keyword_phrase}。这些内容与我现阶段的研究兴趣有较强重合，我也希望在后续阶段继续围绕该方向深入学习。",
        "",
        f"若您方便，我想进一步了解贵组今年在推免生/直博生招收方面的安排，以及我目前的背景是否有机会与您的研究方向匹配。若需要，我可以补充发送个人简历、成绩单、项目材料及英语成绩（{cet6 or '可在此补充'}）。",
        "",
        "感谢您在百忙之中阅读这封邮件，期待您的回复！",
        "",
        "此致",
        "敬礼",
        "",
        f"{profile.get('student_name', '你的名字')}",
        f"邮箱：{profile.get('contact', {}).get('email', 'your_email@example.com')}",
    ]
    return "\n".join(body)


def main() -> int:
    parser = argparse.ArgumentParser(description="保研情报雷达：监控官方通知与社区经验，按画像匹配并生成辅助输出")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_once = sub.add_parser("once", help="执行一次扫描")
    p_once.add_argument("--profile", required=True, help="本地私有画像 JSON")
    p_once.add_argument("--targets", required=True, help="本地监控目标 JSON")
    p_once.add_argument("--db", required=True, help="SQLite 状态库路径")
    p_once.add_argument("--print-only", action="store_true", help="只打印，不推送飞书")
    p_once.add_argument("--push-mode", choices=["item", "digest"], default="item", help="逐条推送或汇总推送")
    p_once.add_argument("--send-empty-digest", action="store_true", help="即使没有新内容也发送一条日报（仅 digest 模式）")

    p_run = sub.add_parser("run", help="循环扫描")
    p_run.add_argument("--profile", required=True)
    p_run.add_argument("--targets", required=True)
    p_run.add_argument("--db", required=True)
    p_run.add_argument("--interval-min", type=int, default=60)
    p_run.add_argument("--print-only", action="store_true")
    p_run.add_argument("--push-mode", choices=["item", "digest"], default="item")
    p_run.add_argument("--send-empty-digest", action="store_true")

    p_inspect = sub.add_parser("inspect", help="检查单条页面")
    p_inspect.add_argument("--url", required=True)
    p_inspect.add_argument("--profile", help="可选，本地画像 JSON")
    p_inspect.add_argument("--content-kind", choices=["official", "experience"], default="official")

    p_score = sub.add_parser("score", help="评估导师/实验室页面匹配度")
    p_score.add_argument("--url", required=True)
    p_score.add_argument("--profile", required=True)

    p_draft = sub.add_parser("draft-email", help="生成套磁信草稿")
    p_draft.add_argument("--url", required=True)
    p_draft.add_argument("--profile", required=True)
    p_draft.add_argument("--mentor-name")

    args = parser.parse_args()
    try:
        if args.cmd == "once":
            result = run_once(
                args.profile,
                args.targets,
                args.db,
                push=not args.print_only,
                push_mode=args.push_mode,
                send_empty_digest=args.send_empty_digest,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "run":
            while True:
                result = run_once(
                    args.profile,
                    args.targets,
                    args.db,
                    push=not args.print_only,
                    push_mode=args.push_mode,
                    send_empty_digest=args.send_empty_digest,
                )
                stamp = dt.datetime.now().isoformat(timespec="seconds")
                print(f"[{stamp}] matched={len(result)}", flush=True)
                if result:
                    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
                time.sleep(max(1, args.interval_min) * 60)
        if args.cmd == "inspect":
            result = inspect_url(args.url, args.profile, args.content_kind)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "score":
            result = score_url(args.url, args.profile)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.cmd == "draft-email":
            print(draft_email(args.url, args.profile, args.mentor_name))
            return 0
    except urllib.error.URLError as e:
        print(f"network error: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"file not found: {e}", file=sys.stderr)
        return 3
    except json.JSONDecodeError as e:
        print(f"invalid json: {e}", file=sys.stderr)
        return 4
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
