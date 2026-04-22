"""test_plugin_write_guard.py — plugin-write-guard PreToolUse 훅 테스트.

`~/.claude/plugins/{cache,marketplaces,data}/**` 쓰기 차단 + JSON deny 응답 계약
+ `CLAUDE_ALLOW_PLUGIN_EDIT=1` 우회를 subprocess 호출로 검증한다.

Run: python3 -m unittest discover -s ~/.claude/hooks/tests -p 'test_plugin_write_guard.py' -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent
HOOK = HOOKS_DIR / "plugin-write-guard.py"
PYTHON = sys.executable


def _run(payload: dict, env_extra: dict | None = None) -> tuple[str, str, int]:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_ALLOW_PLUGIN_EDIT"}
    env["HARNESS_FORCE_ENABLE"] = "1"
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(
        [PYTHON, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    return p.stdout, p.stderr, p.returncode


def _decision(stdout: str) -> str:
    """stdout JSON에서 permissionDecision 추출. JSON 아니면 빈 문자열."""
    stdout = stdout.strip()
    if not stdout:
        return ""
    try:
        data = json.loads(stdout)
        return data.get("hookSpecificOutput", {}).get("permissionDecision", "")
    except json.JSONDecodeError:
        return ""


def _reason(stdout: str) -> str:
    try:
        data = json.loads(stdout)
        return data.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
    except json.JSONDecodeError:
        return ""


class PluginDirBlockTests(unittest.TestCase):
    """세 가지 플러그인 서브디렉토리 모두 차단 확인."""

    def _assert_blocked(self, fp: str) -> str:
        out, err, rc = _run({
            "tool_name": "Write",
            "tool_input": {"file_path": fp},
        })
        self.assertEqual(rc, 0, f"exit 0 기대(JSON deny 패턴), stderr={err}")
        self.assertEqual(err.strip(), "", "stderr 비어야 함 (이제 JSON stdout만)")
        self.assertEqual(_decision(out), "deny", f"deny 기대: {out!r}")
        return _reason(out)

    def test_cache_blocked(self):
        reason = self._assert_blocked("~/.claude/plugins/cache/ralph-loop/1.0.0/hooks/stop-hook.sh")
        self.assertIn("plugin-write-guard", reason)
        self.assertIn("CLAUDE_ALLOW_PLUGIN_EDIT", reason)

    def test_marketplaces_blocked(self):
        reason = self._assert_blocked("~/.claude/plugins/marketplaces/foo.json")
        self.assertIn("커스텀 스킬", reason)

    def test_data_blocked(self):
        reason = self._assert_blocked("~/.claude/plugins/data/session-state.json")
        self.assertIn("재설치", reason)


class PassThroughTests(unittest.TestCase):
    """플러그인 디렉토리 밖은 통과."""

    def _assert_pass(self, payload: dict) -> None:
        out, err, rc = _run(payload)
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "", f"통과 시 무출력 기대: {out!r}")
        self.assertEqual(err.strip(), "")

    def test_src_passes(self):
        self._assert_pass({"tool_name": "Write", "tool_input": {"file_path": "/Users/x/proj/src/foo.ts"}})

    def test_docs_passes(self):
        self._assert_pass({"tool_name": "Edit", "tool_input": {"file_path": "/Users/x/proj/docs/architecture.md"}})

    def test_commands_passes(self):
        # ~/.claude/commands/ 는 커스텀 스킬 영역 — 허용
        self._assert_pass({"tool_name": "Write", "tool_input": {"file_path": "~/.claude/commands/myskill.md"}})

    def test_hooks_passes(self):
        # ~/.claude/hooks/ 는 우리 훅 영역 — 허용
        self._assert_pass({"tool_name": "Edit", "tool_input": {"file_path": "~/.claude/hooks/custom.py"}})


class ToolFilterTests(unittest.TestCase):
    """Write/Edit 외 tool은 file_path와 무관하게 통과."""

    def test_bash_passes_even_on_plugin_path(self):
        # Bash는 차단 대상 아님 — tool 필터가 먼저
        out, err, rc = _run({
            "tool_name": "Bash",
            "tool_input": {"file_path": "~/.claude/plugins/cache/anything"},
        })
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_read_passes(self):
        out, err, rc = _run({
            "tool_name": "Read",
            "tool_input": {"file_path": "~/.claude/plugins/cache/anything"},
        })
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")


class EnvBypassTests(unittest.TestCase):
    """CLAUDE_ALLOW_PLUGIN_EDIT=1 — 플러그인 개발 세션 우회."""

    def test_env_bypasses_block(self):
        out, err, rc = _run(
            {"tool_name": "Write", "tool_input": {"file_path": "~/.claude/plugins/cache/foo"}},
            env_extra={"CLAUDE_ALLOW_PLUGIN_EDIT": "1"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "", "env 우회 시 통과(무출력) 기대")

    def test_env_wrong_value_still_blocks(self):
        # "1" 외 값은 허용 아님
        out, err, rc = _run(
            {"tool_name": "Write", "tool_input": {"file_path": "~/.claude/plugins/cache/foo"}},
            env_extra={"CLAUDE_ALLOW_PLUGIN_EDIT": "true"},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(_decision(out), "deny")


class PathNormalizationTests(unittest.TestCase):
    """expanduser/resolve 기반 경로 정규화 — 우회 방어."""

    def test_symlink_into_plugins_blocked(self):
        # 심볼릭 링크가 플러그인 디렉토리를 가리키면 resolve() 후 차단
        with tempfile.TemporaryDirectory() as td:
            tmp_root = Path(td)
            # 실제 플러그인 디렉토리가 존재해야 resolve가 follow
            real = Path.home() / ".claude" / "plugins" / "cache"
            if not real.exists():
                self.skipTest("실제 plugins/cache 없음 — 심볼릭 링크 resolve 검증 skip")
            link = tmp_root / "shortcut"
            link.symlink_to(real)
            target_via_link = str(link / "some-plugin" / "file.md")

            out, err, rc = _run({
                "tool_name": "Write",
                "tool_input": {"file_path": target_via_link},
            })
            self.assertEqual(rc, 0)
            self.assertEqual(_decision(out), "deny",
                             "심볼릭 링크로 플러그인 디렉토리 우회 시도 차단")

    def test_relative_path_with_home_tilde(self):
        # ~ 확장 확인 — 전체 경로가 resolve되어 비교됨
        out, err, rc = _run({
            "tool_name": "Write",
            "tool_input": {"file_path": "~/.claude/plugins/cache/x"},
        })
        self.assertEqual(rc, 0)
        self.assertEqual(_decision(out), "deny")

    def test_non_plugin_path_with_plugins_substring(self):
        # "plugins"라는 단어가 경로에 있어도 ~/.claude/plugins 아래가 아니면 통과
        out, err, rc = _run({
            "tool_name": "Write",
            "tool_input": {"file_path": "/Users/x/my-plugins/foo.py"},
        })
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")


class MalformedInputTests(unittest.TestCase):
    """잘못된 입력은 조용히 통과 (fail-open)."""

    def test_invalid_json_passes(self):
        p = subprocess.run(
            [PYTHON, str(HOOK)],
            input="not json at all",
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "HARNESS_FORCE_ENABLE": "1"},
        )
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout.strip(), "")

    def test_empty_payload_passes(self):
        out, err, rc = _run({})
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_no_file_path_passes(self):
        out, err, rc = _run({"tool_name": "Write", "tool_input": {}})
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")


if __name__ == "__main__":
    unittest.main()
