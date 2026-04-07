"""
harness_common.py — 훅 공유 유틸리티
PREFIX 결정, deny 헬퍼 등 훅 간 공통 로직.
"""
import json
import os
import re
import sys


def get_prefix():
    """프로젝트별 prefix를 harness.config.json → 디렉토리명 → "proj" 폴백으로 유도."""
    config_path = os.path.join(os.getcwd(), ".claude", "harness.config.json")
    if os.path.exists(config_path):
        try:
            config = json.load(open(config_path))
            return config.get("prefix", "proj")
        except Exception:
            pass
    raw = os.path.basename(os.getcwd()).lower()
    return re.sub(r'[^a-z0-9]', '', raw)[:8] or "proj"


def deny(reason):
    """PreToolUse 훅에서 도구 실행을 거부한다."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason
        }
    }))
    sys.exit(0)


def flag_path(prefix, name):
    """플래그 파일 경로 반환."""
    return f"/tmp/{prefix}_{name}"


def flag_exists(prefix, name):
    """플래그 파일 존재 여부."""
    return os.path.exists(flag_path(prefix, name))
