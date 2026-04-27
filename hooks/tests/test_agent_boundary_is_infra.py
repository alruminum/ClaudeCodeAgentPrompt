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


if __name__ == "__main__":
    unittest.main()
