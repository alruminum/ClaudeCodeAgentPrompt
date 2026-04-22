"""
test_session_agent_cleanup.py — UserPromptSubmit 훅 단위 테스트.

시나리오: agent-gate.py가 live.json.agent="qa"를 기록한 뒤 유저가 Agent tool use를
reject하면 post-agent-flags.py가 돌지 않아 agent 필드가 고아로 남는다.
session-agent-cleanup.py가 새 UserPromptSubmit 타이밍에 이 필드를 청소하는지 확인.

Run: python3 -m unittest discover -s ~/.claude/hooks/tests -p 'test_session_agent_cleanup.py' -v
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
sys.path.insert(0, str(HOOKS_DIR))

import session_state as ss  # noqa: E402


HOOK_SCRIPT = HOOKS_DIR / "session-agent-cleanup.py"


def _run_hook(stdin_json: dict, project_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=json.dumps(stdin_json),
        capture_output=True,
        text=True,
        cwd=str(project_root),
        env={**os.environ, "HARNESS_FORCE_ENABLE": "1"},
    )


class SessionAgentCleanupTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        (self.root / ".claude").mkdir()
        ss.ensure_skeleton(self.root)
        self.sid = "test-sid-abc123"

    def tearDown(self):
        self._td.cleanup()

    def _seed_live_with_agent(self, agent_name: str = "qa"):
        ss.update_live(self.sid, self.root, agent=agent_name)
        live = ss.get_live(self.sid, self.root)
        self.assertEqual(live.get("agent"), agent_name)

    def test_clears_stale_qa_agent(self):
        """agent-gate가 live.json.agent=qa 기록 → Agent reject → cleanup이 해제."""
        self._seed_live_with_agent("qa")
        result = _run_hook({"session_id": self.sid}, self.root)
        self.assertEqual(result.returncode, 0)
        live = ss.get_live(self.sid, self.root)
        self.assertIsNone(live.get("agent") or None)

    def test_clears_any_agent_name(self):
        """qa 뿐 아니라 어떤 에이전트 이름이 고아로 남아도 해제."""
        for name in ("engineer", "architect", "designer", "validator"):
            with self.subTest(agent=name):
                self._seed_live_with_agent(name)
                result = _run_hook({"session_id": self.sid}, self.root)
                self.assertEqual(result.returncode, 0)
                live = ss.get_live(self.sid, self.root)
                self.assertFalse(
                    live.get("agent"),
                    f"{name} agent still present after cleanup",
                )

    def test_no_op_when_live_has_no_agent(self):
        """live.json에 agent 필드가 없으면 아무 것도 하지 않는다."""
        ss.update_live(self.sid, self.root, issue_num="#123")
        result = _run_hook({"session_id": self.sid}, self.root)
        self.assertEqual(result.returncode, 0)
        live = ss.get_live(self.sid, self.root)
        self.assertEqual(live.get("issue_num"), "#123")

    def test_no_op_when_no_session_id(self):
        """stdin에 session_id가 없으면 조용히 종료."""
        result = _run_hook({}, self.root)
        self.assertEqual(result.returncode, 0)

    def test_invalid_json_stdin_does_not_crash(self):
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input="not-json",
            capture_output=True,
            text=True,
            cwd=str(self.root),
        )
        self.assertEqual(result.returncode, 0)

    def test_cleanup_unblocks_agent_boundary_read(self):
        """회귀 재현: stale agent=qa 상태에서 agent-boundary가 infra 파일 Read를 차단하는지,
        cleanup 이후 None으로 판정되는지.
        """
        self._seed_live_with_agent("qa")

        # cleanup 전: active_agent == "qa"
        stdin_data = {"session_id": self.sid}
        with mock.patch.object(ss, "state_root", return_value=self.root / ".claude" / "harness-state"):
            with mock.patch.object(ss, "_find_project_root", return_value=self.root):
                self.assertEqual(ss.active_agent(stdin_data=stdin_data), "qa")

        # cleanup 실행
        result = _run_hook(stdin_data, self.root)
        self.assertEqual(result.returncode, 0)

        # cleanup 후: active_agent == None
        with mock.patch.object(ss, "state_root", return_value=self.root / ".claude" / "harness-state"):
            with mock.patch.object(ss, "_find_project_root", return_value=self.root):
                self.assertIsNone(ss.active_agent(stdin_data=stdin_data))


if __name__ == "__main__":
    unittest.main()
