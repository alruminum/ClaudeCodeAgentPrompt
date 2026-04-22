"""test_skill_hooks.py — Phase 4 스킬 훅 통합 테스트.

skill-gate / post-skill-flags / skill-stop-protect 3개 훅을 subprocess로
호출해 stdin/stdout 계약을 검증한다.

Run: python3 -m unittest discover -s ~/.claude/hooks/tests -p 'test_skill_hooks.py' -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HOOKS_DIR))

import session_state as ss  # noqa: E402

PYTHON = sys.executable


def _run_hook(hook_name: str, payload: dict, env_extra: dict | None = None) -> tuple[str, str, int]:
    """훅을 subprocess로 호출. (stdout, stderr, returncode) 반환."""
    env = os.environ.copy()
    env["HARNESS_FORCE_ENABLE"] = "1"  # 테스트: 화이트리스트 가드 우회
    if env_extra:
        env.update(env_extra)
    p = subprocess.run(
        [PYTHON, str(HOOKS_DIR / hook_name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    return p.stdout, p.stderr, p.returncode


class SkillGateTests(unittest.TestCase):
    """PreToolUse(Skill) — skill-gate.py."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        (self.root / ".claude").mkdir()
        # 훅이 cwd 기반으로 프로젝트 루트를 찾으므로 임시 디렉토리에서 호출
        self._cwd = os.getcwd()
        os.chdir(self.root)
        # state_root 사전 생성
        ss.ensure_skeleton(self.root)
        ss.write_session_pointer("sessTest", self.root)

    def tearDown(self):
        os.chdir(self._cwd)
        self._td.cleanup()

    def test_records_active_skill(self):
        out, err, rc = _run_hook("skill-gate.py", {
            "tool_name": "Skill",
            "session_id": "sessTest",
            "tool_input": {"skill": "ux"},
        })
        self.assertEqual(rc, 0, err)
        sk = ss.get_active_skill("sessTest", project_root=self.root)
        self.assertIsNotNone(sk)
        self.assertEqual(sk["name"], "ux")
        self.assertEqual(sk["level"], "medium")

    def test_non_skill_tool_ignored(self):
        out, err, rc = _run_hook("skill-gate.py", {
            "tool_name": "Bash",
            "session_id": "sessTest",
            "tool_input": {"command": "echo x"},
        })
        self.assertEqual(rc, 0)
        self.assertIsNone(ss.get_active_skill("sessTest", project_root=self.root))

    def test_no_session_id_safe_no_op(self):
        # setUp가 pointer를 만들어두면 폴백이 발동하므로, 이 테스트만 임시 디렉토리를
        # 새로 잡아서 pointer/state_dir이 비어있는 상태를 만든다.
        with tempfile.TemporaryDirectory() as td:
            local_root = Path(td)
            (local_root / ".claude").mkdir()
            here = os.getcwd()
            os.chdir(local_root)
            try:
                out, err, rc = _run_hook("skill-gate.py", {
                    "tool_name": "Skill",
                    "tool_input": {"skill": "ux"},
                }, env_extra={"HARNESS_SESSION_ID": ""})
                # session_id 없어도 crash 안 남, live.json도 안 만들어짐
                self.assertEqual(rc, 0, err)
            finally:
                os.chdir(here)


