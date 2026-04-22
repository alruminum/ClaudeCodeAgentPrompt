"""
test_hook_integration.py — Phase 3 훅 end-to-end 통합 테스트.

agent-gate → agent-boundary → post-agent-flags 라이프사이클이 live.json 단일
소스를 경유해 에이전트 활성/해제를 올바르게 처리하는지 검증.

서브프로세스로 훅을 실행해 실제 stdin/exit 경로를 박제.
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
sys.path.insert(0, str(HOOKS_DIR))
import session_state as ss  # noqa: E402


def _run_hook(name: str, stdin_json: dict, cwd: Path, extra_env: dict | None = None):
    """훅 스크립트를 서브프로세스로 실행. (returncode, stdout, stderr)."""
    script = HOOKS_DIR / name
    env = os.environ.copy()
    # 테스트 격리: HARNESS_SESSION_ID 주입은 stdin 의존성 확인을 방해하므로 기본 미설정
    env.pop("HARNESS_SESSION_ID", None)
    env.pop("HARNESS_AGENT_NAME", None)
    # 화이트리스트 가드 우회 — 테스트는 임시 디렉토리에서 돌리므로 강제 활성
    env["HARNESS_FORCE_ENABLE"] = "1"
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        ["python3", str(script)],
        input=json.dumps(stdin_json),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
        timeout=20,
    )
    return proc.returncode, proc.stdout, proc.stderr


class AgentLifecycleTests(unittest.TestCase):
    """agent-gate(write) → boundary(read) → post-agent-flags(clear) 체인."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        (self.root / ".claude").mkdir(parents=True, exist_ok=True)
        # harness.config.json 필수 — prefix 결정
        (self.root / ".claude" / "harness.config.json").write_text(json.dumps({
            "prefix": "test",
            "default_branch": "main",
        }))
        self.sid = "sessTest01"
        ss.initialize_session(self.sid, project_root=self.root)

    def tearDown(self):
        self._td.cleanup()

    def test_agent_gate_writes_live_json(self):
        """PreToolUse(Agent) → live.json.agent 기록."""
        stdin = {
            "session_id": self.sid,
            "tool_input": {
                "subagent_type": "architect",
                "prompt": "SYSTEM_DESIGN: 시스템 설계 #42",
            },
        }
        rc, out, err = _run_hook("agent-gate.py", stdin, self.root)
        self.assertEqual(rc, 0, msg=f"stderr={err}")
        live = ss.get_live(self.sid, project_root=self.root)
        self.assertEqual(live.get("agent"), "architect")

    def test_agent_gate_rejects_internal_subagent(self):
        """Claude Code 내장 서브에이전트(Explore 등)는 live.json에 기록 금지."""
        stdin = {
            "session_id": self.sid,
            "tool_input": {
                "subagent_type": "Explore",
                "prompt": "search the codebase",
            },
        }
        rc, _, _ = _run_hook("agent-gate.py", stdin, self.root)
        self.assertEqual(rc, 0)
        live = ss.get_live(self.sid, project_root=self.root)
        self.assertNotIn("agent", live, "내장 서브에이전트는 기록하지 않아야 함")

    def test_post_agent_clears_matching_agent(self):
        """PostToolUse(Agent) → 일치하는 agent 필드만 해제."""
        ss.update_live(self.sid, project_root=self.root, agent="architect")
        stdin = {
            "session_id": self.sid,
            "tool_input": {"subagent_type": "architect", "prompt": "SYSTEM_DESIGN: #1"},
            "tool_response": "---MARKER:READY_FOR_IMPL---",
        }
        rc, _, _ = _run_hook("post-agent-flags.py", stdin, self.root)
        self.assertEqual(rc, 0)
        live = ss.get_live(self.sid, project_root=self.root)
        self.assertNotIn("agent", live)

    def test_post_agent_race_protection(self):
        """post-agent가 도착했을 때 다른 agent가 이미 활성이면 그 값 보존."""
        ss.update_live(self.sid, project_root=self.root, agent="validator")  # 현재 활성은 validator
        stdin = {
            "session_id": self.sid,
            # 완료된 건 architect — 뒤늦게 도착한 post-agent
            "tool_input": {"subagent_type": "architect", "prompt": "SYSTEM_DESIGN"},
            "tool_response": "",
        }
        rc, _, _ = _run_hook("post-agent-flags.py", stdin, self.root)
        self.assertEqual(rc, 0)
        live = ss.get_live(self.sid, project_root=self.root)
        self.assertEqual(live.get("agent"), "validator",
                         "다른 agent가 이미 활성일 때 덮어쓰면 안 됨 (race)")


