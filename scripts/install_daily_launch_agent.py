#!/usr/bin/env python3
import argparse
import plistlib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Install a macOS LaunchAgent for daily baoyan-radar scans")
    parser.add_argument("--python", default="/usr/bin/python3", help="Python executable path")
    parser.add_argument("--script", default=None, help="Path to baoyan_radar.py (defaults to sibling script)")
    parser.add_argument("--profile", required=True, help="Local private profile JSON")
    parser.add_argument("--targets", required=True, help="Local targets JSON")
    parser.add_argument("--db", required=True, help="SQLite DB path")
    parser.add_argument("--hour", type=int, default=9, help="Daily hour 0-23")
    parser.add_argument("--minute", type=int, default=0, help="Daily minute 0-59")
    parser.add_argument("--label", default="ai.openclaw.baoyan-radar.daily", help="LaunchAgent label")
    parser.add_argument("--print-only", action="store_true", help="Run scans without Feishu push")
    parser.add_argument("--push-mode", choices=["item", "digest"], default="digest", help="Push individual hits or one digest")
    parser.add_argument("--send-empty-digest", action="store_true", help="Send digest even when no new items are found")
    parser.add_argument("--output", help="Custom plist output path")
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
    log_dir = db_path.parent
    launch_agents = Path.home() / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)
    plist_path = Path(args.output).expanduser() if args.output else launch_agents / f"{args.label}.plist"

    program_arguments = [
        args.python,
        str(script_path),
        "once",
        "--profile", str(profile),
        "--targets", str(targets),
        "--db", str(db_path),
    ]
    if args.print_only:
        program_arguments.append("--print-only")
    else:
        program_arguments.extend(["--push-mode", args.push_mode])
        if args.send_empty_digest:
            program_arguments.append("--send-empty-digest")

    plist = {
        "Label": args.label,
        "ProgramArguments": program_arguments,
        "StartCalendarInterval": {
            "Hour": args.hour,
            "Minute": args.minute,
        },
        "StandardOutPath": str(log_dir / "baoyan-radar.stdout.log"),
        "StandardErrorPath": str(log_dir / "baoyan-radar.stderr.log"),
        "WorkingDirectory": str(script_path.parent.parent),
        "RunAtLoad": False,
    }

    with open(plist_path, "wb") as f:
        plistlib.dump(plist, f)

    print(f"[OK] Wrote LaunchAgent plist: {plist_path}")
    print("Next commands:")
    print(f"  launchctl unload {plist_path} 2>/dev/null || true")
    print(f"  launchctl load {plist_path}")
    print(f"  launchctl start {args.label}   # optional immediate test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