class PostSkillFlagsTests(unittest.TestCase):
    """PostToolUse(Skill) — post-skill-flags.py."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        (self.root / ".claude").mkdir()
        self._cwd = os.getcwd()
        os.chdir(self.root)
        ss.ensure_skeleton(self.root)
        ss.write_session_pointer("sessTest", self.root)

    def tearDown(self):
        os.chdir(self._cwd)
        self._td.cleanup()

    def test_clears_medium_skill(self):
        ss.set_active_skill("sessTest", "ux", "medium", project_root=self.root)
        out, err, rc = _run_hook("post-skill-flags.py", {
            "tool_name": "Skill",
            "session_id": "sessTest",
            "tool_input": {"skill": "ux"},
        })
        self.assertEqual(rc, 0, err)
        self.assertIsNone(ss.get_active_skill("sessTest", project_root=self.root))

    def test_does_not_clear_heavy_skill(self):
        ss.set_active_skill("sessTest", "ralph", "heavy", project_root=self.root)
        out, err, rc = _run_hook("post-skill-flags.py", {
            "tool_name": "Skill",
            "session_id": "sessTest",
            "tool_input": {"skill": "ralph"},
        })
        self.assertEqual(rc, 0, err)
        sk = ss.get_active_skill("sessTest", project_root=self.root)
        self.assertIsNotNone(sk, "heavy는 PostToolUse가 청소하지 않는다")

    def test_name_mismatch_does_not_clear(self):
        ss.set_active_skill("sessTest", "ux", "medium", project_root=self.root)
        # 다른 스킬의 PostToolUse가 도착했을 때 — race 가드 발동
        out, err, rc = _run_hook("post-skill-flags.py", {
            "tool_name": "Skill",
            "session_id": "sessTest",
            "tool_input": {"skill": "qa"},
        })
        self.assertEqual(rc, 0, err)
        sk = ss.get_active_skill("sessTest", project_root=self.root)
        self.assertIsNotNone(sk, "다른 스킬 PostToolUse는 현재 활성 스킬 청소 금지")
        self.assertEqual(sk["name"], "ux")


class SkillStopProtectTests(unittest.TestCase):
    """Stop — skill-stop-protect.py."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        (self.root / ".claude").mkdir()
        self._cwd = os.getcwd()
        os.chdir(self.root)
        ss.ensure_skeleton(self.root)
        ss.write_session_pointer("sessTest", self.root)

    def tearDown(self):
        os.chdir(self._cwd)
        self._td.cleanup()

    def test_no_active_skill_passes(self):
        out, err, rc = _run_hook("skill-stop-protect.py", {
            "session_id": "sessTest",
        })
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "", "활성 스킬 없으면 무출력 통과")

    def test_light_skill_passes(self):
        # light는 PostToolUse가 이미 청소했을 것 — 실수로 도달해도 통과
        ss.set_active_skill("sessTest", "update-config", "light", project_root=self.root)
        out, err, rc = _run_hook("skill-stop-protect.py", {
            "session_id": "sessTest",
        })
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    def test_medium_skill_blocks_stop(self):
        ss.set_active_skill("sessTest", "ux", "medium", project_root=self.root)
        out, err, rc = _run_hook("skill-stop-protect.py", {
            "session_id": "sessTest",
        })
        self.assertEqual(rc, 0, err)
        data = json.loads(out)
        self.assertEqual(data["decision"], "block")
        self.assertIn("ux", data["reason"])
        # reinforcements +1
        sk = ss.get_active_skill("sessTest", project_root=self.root)
        self.assertEqual(sk["reinforcements"], 1)

    def test_heavy_skill_blocks_stop(self):
        ss.set_active_skill("sessTest", "ralph", "heavy", project_root=self.root)
        out, err, rc = _run_hook("skill-stop-protect.py", {
            "session_id": "sessTest",
        })
        self.assertEqual(rc, 0, err)
        data = json.loads(out)
        self.assertEqual(data["decision"], "block")

    def test_heavy_max_reinforcements_releases(self):
        ss.set_active_skill("sessTest", "ralph", "heavy", project_root=self.root)
        # heavy max=10 — 그 만큼 채움
        from skill_protection import get_policy
        max_r = get_policy("heavy")["max_reinforcements"]
        live = ss.get_live("sessTest", project_root=self.root)
        live["skill"]["reinforcements"] = max_r
        ss.update_live("sessTest", project_root=self.root, skill=live["skill"])
        out, err, rc = _run_hook("skill-stop-protect.py", {
            "session_id": "sessTest",
        })
        self.assertEqual(rc, 0, err)
        self.assertEqual(out.strip(), "", "max 도달 시 무출력 통과(=Stop 허용)")
        self.assertIsNone(ss.get_active_skill("sessTest", project_root=self.root))

    def test_heavy_ttl_releases(self):
        # 30분 TTL — started_at을 1시간 전으로 강제 세팅
        ss.set_active_skill(
            "sessTest", "ralph", "heavy",
            project_root=self.root,
            started_at=int(time.time()) - 3600,
        )
        out, err, rc = _run_hook("skill-stop-protect.py", {
            "session_id": "sessTest",
        })
        self.assertEqual(rc, 0, err)
        self.assertEqual(out.strip(), "")
        self.assertIsNone(ss.get_active_skill("sessTest", project_root=self.root))

    def test_ralph_loop_self_managed_not_blocked(self):
        # ralph-loop:ralph-loop는 자체 stop-hook이 prompt 재주입 — Stop 차단 금지.
        ss.set_active_skill("sessTest", "ralph-loop:ralph-loop", "heavy", project_root=self.root)
        out, err, rc = _run_hook("skill-stop-protect.py", {
            "session_id": "sessTest",
        })
        self.assertEqual(rc, 0, err)
        self.assertEqual(out.strip(), "", "ralph-loop는 lifecycle 자체 관리 — Stop 차단 금지")

    def test_global_kill_releases(self):
        ss.set_active_skill("sessTest", "ralph", "heavy", project_root=self.root)
        ss.set_global_signal(self.root, harness_kill=True)
        out, err, rc = _run_hook("skill-stop-protect.py", {
            "session_id": "sessTest",
        })
        self.assertEqual(rc, 0, err)
        self.assertEqual(out.strip(), "")
        self.assertIsNone(ss.get_active_skill("sessTest", project_root=self.root))


if __name__ == "__main__":
    unittest.main()
