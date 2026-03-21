#!/usr/bin/env python3
import argparse
import datetime as dt
import html
import json
import mimetypes
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

STATUS_VALUES = {"new", "watching", "applied", "ignored"}
CATEGORY_VALUES = {"school", "lab", "teacher"}
DEFAULT_TIMEOUT = 12
USER_AGENT = "Mozilla/5.0 (compatible; baoyan-dashboard/0.1)"

POSITIVE_KEYS = [
    "夏令营", "预推免", "推免", "推荐免试", "接收推荐免试", "直博",
    "招生", "报名", "复试", "入营", "优营", "考核", "申请", "名单", "通知", "截止",
]
NEGATIVE_KEYS = [
    "专任教师", "荣休教师", "新闻", "讲座", "论坛", "活动", "工会", "党委", "奖学金",
    "班主任", "教改", "就业", "师生", "热议", "选拔任用", "招聘", "学术报告",
]
TEACHER_KEYS = ["导师", "老师", "teacher", "faculty", "教授", "研究员", "homepage", "主页", "专任教师"]
LAB_KEYS = ["实验室", "lab", "研究组", "研究团队", "group", "团队"]
SCHOOL_KEYS = ["学院", "研究生院", "招生网", "招生", "夏令营", "预推免", "推免", "复试", "名单", "通知", "系"]
SUMMARY_KEYS = POSITIVE_KEYS + ["材料", "报名时间", "截止时间", "申请时间", "考核", "复试", "面试", "机试"]


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def parse_date_candidates(text: str) -> List[dt.date]:
    today = dt.date.today()
    found: List[dt.date] = []
    patterns = [
        r"(20\d{2})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})日?",
        r"(\d{1,2})[月\-/](\d{1,2})日?",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text or ""):
            try:
                if len(m.groups()) == 3:
                    year, month, day = map(int, m.groups())
                else:
                    year = today.year
                    month, day = map(int, m.groups())
                found.append(dt.date(year, month, day))
            except ValueError:
                continue
    return found


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


def parse_deadline(deadline_text: str) -> Dict[str, Any]:
    chosen = choose_best_date(parse_date_candidates(deadline_text or ""))
    if not chosen:
        return {"parsed": None, "days_left": None}
    return {"parsed": chosen.isoformat(), "days_left": (chosen - dt.date.today()).days}


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ").replace("\u3000", " ")).strip()


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_source_map(targets_path: Path) -> Dict[str, Dict[str, Any]]:
    if not targets_path.exists():
        return {}
    data = load_json(targets_path)
    mapping: Dict[str, Dict[str, Any]] = {}
    for source in data.get("sources", []) or []:
        name = str(source.get("name", "")).strip()
        if not name:
            continue
        mapping[name] = {
            "school": str(source.get("school", "")).strip(),
            "tier": str(source.get("tier", "")).strip(),
            "platform": str(source.get("platform", "")).strip(),
            "content_kind": str(source.get("content_kind", "official")).strip() or "official",
            "source_level": str(source.get("source_level", "")).strip().lower(),
            "college": str(source.get("college", "")).strip(),
            "lab": str(source.get("lab", "")).strip(),
            "mentor": str(source.get("mentor", "")).strip(),
            "url": str(source.get("url", "")).strip(),
        }
    return mapping


def source_level(source_meta: Dict[str, Any]) -> str:
    return str(source_meta.get("source_level", "")).strip().lower()


def clean_entity_name(text: str) -> str:
    text = normalize_space(text)
    if not text:
        return ""
    text = re.sub(r"(?:Dr\.?\s*)?([A-Z][A-Za-z\-]+(?:\s+[A-Z][A-Za-z\-]+){0,3})'?s Homepage", r"\1", text, flags=re.I)
    text = re.sub(r"(?:老师|导师|教授|副教授|研究员|个人主页|主页|Homepage|home page)$", "", text, flags=re.I)
    text = text.strip(" -–—|·•")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def humanize_title(raw_title: str, source_meta: Dict[str, Any]) -> str:
    title = clean_entity_name(raw_title)
    level = source_level(source_meta)
    if level == "mentor":
        mentor = clean_entity_name(source_meta.get("mentor", ""))
        if mentor:
            if title in {"", "未命名标题"} or "homepage" in title.lower():
                return mentor
        if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", title):
            return title
    if level == "lab":
        lab = clean_entity_name(source_meta.get("lab", ""))
        if lab and (title in {"", "未命名标题"} or title.lower() in {"lab", "group", "team"}):
            return lab
    return title or raw_title or "未命名标题"


