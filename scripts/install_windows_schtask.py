#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Install a Windows Scheduled Task for daily baoyan-radar scans")
    parser.add_argument("--python", default=sys.executable, help="Python executable path")
    parser.add_argument("--script", default=None, help="Path to baoyan_radar.py (defaults to sibling script)")
    parser.add_argument("--profile", required=True, help="Local private profile JSON")
    parser.add_argument("--targets", required=True, help="Local targets JSON")
    parser.add_argument("--db", required=True, help="SQLite DB path")
    parser.add_argument("--hour", type=int, default=9, help="Daily hour 0-23")
    parser.add_argument("--minute", type=int, default=0, help="Daily minute 0-59")
    parser.add_argument("--label", default="BaoyanRadarDaily", help="Scheduled Task name")
    parser.add_argument("--print-only", action="store_true", help="Run scans without Feishu push")
    parser.add_argument("--push-mode", choices=["item", "digest"], default="digest", help="Push individual hits or one digest")
    parser.add_argument("--send-empty-digest", action="store_true", help="Send digest even when no new items are found")
    args = parser.parse_args()

    if not (0 <= args.hour <= 23):
        raise SystemExit("--hour must be between 0 and 23")
    if not (0 <= args.minute <= 59):
        raise SystemExit("--minute must be between 0 and 59")

    script_path = Path(args.script) if args.script else Path(__file__).with_name("baoyan_radar.py")
    profile = Path(args.profile).expanduser().resolve()
    targets = Path(args.targets).expanduser().resolve()
    db_path = Path(args.db).expanduser().resolve()

    if not script_path.exists():
        raise SystemExit(f"script not found: {script_path}")
    if not profile.exists():
        raise SystemExit(f"profile not found: {profile}")
    if not targets.exists():
        raise SystemExit(f"targets not found: {targets}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    run_args = [
        args.python,
        str(script_path),
        "once",
        "--profile", str(profile),
        "--targets", str(targets),
        "--db", str(db_path),
    ]
    if args.print_only:
        run_args.append("--print-only")
    else:
        run_args.extend(["--push-mode", args.push_mode])
        if args.send_empty_digest:
            run_args.append("--send-empty-digest")

    task_cmd = subprocess.list2cmdline(run_args)
    start_time = f"{args.hour:02d}:{args.minute:02d}"
    schtasks_cmd = [
        "schtasks",
        "/Create",
        "/SC", "DAILY",
        "/TN", args.label,
        "/TR", task_cmd,
        "/ST", start_time,
        "/F",
    ]
    subprocess.run(schtasks_cmd, check=True)

    print(f"[OK] Created Windows Scheduled Task: {args.label}")
    print("Next commands:")
    print(f"  schtasks /Run /TN {args.label}     REM optional immediate test")
    print(f"  schtasks /Query /TN {args.label}")
    print(f"  schtasks /Delete /TN {args.label} /F")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
