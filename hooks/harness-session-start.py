#!/usr/bin/env python3
"""
Harness Session Start — SessionStart hook
Usage: python3 harness-session-start.py [PREFIX|auto]
  auto: reads prefix from .claude/harness.config.json in CWD
"""
import glob
import json
import os
import re
import sys

def get_prefix(raw):
    if raw != "auto":
        return raw
    config_path = os.path.join(os.getcwd(), ".claude", "harness.config.json")
    if os.path.exists(config_path):
        try:
            cfg = json.load(open(config_path))
            return cfg.get("prefix", "proj")
        except Exception:
            pass
    return re.sub(r'[^a-z0-9]', '', os.path.basename(os.getcwd()).lower())[:8] or "proj"


def main():
    raw = sys.argv[1] if len(sys.argv) > 1 else "auto"
    prefix = get_prefix(raw)

    removed = []
    for f in glob.glob(f'/tmp/{prefix}_*'):
        try:
            os.remove(f)
            removed.append(os.path.basename(f))
        except Exception:
            pass

    print("OK")


if __name__ == "__main__":
    main()