def guess_school(source_name: str, title: str) -> str:
    candidates = re.findall(r"([\u4e00-\u9fa5]{2,}(?:大学|学院))", f"{source_name} {title}")
    return candidates[0] if candidates else ""


def classify_category(source_name: str, title: str, content_kind: str, source_level_value: str = "") -> str:
    if source_level_value == "mentor":
        return "teacher"
    if source_level_value == "lab":
        return "lab"
    text = f"{source_name} {title}".lower()
    if any(key in text for key in TEACHER_KEYS):
        return "teacher"
    if any(key in text for key in LAB_KEYS):
        return "lab"
    if content_kind == "experience":
        return "teacher"
    if any(key in text for key in SCHOOL_KEYS):
        return "school"
    return "school"


def compute_actionability(title: str, source_name: str, deadline_text: str, content_kind: str, category: str) -> Dict[str, Any]:
    text = f"{title} {source_name} {deadline_text}"
    score = 0
    score += sum(20 for key in POSITIVE_KEYS if key in text)
    score -= sum(18 for key in NEGATIVE_KEYS if key in text)
    if deadline_text:
        score += 15
    if content_kind == "experience":
        score += 12
    if category == "school":
        score += 10
    if category == "lab":
        score += 2
    if category == "teacher":
        score -= 2
    level = "high" if score >= 30 else "medium" if score >= 10 else "low"
    return {"actionScore": score, "actionable": score >= 30, "level": level}


def html_to_text(content: str) -> str:
    content = re.sub(r"<script.*?>.*?</script>", " ", content, flags=re.I | re.S)
    content = re.sub(r"<style.*?>.*?</style>", " ", content, flags=re.I | re.S)
    content = re.sub(r"<br\s*/?>", "\n", content, flags=re.I)
    content = re.sub(r"</p>", "\n", content, flags=re.I)
    content = re.sub(r"</div>", "\n", content, flags=re.I)
    content = re.sub(r"<[^>]+>", " ", content)
    content = html.unescape(content)
    lines = [normalize_space(line) for line in content.splitlines()]
    return "\n".join([line for line in lines if line])


def extract_title_from_html(content: str) -> str:
    for pat in [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']twitter:title["\'][^>]+content=["\']([^"\']+)["\']',
        r'<h1[^>]*>(.*?)</h1>',
        r'<title[^>]*>(.*?)</title>',
    ]:
        m = re.search(pat, content, flags=re.I | re.S)
        if not m:
            continue
        title = normalize_space(re.sub(r"<[^>]+>", " ", html.unescape(m.group(1))))
        if title:
            return title
    return ""


