# Preset expansion notes

Use these source tiers when expanding presets:

## 1. School-level official sources

Use graduate-school / admission portals for broad recall.

## 2. College-level official sources

Prefer these next for better precision:

- 计算机学院
- 人工智能学院
- 软件学院
- 电子信息相关学院
- 研究生培养 / 招生通知栏目

## 3. Lab / mentor sources

Use when available:

- lab homepage news page
- PI homepage
- group admissions page
- recent publications page

For mentor-oriented sources, preserve fields like:

```json
{
  "content_kind": "official",
  "source_level": "mentor",
  "school": "某大学",
  "college": "计算机学院",
  "lab": "视觉智能实验室",
  "mentor": "某老师",
  "name": "某老师主页",
  "url": "https://example.edu.cn/pi",
  "include_keywords": ["招生", "推免", "实验室", "视觉", "多模态"],
  "discipline_keywords": ["计算机视觉", "多模态", "大模型"]
}
```

## Practical rule

Keep school-level sources for recall.
Add college / lab / mentor sources for precision.
