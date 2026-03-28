#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["lz4"]
# ///
"""Count Firefox tabs by reading the session recovery file."""

import argparse
import configparser
import json
import sys
from pathlib import Path

import lz4.block


def find_firefox_dirs() -> list[Path]:
    """Return candidate Firefox profile root directories, in priority order."""
    home = Path.home()
    candidates = [
        # Linux snap
        home / "snap/firefox/common/.mozilla/firefox",
        # Linux native
        home / ".mozilla/firefox",
        # macOS
        home / "Library/Application Support/Firefox",
    ]
    return [d for d in candidates if d.is_dir()]


def find_default_profile(firefox_dir: Path) -> Path | None:
    """Parse profiles.ini to find the default profile path."""
    ini = firefox_dir / "profiles.ini"
    if not ini.exists():
        return None

    config = configparser.ConfigParser()
    config.read(ini)

    # Look for an Install* section with a Default key (Firefox >= 67)
    for section in config.sections():
        if section.startswith("Install") and "Default" in config[section]:
            profile_path = config[section]["Default"]
            resolved = (firefox_dir / profile_path).resolve()
            if resolved.is_dir():
                return resolved

    # Fall back to Profile section marked Default=1
    for section in config.sections():
        if section.startswith("Profile") and config[section].get("Default") == "1":
            profile_path = config[section]["Path"]
            if config[section].get("IsRelative") == "1":
                resolved = (firefox_dir / profile_path).resolve()
            else:
                resolved = Path(profile_path)
            if resolved.is_dir():
                return resolved

    return None


def find_recovery_file(profile: Path | None = None) -> Path:
    """Locate recovery.jsonlz4, either from an explicit profile or by auto-detection."""
    if profile:
        f = Path(profile) / "sessionstore-backups" / "recovery.jsonlz4"
        if not f.exists():
            print(f"error: recovery file not found at {f}", file=sys.stderr)
            sys.exit(1)
        return f

    for firefox_dir in find_firefox_dirs():
        prof = find_default_profile(firefox_dir)
        if prof:
            f = prof / "sessionstore-backups" / "recovery.jsonlz4"
            if f.exists():
                return f

    print(
        "error: could not find Firefox recovery file. "
        "Is Firefox running? Use --profile to specify the profile directory.",
        file=sys.stderr,
    )
    sys.exit(1)


def read_session(path: Path) -> dict:
    """Read and decompress a .jsonlz4 session file."""
    with open(path, "rb") as f:
        f.read(8)  # skip mozlz4 magic header
        return json.loads(lz4.block.decompress(f.read()))


def count_tabs(session: dict) -> dict:
    """Extract tab counts from session data."""
    windows = session.get("windows", [])
    per_window = []
    pinned_total = 0

    for win in windows:
        tabs = win.get("tabs", [])
        per_window.append(len(tabs))
        pinned_total += sum(1 for t in tabs if t.get("pinned", False))

    return {
        "tabs": sum(per_window),
        "windows": len(windows),
        "pinned": pinned_total,
        "per_window": per_window,
    }


def format_human(counts: dict) -> str:
    per_win = ", ".join(str(n) for n in counts["per_window"])
    lines = [
        f"Tabs:    {counts['tabs']} ({counts['pinned']} pinned)",
        f"Windows: {counts['windows']} ({per_win})",
    ]
    return "\n".join(lines)


def format_influx(counts: dict) -> str:
    return f"firefox_tabs tabs={counts['tabs']}i,windows={counts['windows']}i,pinned={counts['pinned']}i"


def main():
    parser = argparse.ArgumentParser(description="Count Firefox tabs")
    parser.add_argument(
        "--influx", action="store_true", help="Output in InfluxDB line protocol"
    )
    parser.add_argument(
        "--profile", type=Path, help="Firefox profile directory (auto-detected if omitted)"
    )
    args = parser.parse_args()

    recovery = find_recovery_file(args.profile)
    session = read_session(recovery)
    counts = count_tabs(session)

    if args.influx:
        print(format_influx(counts))
    else:
        print(format_human(counts))


if __name__ == "__main__":
    main()
