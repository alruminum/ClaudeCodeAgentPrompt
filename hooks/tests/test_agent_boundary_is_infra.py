"""
test_agent_boundary_is_infra.py — issue #84 PR-1+2

is_infra_project() 4신호 OR 판정 + agent_boundary_debug.log의 is_infra 필드 검증.

각 신호를 개별로 켜서 True 확인, 모두 끄면 False 확인.
서브프로세스 + tempfile.TemporaryDirectory()로 부모 환경 오염 방지.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOKS_DIR = Path(__file__).resolve().parent.parent
HOOK = HOOKS_DIR / "agent-boundary.py"
PYTHON = sys.executable

_MINIMAL_PAYLOAD = {
    "tool_name": "Read",
    "tool_input": {"file_path": "/tmp/harmless-probe.txt"},
}


def _make_project(root: Path) -> None:
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "harness.config.json").write_text(json.dumps({
        "prefix": "test",
        "default_branch": "main",
    }))


def _run_hook(env_extra: dict | None, cwd: Path) -> tuple[int, str, str]:
    env = {**os.environ}
    env["HARNESS_FORCE_ENABLE"] = "1"
    for k in ("HARNESS_INFRA", "CLAUDE_PLUGIN_ROOT", "HARNESS_AGENT_NAME", "HARNESS_SESSION_ID"):
        env.pop(k, None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [PYTHON, str(HOOK)],
        input=json.dumps(_MINIMAL_PAYLOAD),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
        timeout=10,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _last_dbg_entry(state_dir: Path) -> dict | None:
    log_path = state_dir / "agent_boundary_debug.log"
    if not log_path.exists():
        return None
    lines = log_path.read_text().strip().splitlines()
    if not lines:
        return None
    # 마지막 entry 중 'tool'/'fp'가 있는 매 hook-call entry만 (deny entry는 'event' 키)
    for raw in reversed(lines):
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if "tool" in obj and "fp" in obj:
            return obj
    return None


class IsInfraSignalTests(unittest.TestCase):
    """4신호 각각 단독으로 True를 만들 수 있는지 확인."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        _make_project(self.root)
        self.state_dir = self.root / ".claude" / "harness-state"

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_signal1_harness_infra_env_true(self) -> None:
        rc, _out, _err = _run_hook({"HARNESS_INFRA": "1"}, cwd=self.root)
        self.assertEqual(rc, 0)
        entry = _last_dbg_entry(self.state_dir)
        self.assertIsNotNone(entry, "debug log entry not found")
        self.assertIs(entry["is_infra"], True)

    def test_signal3_claude_plugin_root_env_true(self) -> None:
        rc, _out, _err = _run_hook({"CLAUDE_PLUGIN_ROOT": "/some/plugin/root"}, cwd=self.root)
        self.assertEqual(rc, 0)
        entry = _last_dbg_entry(self.state_dir)
        self.assertIsNotNone(entry)
        self.assertIs(entry["is_infra"], True)

    def test_signal4_cwd_equals_home_claude_true(self) -> None:
        infra_root = Path.home() / ".claude"
        if not infra_root.exists():
            self.skipTest("~/.claude not present in test env")
        # get_state_dir()이 cwd=~/.claude 일 때 ~/.claude/.claude/harness-state 를 사용 (walk-up 결과)
        infra_state = infra_root / ".claude" / "harness-state"
        rc, _out, _err = _run_hook(None, cwd=infra_root)
        self.assertEqual(rc, 0)
        log_path = infra_state / "agent_boundary_debug.log"
        self.assertTrue(log_path.exists(), f"debug log not written at {log_path}")
        entry = _last_dbg_entry(infra_state)
        self.assertIsNotNone(entry)
        self.assertIs(entry["is_infra"], True)


