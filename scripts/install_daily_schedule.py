#!/usr/bin/env python3
import platform
import subprocess
import sys
from pathlib import Path


def main() -> int:
    system = platform.system().lower()
    scripts_dir = Path(__file__).resolve().parent
    argv = sys.argv[1:]

    if system == "darwin":
        target = scripts_dir / "install_daily_launch_agent.py"
    elif system == "windows":
        target = scripts_dir / "install_windows_schtask.py"
    else:
        print(f"Unsupported OS for auto scheduler install: {platform.system()}", file=sys.stderr)
        print("Supported: macOS (LaunchAgent), Windows (schtasks)", file=sys.stderr)
        return 2

    result = subprocess.run([sys.executable, str(target)] + argv)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