def fetch_url(url: str) -> Dict[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        try:
            body = raw.decode(charset, errors="ignore")
        except LookupError:
            body = raw.decode("utf-8", errors="ignore")
        return {"final_url": resp.geturl(), "html": body}


def extract_links(html_content: str, base_url: str) -> List[Dict[str, str]]:
    links: List[Dict[str, str]] = []
    pattern = re.compile(r"<a\b[^>]*href=[\"']?([^\"' >]+)[\"']?[^>]*>(.*?)</a>", re.I | re.S)
    for href, anchor_html in pattern.findall(html_content):
        href = href.strip()
        if not href or href.startswith("javascript:") or href.startswith("#"):
            continue
        links.append({
            "url": urllib.parse.urljoin(base_url, href),
            "text": normalize_space(re.sub(r"<[^>]+>", " ", html.unescape(anchor_html))),
        })
    deduped: List[Dict[str, str]] = []
    seen = set()
    for link in links:
        if link["url"] in seen:
            continue
        seen.add(link["url"])
        deduped.append(link)
    return deduped


def extract_meta_description(content: str) -> str:
    for pat in [
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']twitter:description["\'][^>]+content=["\']([^"\']+)["\']',
    ]:
        m = re.search(pat, content, flags=re.I | re.S)
        if m:
            desc = normalize_space(html.unescape(m.group(1)))
            if desc:
                return desc
    return ""


def pick_profile_summary(text: str, title: str, category: str) -> str:
    lines = [normalize_space(line) for line in text.splitlines() if normalize_space(line)]
    keys = SUMMARY_KEYS[:]
    if category == "teacher":
        keys += ["研究方向", "个人简介", "个人介绍", "Biography", "Bio", "Interests", "Email", "招生"]
    if category == "lab":
        keys += ["研究方向", "实验室简介", "团队介绍", "研究组", "招生", "加入我们"]

    picked: List[str] = []
    for line in lines:
        if len(line) < 12:
            continue
        if title and normalize_space(line) == normalize_space(title):
            continue
        if any(key.lower() in line.lower() for key in keys):
            picked.append(line)
        if len(picked) >= 3:
            break
    if not picked:
        for line in lines:
            if len(line) >= 24:
                picked.append(line)
            if len(picked) >= 2:
                break
    return "；".join(picked[:2])[:260]


def extract_github_url(links: List[Dict[str, str]]) -> str:
    for link in links:
        if "github.com/" in link["url"].lower():
            return link["url"]
    return ""


def fetch_github_summary(url: str) -> str:
    if not url:
        return ""
    try:
        fetched = fetch_url(url)
    except Exception:
        return ""
    desc = extract_meta_description(fetched["html"])
    if desc:
        return desc[:220]
    text = html_to_text(fetched["html"])
    for line in text.splitlines():
        line = normalize_space(line)
        if 18 <= len(line) <= 220:
            return line
    return ""


def merge_profile_summary(category: str, official_summary: str, github_summary: str) -> str:
    parts: List[str] = []
    if official_summary:
        parts.append(("官网简介：" if category in {"teacher", "lab"} else "页面摘要：") + official_summary)
    if github_summary:
        parts.append("GitHub 简介：" + github_summary)
    return " ｜ ".join(parts)[:420]


def pick_summary(text: str, title: str) -> str:
    lines = [normalize_space(line) for line in text.splitlines() if normalize_space(line)]
    picked: List[str] = []
    for line in lines:
        if len(line) < 12:
            continue
        if title and line == title:
            continue
        if any(key in line for key in SUMMARY_KEYS):
            picked.append(line)
        if len(picked) >= 3:
            break
    if not picked:
        for line in lines:
            if len(line) >= 18:
                picked.append(line)
            if len(picked) >= 2:
                break
    summary = "；".join(picked[:2])
    return summary[:220]


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        conn.commit()


def db_connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notice_meta (
            url TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'new',
            starred INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notice_enrichment (
            url TEXT PRIMARY KEY,
            resolved_title TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            entity_name TEXT NOT NULL DEFAULT '',
            homepage_url TEXT NOT NULL DEFAULT '',
            github_url TEXT NOT NULL DEFAULT '',
            official_summary TEXT NOT NULL DEFAULT '',
            github_summary TEXT NOT NULL DEFAULT '',
            profile_summary TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )
    try:
        ensure_column(conn, "notices", "source_level", "TEXT")
        ensure_column(conn, "notices", "content_kind", "TEXT")
        ensure_column(conn, "notices", "source_tier", "TEXT")
    except sqlite3.OperationalError:
        pass
    ensure_column(conn, "notice_enrichment", "entity_name", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "notice_enrichment", "homepage_url", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "notice_enrichment", "github_url", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "notice_enrichment", "official_summary", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "notice_enrichment", "github_summary", "TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "notice_enrichment", "profile_summary", "TEXT NOT NULL DEFAULT ''")
    conn.commit()
    return conn


def fetch_items(conn: sqlite3.Connection, source_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          n.url,
          n.source_name,
          n.title,
          n.first_seen_at,
          n.fit_score,
          n.deadline_text,
          COALESCE(n.content_kind, '') AS content_kind,
          COALESCE(n.source_tier, '') AS source_tier,
          COALESCE(n.source_level, '') AS source_level,
          COALESCE(m.status, 'new') AS status,
          COALESCE(m.starred, 0) AS starred,
          COALESCE(m.notes, '') AS notes,
          COALESCE(e.resolved_title, '') AS resolved_title,
          COALESCE(e.summary, '') AS summary,
          COALESCE(e.entity_name, '') AS entity_name,
          COALESCE(e.homepage_url, '') AS homepage_url,
          COALESCE(e.github_url, '') AS github_url,
          COALESCE(e.official_summary, '') AS official_summary,
          COALESCE(e.github_summary, '') AS github_summary,
          COALESCE(e.profile_summary, '') AS profile_summary
        FROM notices n
        LEFT JOIN notice_meta m ON n.url = m.url
        LEFT JOIN notice_enrichment e ON n.url = e.url
        ORDER BY n.first_seen_at DESC
        """
    ).fetchall()

    items: List[Dict[str, Any]] = []
    for row in rows:
        source_meta = source_map.get(row["source_name"], {})
        deadline = parse_deadline(row["deadline_text"] or "")
        content_kind = (row["content_kind"] or source_meta.get("content_kind") or "official").lower()
        source_level_value = (row["source_level"] or source_meta.get("source_level") or "").lower()
        raw_title = row["resolved_title"] or row["title"] or "未命名标题"
        fallback_title = humanize_title(raw_title, source_meta)
        entity_name = clean_entity_name(row["entity_name"] or "")
        title = entity_name or fallback_title
        category = classify_category(row["source_name"] or "", title, content_kind, source_level_value)
        homepage_url = row["homepage_url"] or row["url"]
        summary = row["profile_summary"] or row["summary"] or ""
        item = {
            "url": row["url"],
            "homepageUrl": homepage_url,
            "githubUrl": row["github_url"] or "",
            "title": title,
            "entityName": entity_name or title,
            "sourceName": row["source_name"] or "未命名来源",
            "school": source_meta.get("school") or guess_school(row["source_name"] or "", title),
            "college": source_meta.get("college", ""),
            "tier": row["source_tier"] or source_meta.get("tier", ""),
            "contentKind": content_kind,
            "category": category,
            "sourceLevel": source_level_value,
            "fitScore": int(row["fit_score"] or 0),
            "deadlineText": row["deadline_text"] or "",
            "parsedDeadline": deadline["parsed"],
            "daysLeft": deadline["days_left"],
            "firstSeenAt": row["first_seen_at"] or "",
            "status": row["status"] if row["status"] in STATUS_VALUES else "new",
            "starred": bool(row["starred"]),
            "notes": row["notes"] or "",
            "summary": summary,
            "officialSummary": row["official_summary"] or "",
            "githubSummary": row["github_summary"] or "",
        }
        item.update(compute_actionability(item["title"], item["sourceName"], item["deadlineText"], content_kind, category))
        items.append(item)
    return items


def enrich_items(conn: sqlite3.Connection, items: List[Dict[str, Any]], limit: int = 20) -> int:
    targets = [item for item in items if not item.get("summary") or item.get("title") == "未命名标题" or item.get("category") in {"teacher", "lab"}][:limit]
    done = 0
    for item in targets:
        try:
            fetched = fetch_url(item.get("homepageUrl") or item["url"])
            homepage_url = fetched.get("final_url") or item.get("homepageUrl") or item["url"]
            resolved_title = extract_title_from_html(fetched["html"]) or item["title"]
            text = html_to_text(fetched["html"])
            links = extract_links(fetched["html"], homepage_url)
            if 'mp.weixin.qq.com' in item['url'] and resolved_title == '未命名标题':
                resolved_title = extract_title_from_html(fetched['html']) or resolved_title

            entity_name = item.get("entityName") or humanize_title(resolved_title, {
                "source_level": item.get("sourceLevel", ""),
                "mentor": item.get("title", ""),
            })
            entity_name = clean_entity_name(entity_name or resolved_title or item.get("title", ""))

            category = item.get("category", "school")
            official_summary = pick_profile_summary(text, entity_name or resolved_title, category) if category in {"teacher", "lab"} else pick_summary(text, resolved_title)
            github_url = extract_github_url(links)
            github_summary = fetch_github_summary(github_url) if category in {"teacher", "lab"} else ""
            profile_summary = merge_profile_summary(category, official_summary, github_summary) or official_summary or pick_summary(text, resolved_title)
            summary = profile_summary if category in {"teacher", "lab"} else (official_summary or pick_summary(text, resolved_title))

            conn.execute(
                """
                INSERT INTO notice_enrichment (
                  url, resolved_title, summary, entity_name, homepage_url, github_url,
                  official_summary, github_summary, profile_summary, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                  resolved_title = excluded.resolved_title,
                  summary = excluded.summary,
                  entity_name = excluded.entity_name,
                  homepage_url = excluded.homepage_url,
                  github_url = excluded.github_url,
                  official_summary = excluded.official_summary,
                  github_summary = excluded.github_summary,
                  profile_summary = excluded.profile_summary,
                  updated_at = excluded.updated_at
                """,
                (item["url"], resolved_title, summary, entity_name, homepage_url, github_url, official_summary, github_summary, profile_summary, now_iso()),
            )
            done += 1
        except urllib.error.URLError:
            continue
        except Exception:
            continue
    conn.commit()
    return done


def filter_items(items: List[Dict[str, Any]], query: Dict[str, str]) -> List[Dict[str, Any]]:
    kind = query.get("kind", "all")
    status = query.get("status", "all")
    category = query.get("category", "all")
    source = query.get("source", "all")
    q = query.get("q", "").strip().lower()
    sort = query.get("sort", "latest")
    only_actionable = query.get("onlyActionable", "0") == "1"

    out = []
    for item in items:
        if kind != "all" and item["contentKind"] != kind:
            continue
        if status != "all" and item["status"] != status:
            continue
        if category != "all" and item["category"] != category:
            continue
        if only_actionable and not item.get("actionable"):
            continue
        source_value = item["school"] or item["sourceName"]
        if source != "all" and source_value != source:
            continue
        if q:
            hay = " ".join([
                item["title"],
                item.get("entityName", ""),
                item["sourceName"],
                item["school"],
                item.get("college", ""),
                item["notes"],
                item.get("summary", ""),
                item.get("officialSummary", ""),
                item.get("githubSummary", ""),
                item["deadlineText"],
            ]).lower()
            if q not in hay:
                continue
        out.append(item)

    if sort == "fit":
        out.sort(key=lambda x: (x["fitScore"], x["actionScore"], x["firstSeenAt"]), reverse=True)
    elif sort == "deadline":
        out.sort(key=lambda x: (99999 if x["daysLeft"] is None else x["daysLeft"], -x["fitScore"]))
    else:
        out.sort(key=lambda x: x["firstSeenAt"], reverse=True)
    return out


def build_overview(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "total": len(items),
        "official": sum(1 for item in items if item["contentKind"] == "official"),
        "experience": sum(1 for item in items if item["contentKind"] == "experience"),
        "schoolCount": sum(1 for item in items if item["category"] == "school"),
        "labCount": sum(1 for item in items if item["category"] == "lab"),
        "teacherCount": sum(1 for item in items if item["category"] == "teacher"),
        "newCount": sum(1 for item in items if item["status"] == "new"),
        "starred": sum(1 for item in items if item["starred"]),
        "deadlineSoon": sum(1 for item in items if isinstance(item["daysLeft"], int) and 0 <= item["daysLeft"] <= 7 and item["status"] != "ignored"),
        "actionable": sum(1 for item in items if item.get("actionable")),
    }


def build_source_options(items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    values: List[Dict[str, str]] = []
    seen = set()
    for item in items:
        label = item["school"] or item["sourceName"]
        if not label or label in seen:
            continue
        seen.add(label)
        values.append({"value": label, "label": label})
    values.sort(key=lambda x: x["label"])
    return values


def build_highlights(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    today_prefix = dt.date.today().isoformat()
    today_items = [item for item in items if str(item.get("firstSeenAt", "")).startswith(today_prefix)]
    today_items.sort(key=lambda x: (x["actionScore"], x["fitScore"], x["firstSeenAt"]), reverse=True)

    urgent = [item for item in items if item.get("actionable") and isinstance(item.get("daysLeft"), int) and 0 <= item["daysLeft"] <= 30 and item["status"] != "ignored"]
    urgent.sort(key=lambda x: (x["daysLeft"], -x["fitScore"]))

    high_fit = [item for item in items if item.get("actionable")]
    high_fit.sort(key=lambda x: (x["fitScore"], x["actionScore"], x["firstSeenAt"]), reverse=True)
    return {"today": today_items[:6], "urgent": urgent[:6], "highFit": high_fit[:6]}


def update_notice_state(conn: sqlite3.Connection, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = str(payload.get("url", "")).strip()
    if not url:
        raise ValueError("missing url")

    existing = conn.execute("SELECT status, starred, notes FROM notice_meta WHERE url = ? LIMIT 1", (url,)).fetchone()
    status = str(payload.get("status", existing["status"] if existing else "new")).strip()
    if status not in STATUS_VALUES:
        raise ValueError("invalid status")
    starred = int(bool(payload.get("starred", existing["starred"] if existing else 0)))
    notes = str(payload.get("notes", existing["notes"] if existing else ""))

    conn.execute(
        """
        INSERT INTO notice_meta (url, status, starred, notes, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
          status = excluded.status,
          starred = excluded.starred,
          notes = excluded.notes,
          updated_at = excluded.updated_at
        """,
        (url, status, starred, notes, now_iso()),
    )
    conn.commit()
    return {"ok": True}


def read_text_tail(path: Path, max_chars: int = 10000) -> str:
    if not path.exists():
        return "暂无日志"
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text if len(text) <= max_chars else text[-max_chars:]


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_scan_status(status_path: Path) -> Dict[str, Any]:
    if not status_path.exists():
        return {"running": False, "message": "提示：可以直接在页面里点“立即扫描”执行一次保研雷达扫描。"}
    data = load_json(status_path)
    pid = data.get("pid")
    if data.get("running") and isinstance(pid, int) and not pid_alive(pid):
        data["running"] = False
    return data


def write_scan_status(status_path: Path, payload: Dict[str, Any]) -> None:
    status_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def monitor_process(proc: subprocess.Popen, status_path: Path, log_path: Path, root: Path) -> None:
    return_code = proc.wait()
    try:
        conn = db_connect(root / "state" / "radar.db")
        try:
            items = fetch_items(conn, load_source_map(root / "config" / "targets.local.json"))
            enrich_items(conn, items, limit=18)
        finally:
            conn.close()
    except Exception:
        pass

    status = read_scan_status(status_path)
    status.update({
        "running": False,
        "finishedAt": now_iso(),
        "lastExitCode": return_code,
        "message": "上次扫描完成。" if return_code == 0 else f"扫描结束，但退出码为 {return_code}。",
        "log": read_text_tail(log_path),
    })
    status.pop("pid", None)
    write_scan_status(status_path, status)


def trigger_scan(root: Path, status_path: Path, log_path: Path) -> Dict[str, Any]:
    profile_path = root / "config" / "profile.local.json"
    targets_path = root / "config" / "targets.local.json"
    db_path = root / "state" / "radar.db"
    if not profile_path.exists() or not targets_path.exists():
        raise FileNotFoundError("缺少 profile.local.json 或 targets.local.json，请先完成 setup_web.py 配置。")

    current = read_scan_status(status_path)
    if current.get("running") and isinstance(current.get("pid"), int) and pid_alive(current["pid"]):
        return {"ok": True, "message": "已经有扫描任务在运行。"}

    cmd = [
        sys.executable,
        str(root / "scripts" / "baoyan_radar.py"),
        "once",
        "--profile", str(profile_path),
        "--targets", str(targets_path),
        "--db", str(db_path),
        "--push-mode", "digest",
        "--send-empty-digest",
    ]

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write(f"[{now_iso()}] scan started\n")
        fh.flush()
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=str(root))

    status = {"running": True, "startedAt": now_iso(), "pid": proc.pid, "message": "扫描已启动，完成后会刷新到列表里。", "log": read_text_tail(log_path)}
    write_scan_status(status_path, status)
    threading.Thread(target=monitor_process, args=(proc, status_path, log_path, root), daemon=True).start()
    return {"ok": True, "message": "扫描已启动。"}


def trigger_enrich(root: Path, limit: int = 24) -> Dict[str, Any]:
    conn = db_connect(root / "state" / "radar.db")
    try:
        items = fetch_items(conn, load_source_map(root / "config" / "targets.local.json"))
        count = enrich_items(conn, items, limit=limit)
    finally:
        conn.close()
    return {"ok": True, "enriched": count}


def load_targets(root: Path) -> Dict[str, Any]:
    return load_json(root / "config" / "targets.local.json")


def resolve_school_from_message(message: str, targets: Dict[str, Any]) -> str:
    schools = sorted({str(item.get("school", "")).strip() for item in targets.get("sources", []) or [] if str(item.get("school", "")).strip()}, key=len, reverse=True)
    for school in schools:
        if school and school in message:
            return school
    aliases = {
        "上交": "上海交通大学",
        "交大": "上海交通大学",
        "中科大": "中国科学技术大学",
        "科大": "中国科学技术大学",
        "武大": "武汉大学",
        "南大": "南京大学",
        "华科": "华中科技大学",
        "华科大": "华中科技大学",
        "东大": "东南大学",
        "中大": "中山大学",
        "哈工大": "哈尔滨工业大学",
        "北航": "北京航空航天大学",
        "北理": "北京理工大学",
        "西交": "西安交通大学",
        "山大": "山东大学",
        "湖大": "湖南大学",
        "同济": "同济大学",
    }
    for alias, school in aliases.items():
        if alias in message:
            return school
    return ""


def resolve_command_intent(message: str) -> Dict[str, Any]:
    msg = normalize_space(message)
    want_teacher = any(token in msg for token in ["老师", "导师", "教师"])
    want_lab = any(token in msg for token in ["实验室", "研究组", "团队"])
    want_experience = "经验" in msg or "面经" in msg
    if want_teacher:
        category = "teacher"
    elif want_lab:
        category = "lab"
    else:
        category = "school"
    return {
        "message": msg,
        "category": category,
        "kind": "experience" if want_experience else "official",
        "should_scan": any(token in msg for token in ["扫描", "刷新", "更新", "搜", "抓", "看看", "查一下", "查查", "帮我"]),
    }


def select_sources_for_command(targets: Dict[str, Any], school: str, category: str, kind: str) -> Dict[str, Any]:
    sources = targets.get("sources", []) or []
    school_sources = [item for item in sources if str(item.get("school", "")).strip() == school] if school else sources[:]
    selected: List[Dict[str, Any]] = []
    fallback_note = ""

    if category == "teacher":
        selected = [item for item in school_sources if str(item.get("source_level", "")).strip().lower() == "mentor"]
        if not selected and school:
            labs = [item for item in school_sources if str(item.get("source_level", "")).strip().lower() == "lab"]
            officials = [item for item in school_sources if str(item.get("content_kind", "official")).strip().lower() == "official"]
            selected = labs or officials
            if selected:
                fallback_note = f"当前未配置{school}老师主页源，先改为扫描该校{'实验室' if labs else '学院/官网'}来源。"
    elif category == "lab":
        selected = [item for item in school_sources if str(item.get("source_level", "")).strip().lower() == "lab"]
        if not selected and school:
            officials = [item for item in school_sources if str(item.get("content_kind", "official")).strip().lower() == "official"]
            selected = officials
            if selected:
                fallback_note = f"当前未配置{school}实验室源，先改为扫描该校学院/官网来源。"
    else:
        if kind == "experience":
            selected = [item for item in school_sources if str(item.get("content_kind", "official")).strip().lower() == "experience"]
        if not selected:
            selected = [item for item in school_sources if str(item.get("content_kind", "official")).strip().lower() == "official"] or school_sources

    return {"sources": selected, "fallback_note": fallback_note}


def run_targeted_scan(root: Path, selected_sources: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not selected_sources:
        return {"ok": False, "error": "没有匹配到可扫描的来源。"}
    targets = load_targets(root)
    subset = {key: value for key, value in targets.items() if key != "sources"}
    subset["sources"] = selected_sources
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as fh:
        json.dump(subset, fh, ensure_ascii=False, indent=2)
        temp_targets = fh.name
    try:
        cmd = [
            sys.executable,
            str(root / "scripts" / "baoyan_radar.py"),
            "once",
            "--profile", str(root / "config" / "profile.local.json"),
            "--targets", temp_targets,
            "--db", str(root / "state" / "radar.db"),
            "--print-only",
        ]
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=240)
        stdout = proc.stdout.strip() or "[]"
        try:
            payload = json.loads(stdout)
            scanned = len(payload) if isinstance(payload, list) else 0
        except Exception:
            payload = []
            scanned = 0
        conn = db_connect(root / "state" / "radar.db")
        try:
            items = fetch_items(conn, load_source_map(root / "config" / "targets.local.json"))
            enrich_items(conn, items, limit=36)
        finally:
            conn.close()
        return {
            "ok": proc.returncode == 0,
            "scanned": scanned,
            "stdout": stdout[-4000:],
            "stderr": (proc.stderr or "")[-2000:],
        }
    finally:
        try:
            os.unlink(temp_targets)
        except OSError:
            pass


def handle_assistant_command(root: Path, message: str) -> Dict[str, Any]:
    msg = normalize_space(message)
    if not msg:
        raise ValueError("请输入想让我执行的内容。")

    targets = load_targets(root)
    intent = resolve_command_intent(msg)
    school = resolve_school_from_message(msg, targets)
    selection = select_sources_for_command(targets, school, intent["category"], intent["kind"])
    sources = selection["sources"]
    fallback_note = selection["fallback_note"]

    if not sources:
        school_text = school or "当前配置"
        return {
            "ok": False,
            "reply": f"我没在现有配置里找到和“{school_text}”匹配的可扫描来源。你可以先在 targets.local.json 里补这个学校的老师/实验室源。",
        }

    scan_result = run_targeted_scan(root, sources) if intent["should_scan"] else {"ok": True, "scanned": 0}
    source_labels = [str(item.get("name", "未命名来源")) for item in sources[:6]]
    if len(sources) > 6:
        source_labels.append(f"…共 {len(sources)} 个来源")

    filters: Dict[str, Any] = {
        "source": school or "all",
        "category": intent["category"] if intent["category"] in CATEGORY_VALUES else "all",
        "kind": intent["kind"],
        "onlyActionable": False,
        "sort": "latest",
    }
    if fallback_note and filters["category"] == "teacher":
        if any(str(item.get("source_level", "")).strip().lower() == "lab" for item in sources):
            filters["category"] = "lab"
        else:
            filters["category"] = "school"

    reply_parts = []
    if school:
        reply_parts.append(f"已按“{school}”处理")
    else:
        reply_parts.append("已按当前配置处理")
    if intent["category"] == "teacher":
        reply_parts.append("老师相关来源")
    elif intent["category"] == "lab":
        reply_parts.append("实验室相关来源")
    else:
        reply_parts.append("学院/官网相关来源")
    if intent["should_scan"]:
        reply_parts.append(f"扫描完成，命中 {scan_result.get('scanned', 0)} 条新增记录")
    reply = "，".join(reply_parts) + "。"
    if fallback_note:
        reply += fallback_note
    reply += " 已帮你刷新列表并切到对应筛选。"

    return {
        "ok": bool(scan_result.get("ok", True)),
        "reply": reply,
        "filters": filters,
        "matchedSources": source_labels,
        "scanned": scan_result.get("scanned", 0),
        "stderr": scan_result.get("stderr", ""),
    }


def json_response(handler: BaseHTTPRequestHandler, payload: Dict[str, Any], status: int = 200) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def text_response(handler: BaseHTTPRequestHandler, body: str, status: int = 200) -> None:
    data = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def read_json_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length > 0 else b"{}"
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def make_handler(root: Path, host: str, port: int):
    dashboard_dist = root / "dashboard" / "dist"
    db_path = root / "state" / "radar.db"
    targets_path = root / "config" / "targets.local.json"
    scan_status_path = root / "state" / "dashboard-scan-status.json"
    scan_log_path = root / "state" / "dashboard-scan.log"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def _serve_static(self, request_path: str) -> None:
            if not dashboard_dist.exists():
                text_response(self, "<h1>Dashboard not built</h1><pre>cd dashboard && npm install && npm run build</pre>", status=500)
                return
            rel = request_path.lstrip("/") or "index.html"
            file_path = dashboard_dist / rel
            if file_path.is_dir():
                file_path = file_path / "index.html"
            if not file_path.exists() or not file_path.is_file():
                file_path = dashboard_dist / "index.html"
            data = file_path.read_bytes()
            mime, _ = mimetypes.guess_type(str(file_path))
            self.send_response(200)
            self.send_header("Content-Type", f"{mime or 'application/octet-stream'}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            if path == "/api/health":
                json_response(self, {"ok": True})
                return
            if path == "/api/overview":
                conn = db_connect(db_path)
                try:
                    items = fetch_items(conn, load_source_map(targets_path))
                finally:
                    conn.close()
                json_response(self, build_overview(items))
                return
            if path == "/api/notices":
                conn = db_connect(db_path)
                try:
                    items = fetch_items(conn, load_source_map(targets_path))
                finally:
                    conn.close()
                query = dict(urllib.parse.parse_qsl(parsed.query))
                filtered = filter_items(items, query)
                json_response(self, {"items": filtered, "total": len(filtered), "options": {"sources": build_source_options(items)}})
                return
            if path == "/api/highlights":
                conn = db_connect(db_path)
                try:
                    items = fetch_items(conn, load_source_map(targets_path))
                finally:
                    conn.close()
                json_response(self, build_highlights(items))
                return
            if path == "/api/scan-status":
                payload = read_scan_status(scan_status_path)
                payload["log"] = read_text_tail(scan_log_path)
                json_response(self, payload)
                return
            self._serve_static(path)

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            try:
                if path == "/api/notices/state":
                    payload = read_json_body(self)
                    conn = db_connect(db_path)
                    try:
                        result = update_notice_state(conn, payload)
                    finally:
                        conn.close()
                    json_response(self, result)
                    return
                if path == "/api/scan":
                    json_response(self, trigger_scan(root, scan_status_path, scan_log_path))
                    return
                if path == "/api/enrich":
                    payload = read_json_body(self)
                    limit = int(payload.get("limit", 24))
                    json_response(self, trigger_enrich(root, limit=limit))
                    return
                if path == "/api/assistant-command":
                    payload = read_json_body(self)
                    message = str(payload.get("message", ""))
                    json_response(self, handle_assistant_command(root, message))
                    return
                json_response(self, {"ok": False, "error": "not found"}, status=404)
            except FileNotFoundError as exc:
                json_response(self, {"ok": False, "error": str(exc)}, status=400)
            except ValueError as exc:
                json_response(self, {"ok": False, "error": str(exc)}, status=400)
            except json.JSONDecodeError:
                json_response(self, {"ok": False, "error": "invalid json body"}, status=400)
            except Exception as exc:
                json_response(self, {"ok": False, "error": str(exc)}, status=500)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Run baoyan dashboard web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    server = ThreadingHTTPServer((args.host, args.port), make_handler(root, args.host, args.port))
    print(f"[OK] baoyan dashboard running at http://{args.host}:{args.port}/")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