class IsInfraAllFalseTests(unittest.TestCase):
    """4신호 모두 비활성 → False 보장."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        _make_project(self.root)
        self.state_dir = self.root / ".claude" / "harness-state"

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_all_signals_off_false(self) -> None:
        # cwd는 임시 디렉토리, env에는 HARNESS_INFRA / CLAUDE_PLUGIN_ROOT 없음.
        # 단, 신호 2(마커 파일)은 실파일이라 부모 환경에 ~/.claude/.harness-infra가
        # 있으면 True가 됨. 부모 환경에 마커 파일이 없는 일반 케이스를 가정.
        marker = Path.home() / ".claude" / ".harness-infra"
        if marker.exists():
            self.skipTest("infra marker present in parent env — cannot assert all-false")
        rc, _out, _err = _run_hook(None, cwd=self.root)
        self.assertEqual(rc, 0)
        entry = _last_dbg_entry(self.state_dir)
        self.assertIsNotNone(entry)
        self.assertIs(entry["is_infra"], False)


class IsInfraDebugLogFieldTests(unittest.TestCase):
    """is_infra 필드가 매 hook 호출 debug log에 bool 타입으로 기록되는지 확인."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        _make_project(self.root)
        self.state_dir = self.root / ".claude" / "harness-state"

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_is_infra_key_present_when_signal_on(self) -> None:
        _run_hook({"HARNESS_INFRA": "1"}, cwd=self.root)
        entry = _last_dbg_entry(self.state_dir)
        self.assertIsNotNone(entry)
        self.assertIn("is_infra", entry)

    def test_is_infra_value_is_bool(self) -> None:
        _run_hook({"HARNESS_INFRA": "1"}, cwd=self.root)
        entry = _last_dbg_entry(self.state_dir)
        self.assertIsNotNone(entry)
        self.assertIsInstance(entry["is_infra"], bool)


class InfraBypassTests(unittest.TestCase):
    """인프라 모드에서의 Write 차단/허용 분기 검증 (이슈 #85).

    수용 기준:
    - 인프라 모드 ON: harness-state/ Write → deny (런타임 상태 보호)
    - 인프라 모드 ON: hooks/ Write → 허용 (HARNESS_INFRA_PATTERNS 광역 차단 우회)
    - 인프라 모드 ON: .sessions/ Write → deny (세션 상태 보호)
    - 인프라 모드 OFF: hooks/ 광역 차단은 active_agent 컨텍스트 별 정책으로 검증
    """

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        _make_project(self.root)

    def tearDown(self) -> None:
        self._td.cleanup()

    def _run_write(self, payload: dict, infra_on: bool) -> subprocess.CompletedProcess:
        env = {**os.environ, "HARNESS_FORCE_ENABLE": "1"}
        for k in ("HARNESS_AGENT_NAME", "HARNESS_SESSION_ID", "HARNESS_INFRA", "CLAUDE_PLUGIN_ROOT"):
            env.pop(k, None)
        if infra_on:
            env["HARNESS_INFRA"] = "1"
        return subprocess.run(
            [PYTHON, str(HOOK)],
            input=json.dumps(payload),
            capture_output=True, text=True,
            env=env, cwd=str(self.root), timeout=10,
        )

    def _is_denied(self, proc: subprocess.CompletedProcess) -> bool:
        if not proc.stdout.strip():
            return False
        try:
            out = json.loads(proc.stdout)
            return out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
        except json.JSONDecodeError:
            return False

    def test_infra_mode_state_write_denied(self) -> None:
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / ".claude" / "harness-state" / "live.json"),
                "content": "{}",
            },
        }
        proc = self._run_write(payload, infra_on=True)
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(
            self._is_denied(proc),
            f"harness-state/ Write는 인프라 모드에서도 차단되어야 한다. stdout={proc.stdout!r}"
        )

    def test_infra_mode_hooks_write_allowed(self) -> None:
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / "hooks" / "test.py"),
                "content": "# test",
            },
        }
        proc = self._run_write(payload, infra_on=True)
        self.assertEqual(proc.returncode, 0)
        self.assertFalse(
            self._is_denied(proc),
            f"hooks/ Write는 인프라 모드에서 허용되어야 한다. stdout={proc.stdout!r}"
        )

    def test_infra_mode_sessions_write_denied(self) -> None:
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / ".sessions" / "abc123" / "live.json"),
                "content": "{}",
            },
        }
        proc = self._run_write(payload, infra_on=True)
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(
            self._is_denied(proc),
            f".sessions/ Write는 인프라 모드에서도 차단되어야 한다. stdout={proc.stdout!r}"
        )

    def test_normal_mode_does_not_crash(self) -> None:
        payload = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.root / "hooks" / "test.py"),
                "content": "# test",
            },
        }
        proc = self._run_write(payload, infra_on=False)
        self.assertEqual(proc.returncode, 0, f"훅이 예외로 종료됨: stderr={proc.stderr!r}")


if __name__ == "__main__":
    unittest.main()