class AgentBoundaryTests(unittest.TestCase):
    """agent-boundary.py가 live.json을 읽어 경로 접근을 판정."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        (self.root / ".claude").mkdir(parents=True, exist_ok=True)
        (self.root / ".claude" / "harness.config.json").write_text(json.dumps({
            "prefix": "test",
            "default_branch": "main",
        }))
        self.sid = "sessB02"
        ss.initialize_session(self.sid, project_root=self.root)

    def tearDown(self):
        self._td.cleanup()

    def _boundary(self, stdin, extra_env=None):
        return _run_hook("agent-boundary.py", stdin, self.root, extra_env)

    def test_architect_can_write_trd(self):
        ss.update_live(self.sid, project_root=self.root, agent="architect")
        stdin = {
            "session_id": self.sid,
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "trd.md")},
        }
        rc, out, _ = self._boundary(stdin)
        self.assertEqual(rc, 0)
        # deny 메시지 없음
        self.assertNotIn("deny", out.lower())

    def test_product_planner_cannot_write_trd(self):
        ss.update_live(self.sid, project_root=self.root, agent="product-planner")
        stdin = {
            "session_id": self.sid,
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "trd.md")},
        }
        rc, out, _ = self._boundary(stdin)
        # deny 메시지 확인 — exit 0이어도 stdout에 JSON deny 포함
        self.assertIn("deny", out.lower())

    def test_main_claude_cannot_write_src(self):
        """live.json.agent 없음 = 메인 Claude. src/** 수정 금지."""
        stdin = {
            "session_id": self.sid,
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "src" / "foo.ts")},
        }
        rc, out, _ = self._boundary(stdin)
        self.assertIn("file-ownership", out)

    def test_cross_session_agent_does_not_leak(self):
        """다른 세션에서 agent가 활성이어도 이 세션 판정에 영향 없음."""
        # 세션 A에 engineer 활성
        ss.initialize_session("sessOther", project_root=self.root)
        ss.update_live("sessOther", project_root=self.root, agent="engineer")
        # 세션 B(self.sid)는 활성 agent 없음 → src/ 수정 차단되어야
        stdin = {
            "session_id": self.sid,
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "src" / "foo.ts")},
        }
        rc, out, _ = self._boundary(stdin)
        self.assertIn("file-ownership", out,
                      "다른 세션의 agent 플래그가 이 세션으로 새면 안 됨")

    def test_agent_tool_path_no_env_propagation(self):
        """Agent 툴 경로 재현 — env var 없이 live.json만으로 판정."""
        ss.update_live(self.sid, project_root=self.root, agent="architect")
        stdin = {
            "session_id": self.sid,  # stdin으로만 sid 전달
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.root / "docs" / "architecture.md")},
        }
        # extra_env 명시적으로 비움 — env var 없어도 통과해야 함
        rc, out, _ = self._boundary(stdin, extra_env={})
        self.assertNotIn("deny", out.lower(),
                         "Agent 툴 경로(env 미전파)에서도 live.json 기반 판정이 작동해야 함")


class AgentGatePromptTests(unittest.TestCase):
    """agent-gate.py 프롬프트 검증 (Mode/이슈 번호 정책)."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        (self.root / ".claude").mkdir(parents=True, exist_ok=True)
        (self.root / ".claude" / "harness.config.json").write_text(json.dumps({
            "prefix": "test", "default_branch": "main",
        }))
        self.sid = "sessPrompt04"
        ss.initialize_session(self.sid, project_root=self.root)

    def tearDown(self):
        self._td.cleanup()

    def _decision(self, out: str) -> str:
        for line in out.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
                hook_out = data.get("hookSpecificOutput", {})
                return hook_out.get("permissionDecision", "")
            except json.JSONDecodeError:
                continue
        return ""

    def test_architect_without_mode_passes_with_warning(self):
        """모드 키워드 미지정 → 경고만 stderr, 통과."""
        stdin = {"session_id": self.sid,
                 "tool_input": {"subagent_type": "architect",
                                "prompt": "이 이슈 좀 봐줘 #42"}}
        rc, out, err = _run_hook("agent-gate.py", stdin, self.root)
        self.assertEqual(rc, 0)
        self.assertNotEqual(self._decision(out), "deny")
        self.assertIn("키워드", err)  # 경고 메시지 존재

    def test_architect_light_plan_without_issue_passes(self):
        """LIGHT_PLAN 은 이슈 번호 없어도 통과."""
        stdin = {"session_id": self.sid,
                 "tool_input": {"subagent_type": "architect",
                                "prompt": "LIGHT_PLAN: 버튼 색 바꾸기"}}
        rc, out, _ = _run_hook("agent-gate.py", stdin, self.root)
        self.assertEqual(rc, 0)
        self.assertNotEqual(self._decision(out), "deny")

    def test_architect_tech_epic_without_issue_passes(self):
        """TECH_EPIC 은 이슈 번호 없어도 통과."""
        stdin = {"session_id": self.sid,
                 "tool_input": {"subagent_type": "architect",
                                "prompt": "TECH_EPIC: 기술 부채 정리"}}
        rc, out, _ = _run_hook("agent-gate.py", stdin, self.root)
        self.assertEqual(rc, 0)
        self.assertNotEqual(self._decision(out), "deny")

    def test_architect_module_plan_without_issue_blocked(self):
        """MODULE_PLAN 은 이슈 번호 필요 — 기존 동작 유지."""
        stdin = {"session_id": self.sid,
                 "tool_input": {"subagent_type": "architect",
                                "prompt": "MODULE_PLAN: impl 계획 작성"}}
        rc, out, _ = _run_hook("agent-gate.py", stdin, self.root)
        self.assertEqual(self._decision(out), "deny")

    def test_engineer_without_issue_still_blocked(self):
        """engineer는 예외 없이 이슈 번호 필수 — 루프 불변식."""
        stdin = {"session_id": self.sid,
                 "tool_input": {"subagent_type": "engineer",
                                "prompt": "구현해줘 LIGHT_PLAN"}}
        rc, out, _ = _run_hook("agent-gate.py", stdin, self.root)
        self.assertEqual(self._decision(out), "deny")


class IssueGateTests(unittest.TestCase):
    """issue-gate.py가 live.json을 읽어 ISSUE_CREATORS 판정."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        (self.root / ".claude").mkdir(parents=True, exist_ok=True)
        (self.root / ".claude" / "harness.config.json").write_text(json.dumps({
            "prefix": "test", "default_branch": "main",
        }))
        self.sid = "sessC03"
        ss.initialize_session(self.sid, project_root=self.root)

    def tearDown(self):
        self._td.cleanup()

    def _decision(self, out: str) -> str:
        """stdout의 JSON deny payload에서 permissionDecision 추출."""
        for line in out.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
                hook_out = data.get("hookSpecificOutput", {})
                return hook_out.get("permissionDecision", "")
            except json.JSONDecodeError:
                continue
        return ""

    def test_main_claude_blocked(self):
        stdin = {"session_id": self.sid, "tool_name": "mcp__github__create_issue",
                 "tool_input": {"title": "x", "body": "y"}}
        rc, out, _ = _run_hook("issue-gate.py", stdin, self.root)
        self.assertEqual(self._decision(out), "deny")

    def test_qa_agent_allowed(self):
        ss.update_live(self.sid, project_root=self.root, agent="qa")
        stdin = {"session_id": self.sid, "tool_name": "mcp__github__create_issue",
                 "tool_input": {"title": "x"}}
        rc, out, _ = _run_hook("issue-gate.py", stdin, self.root)
        self.assertNotEqual(self._decision(out), "deny")


if __name__ == "__main__":
    unittest.main()
