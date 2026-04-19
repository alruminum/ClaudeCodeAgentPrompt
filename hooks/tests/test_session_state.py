"""
test_session_state.py — Phase 3 session-isolation 모듈 단위 테스트.

OMC 패턴 및 PR #24/#26/#29 재현 시나리오 박제.

Run: python3 -m unittest discover -s ~/.claude/hooks/tests -p 'test_session_state.py' -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import session_state as ss  # noqa: E402


def _touch_claude(root: Path) -> Path:
    """tmp dir을 프로젝트 루트처럼 만든다."""
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    return root


class SessionIdValidationTests(unittest.TestCase):
    def test_valid_formats(self):
        for ok in ("a", "abc", "ABC-123", "sess_01-XYZ", "0" + "a" * 255):
            self.assertTrue(ss.valid_session_id(ok), ok)

    def test_invalid_formats(self):
        for bad in ("", "-abc", "_abc", "../evil", "a/b", "a.b", None, 0, "  ", "abc" * 200):
            self.assertFalse(ss.valid_session_id(bad), repr(bad))

    def test_stdin_parser_three_variants(self):
        # OMC 3변형 fallback 확인
        self.assertEqual(ss.session_id_from_stdin({"session_id": "abc123"}), "abc123")
        self.assertEqual(ss.session_id_from_stdin({"sessionId": "abc123"}), "abc123")
        self.assertEqual(ss.session_id_from_stdin({"sessionid": "abc123"}), "abc123")
        self.assertEqual(ss.session_id_from_stdin({}), "")
        self.assertEqual(ss.session_id_from_stdin({"session_id": "../evil"}), "")


class AtomicWriteTests(unittest.TestCase):
    def test_atomic_write_adds_meta_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.json"
            ss.atomic_write_json(p, {"k": "v"}, mode="session", session_id="sidA")
            data = json.loads(p.read_text())
            self.assertEqual(data["k"], "v")
            self.assertIn("_meta", data)
            self.assertEqual(data["_meta"]["mode"], "session")
            self.assertEqual(data["_meta"]["sessionId"], "sidA")
            self.assertIsInstance(data["_meta"]["written_at"], int)

    def test_atomic_write_mode_is_restrictive(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "secret.json"
            ss.atomic_write_json(p, {"x": 1})
            st = p.stat()
            self.assertEqual(st.st_mode & 0o777, 0o600)

    def test_atomic_write_no_tmp_leftover(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.json"
            ss.atomic_write_json(p, {"x": 1})
            # tmp 잔재 없어야 함
            leftovers = [f for f in Path(td).iterdir() if ".tmp" in f.name]
            self.assertEqual(leftovers, [])


class LiveJsonTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = _touch_claude(Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    def test_update_and_read_same_session(self):
        ss.update_live("sessA", project_root=self.root, agent="engineer", issue_num="42")
        live = ss.get_live("sessA", project_root=self.root)
        self.assertEqual(live["agent"], "engineer")
        self.assertEqual(live["issue_num"], "42")
        self.assertEqual(live["session_id"], "sessA")
        self.assertNotIn("_meta", live)  # read 시 strip

    def test_strict_ownership_reject_cross_session(self):
        """다른 세션이 같은 경로 덮어썼으면 읽을 때 무시."""
        ss.update_live("sessA", project_root=self.root, agent="engineer")
        # 같은 파일에 sessB의 meta로 덮어씀 (시나리오: path 공격)
        p = ss.live_path("sessA", project_root=self.root)
        raw = json.loads(p.read_text())
        raw["_meta"]["sessionId"] = "sessB"
        p.write_text(json.dumps(raw))
        self.assertEqual(ss.get_live("sessA", project_root=self.root), {})

    def test_update_none_clears_field(self):
        ss.update_live("sessA", project_root=self.root, agent="engineer")
        ss.update_live("sessA", project_root=self.root, agent=None)
        self.assertNotIn("agent", ss.get_live("sessA", project_root=self.root))

    def test_clear_live_field_guarded(self):
        ss.update_live("sessA", project_root=self.root, agent="engineer")
        # 값이 다르면 삭제 안됨
        self.assertFalse(ss.clear_live_field("sessA", "agent",
                                             expect_value="validator",
                                             project_root=self.root))
        self.assertEqual(ss.get_live("sessA", project_root=self.root)["agent"], "engineer")
        # 값이 같으면 삭제
        self.assertTrue(ss.clear_live_field("sessA", "agent",
                                            expect_value="engineer",
                                            project_root=self.root))
        self.assertNotIn("agent", ss.get_live("sessA", project_root=self.root))

    def test_invalid_session_id_noop(self):
        ss.update_live("../evil", project_root=self.root, agent="x")
        self.assertEqual(ss.get_live("../evil", project_root=self.root), {})


class IsolationTests(unittest.TestCase):
    """2세션 격리 — PR #24/#26/#29의 뿌리 문제 박제."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = _touch_claude(Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    def test_two_sessions_independent(self):
        ss.update_live("sA", project_root=self.root, agent="engineer", issue_num="10")
        ss.update_live("sB", project_root=self.root, agent="architect", issue_num="20")
        self.assertEqual(ss.get_live("sA", project_root=self.root)["agent"], "engineer")
        self.assertEqual(ss.get_live("sB", project_root=self.root)["agent"], "architect")
        self.assertEqual(ss.get_live("sA", project_root=self.root)["issue_num"], "10")
        self.assertEqual(ss.get_live("sB", project_root=self.root)["issue_num"], "20")

    def test_active_agent_reads_correct_session(self):
        ss.update_live("sA", project_root=self.root, agent="engineer")
        ss.update_live("sB", project_root=self.root, agent="architect")
        # sA 컨텍스트로 조회
        self.assertEqual(
            ss.active_agent({"session_id": "sA"}, project_root=self.root), "engineer"
        )
        # sB 컨텍스트로 조회
        self.assertEqual(
            ss.active_agent({"session_id": "sB"}, project_root=self.root), "architect"
        )
        # 세션 없는 컨텍스트 — None (메인 Claude 직접 호출 시나리오)
        # 이 때는 pointer 폴백이 없도록 HARNESS_SESSION_ID와 .session-id 모두 없어야
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HARNESS_SESSION_ID", None)
            self.assertIsNone(ss.active_agent({}, project_root=self.root))


class IssueLockTests(unittest.TestCase):
    """이슈 lock — 두 세션이 같은 이슈 동시 작업 방지."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = _touch_claude(Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    def test_first_claim_succeeds(self):
        ok, holder = ss.claim_issue_lock("mb", "42", "sA", project_root=self.root)
        self.assertTrue(ok)
        self.assertIsNone(holder)

    def test_same_session_reentry(self):
        ss.claim_issue_lock("mb", "42", "sA", project_root=self.root)
        ok, holder = ss.claim_issue_lock("mb", "42", "sA", project_root=self.root)
        self.assertTrue(ok, "같은 세션 재진입은 허용")
        self.assertIsNone(holder)

    def test_different_session_rejected_when_alive(self):
        ss.claim_issue_lock("mb", "42", "sA", project_root=self.root)
        # sA의 holder PID=자기 자신이므로 alive. heartbeat 방금 기록.
        ok, holder = ss.claim_issue_lock("mb", "42", "sB", project_root=self.root)
        self.assertFalse(ok)
        self.assertEqual(holder["session_id"], "sA")

    def test_stale_lock_taken_over(self):
        # 존재하지 않는 PID를 holder로 강제 세팅
        p = ss.issue_lock_path("mb", "42", project_root=self.root)
        ss.atomic_write_json(p, {
            "session_id": "sA",
            "pid": 999999,  # 존재하지 않는 PID
            "heartbeat": 0,  # 오래됨
            "started": 0,
        }, mode="issue-lock")
        ok, _ = ss.claim_issue_lock("mb", "42", "sB", project_root=self.root)
        self.assertTrue(ok, "stale lock은 인계되어야 함")
        live = ss.read_json(p)
        self.assertEqual(live["session_id"], "sB")

    def test_release_guarded(self):
        ss.claim_issue_lock("mb", "42", "sA", project_root=self.root)
        # 다른 세션이 해제 시도 — 거부
        self.assertFalse(ss.release_issue_lock("mb", "42", "sB", project_root=self.root))
        # 원소유자 해제 — 성공
        self.assertTrue(ss.release_issue_lock("mb", "42", "sA", project_root=self.root))
        # 없는 lock 해제 — idempotent
        self.assertTrue(ss.release_issue_lock("mb", "42", "sC", project_root=self.root))

    def test_heartbeat_only_by_owner(self):
        ss.claim_issue_lock("mb", "42", "sA", project_root=self.root)
        self.assertTrue(ss.heartbeat_issue_lock("mb", "42", "sA", project_root=self.root))
        self.assertFalse(ss.heartbeat_issue_lock("mb", "42", "sB", project_root=self.root))

    def test_heartbeat_refresh_prevents_stale_takeover(self):
        """장시간 실행 시나리오 — heartbeat 갱신이 stale 판정을 막아야 한다.
        회귀: executor.heartbeat_loop가 heartbeat_issue_lock을 호출하지 않으면
        30분 넘는 deep impl 루프가 다른 세션에게 lock을 탈취당하는 버그.
        """
        import time as _time
        ss.claim_issue_lock("mb", "42", "sA", project_root=self.root)
        p = ss.issue_lock_path("mb", "42", project_root=self.root)

        # heartbeat을 오래된 시각으로 수동 조작 (30분 이전)
        data = ss.read_json(p)
        data["heartbeat"] = int(_time.time()) - (ss.DEFAULT_LOCK_STALE_SEC + 60)
        ss.atomic_write_json(p, data, mode="issue-lock", session_id="sA")

        # 이 시점 sB가 claim 시도 → stale 판정으로 탈취됨 (버그 재현)
        ok_before, _ = ss.claim_issue_lock("mb", "42", "sB", project_root=self.root)
        self.assertTrue(ok_before, "heartbeat 갱신 없으면 stale 탈취 발생")

        # sA로 다시 세팅, 이번엔 heartbeat_issue_lock 호출로 갱신
        ss.release_issue_lock("mb", "42", "sB", project_root=self.root)
        ss.claim_issue_lock("mb", "42", "sA", project_root=self.root)
        data = ss.read_json(p)
        data["heartbeat"] = int(_time.time()) - (ss.DEFAULT_LOCK_STALE_SEC + 60)
        ss.atomic_write_json(p, data, mode="issue-lock", session_id="sA")
        # executor의 heartbeat_loop가 호출해야 할 것 — heartbeat_issue_lock
        self.assertTrue(ss.heartbeat_issue_lock("mb", "42", "sA", project_root=self.root))
        # 이후 sC의 claim은 거부되어야 함
        ok_after, holder = ss.claim_issue_lock("mb", "42", "sC", project_root=self.root)
        self.assertFalse(ok_after, "heartbeat 갱신 후에는 탈취 불가")
        self.assertEqual(holder["session_id"], "sA")


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = _touch_claude(Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    def test_cleanup_preserves_current_session(self):
        ss.update_live("sA", project_root=self.root, agent="e")
        ss.update_live("sB", project_root=self.root, agent="a")
        # sB를 오래된 상태로 조작
        old_live = ss.live_path("sB", project_root=self.root)
        old_time = 0  # 1970
        os.utime(old_live, (old_time, old_time))
        removed = ss.cleanup_stale_sessions(self.root, keep="sA")
        self.assertEqual(removed, 1)
        self.assertEqual(ss.get_live("sA", project_root=self.root)["agent"], "e")
        self.assertEqual(ss.get_live("sB", project_root=self.root), {})

    def test_migrate_legacy_flags_removes_old_dir(self):
        root = ss.state_root(self.root)
        # 레거시 구조 생성
        (root / ".flags" / "claude_1").mkdir(parents=True, exist_ok=True)
        (root / ".flags" / "claude_1" / "mb_plan_validation_passed").touch()
        (root / ".claude_Explore_active").touch()  # top-level 잔재 (실제 관찰된 케이스)
        result = ss.migrate_legacy_flags(self.root)
        self.assertGreaterEqual(result["removed"], 1)
        self.assertFalse((root / ".flags").exists())
        self.assertFalse((root / ".claude_Explore_active").exists())

    def test_migrate_skips_when_harness_active(self):
        root = ss.state_root(self.root)
        (root / ".flags" / "x").mkdir(parents=True)
        # 살아있는 PID (자기 자신) harness_active
        (root / "mb_10_harness_active").write_text(json.dumps({"pid": os.getpid()}))
        result = ss.migrate_legacy_flags(self.root)
        self.assertEqual(result["skipped"], 1)
        self.assertTrue((root / ".flags").exists(), "활성 하네스 있으면 삭제 금지")


class SkeletonAndPointerTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = _touch_claude(Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    def test_initialize_session_creates_skeleton(self):
        sd = ss.initialize_session("sessA", project_root=self.root)
        self.assertIsNotNone(sd)
        root = self.root / ".claude" / "harness-state"
        for sub in (".sessions", ".issues", ".logs", ".rate"):
            self.assertTrue((root / sub).is_dir(), sub)
        self.assertTrue((root / ".session-id").exists())
        self.assertEqual((root / ".session-id").read_text(), "sessA")
        self.assertTrue((sd / "live.json").exists())

    def test_pointer_read_write_roundtrip(self):
        ss.write_session_pointer("abc-123", project_root=self.root)
        self.assertEqual(ss.read_session_pointer(project_root=self.root), "abc-123")

    def test_current_session_env_var_wins(self):
        ss.write_session_pointer("fromFile", project_root=self.root)
        with mock.patch.dict(os.environ, {"HARNESS_SESSION_ID": "fromEnv"}):
            self.assertEqual(ss.current_session_id(self.root), "fromEnv")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HARNESS_SESSION_ID", None)
            self.assertEqual(ss.current_session_id(self.root), "fromFile")

    def test_invalid_pointer_rejected(self):
        root = ss.state_root(self.root)
        (root / ".session-id").write_text("../evil")
        self.assertEqual(ss.read_session_pointer(self.root), "")


class RalphPathTests(unittest.TestCase):
    """ralph 스킬 세션 경로 격리 — /tmp 교차오염 버그 회귀 방지."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = _touch_claude(Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    def test_ralph_dir_under_session(self):
        d = ss.ralph_dir("sessA", project_root=self.root)
        expected = self.root / ".claude" / "harness-state" / ".sessions" / "sessA" / "ralph"
        self.assertEqual(d.resolve(), expected.resolve())
        self.assertTrue(d.is_dir())

    def test_ralph_paths_have_correct_filenames(self):
        self.assertEqual(ss.ralph_task_path("sessA", self.root).name, "task.md")
        self.assertEqual(ss.ralph_progress_path("sessA", self.root).name, "progress.md")
        self.assertEqual(ss.ralph_state_path("sessA", self.root).name, "state.json")

    def test_ralph_sessions_are_isolated(self):
        a = ss.ralph_dir("sessA", project_root=self.root)
        b = ss.ralph_dir("sessB", project_root=self.root)
        self.assertNotEqual(a, b)
        (a / "task.md").write_text("A의 작업")
        (b / "task.md").write_text("B의 작업")
        self.assertEqual((a / "task.md").read_text(), "A의 작업")
        self.assertEqual((b / "task.md").read_text(), "B의 작업")

    def test_ralph_fallback_to_global_when_sid_invalid(self):
        d = ss.ralph_dir("", project_root=self.root)
        self.assertEqual(d.parent.name, "_global")


class GlobalSignalTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = _touch_claude(Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    def test_global_signal_is_lenient(self):
        # 어떤 세션에서도 읽기/쓰기 가능 — 소유자 검증 없음
        ss.set_global_signal(self.root, harness_kill=True)
        data = ss.get_global_signal(self.root)
        self.assertTrue(data.get("harness_kill"))

    def test_global_signal_clear(self):
        ss.set_global_signal(self.root, harness_kill=True)
        ss.set_global_signal(self.root, harness_kill=None)
        self.assertNotIn("harness_kill", ss.get_global_signal(self.root))

    def test_child_subprocess_inherits_parent_flags_via_env(self):
        """하네스가 자식 CC 프로세스를 spawn할 때 HARNESS_SESSION_ID env로
        부모 세션의 flags_dir를 공유해야 한다.

        시나리오: 세션 A가 LGTM 기록 → 자식 engineer(새 session_id=Z)가
        commit-gate에서 LGTM 플래그 읽기. env 전파가 없으면 세션 Z 스코프에서
        빈 플래그를 보게 되어 commit deny.
        """
        # 세션 A에서 LGTM 플래그 기록 (하네스 impl_loop.py가 하는 일)
        from session_state import session_flags_dir
        flags_a = session_flags_dir("sessParent", "mb", "42", project_root=self.root)
        (flags_a / "mb_pr_reviewer_lgtm").touch()

        # 자식 프로세스 env 가정: 하네스 core.py가 주입하는 3종 env
        import subprocess as _subp
        result = _subp.run(
            ["python3", "-c",
             "import sys; sys.path.insert(0, '{}'); "
             "import harness_common; print(harness_common.get_flags_dir())".format(
                 str(Path(__file__).resolve().parent.parent)
             )],
            env={
                **os.environ,
                "HARNESS_SESSION_ID": "sessParent",
                "HARNESS_ISSUE_NUM": "42",
                "HARNESS_PREFIX": "mb",
            },
            cwd=str(self.root),
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        fdir = result.stdout.strip()
        expected = str(flags_a)
        self.assertEqual(fdir, expected,
                         "자식 subprocess가 env 우선으로 부모 세션 flags_dir를 봐야 함")
        # 실제로 플래그 파일 존재 확인
        self.assertTrue((Path(fdir) / "mb_pr_reviewer_lgtm").exists())

    def test_kill_signal_propagates_cross_session(self):
        """세션 A가 kill을 요청하면 세션 B의 다음 체크에서 감지되어야 함.
        하네스 core.kill_check / router의 kill 감지가 .global.json을 보는지.
        """
        # 세션 A에서 kill 기록
        ss.set_global_signal(self.root, harness_kill=True)
        # 세션 B에서 읽기 — 동일 .global.json
        signal = ss.get_global_signal(self.root)
        self.assertTrue(signal.get("harness_kill"))
        # kill 소비 후 해제
        ss.set_global_signal(self.root, harness_kill=None)
        self.assertFalse(ss.get_global_signal(self.root).get("harness_kill"))


class RegressionScenarioTests(unittest.TestCase):
    """PR #24/#26/#29 재현 박제."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = _touch_claude(Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    def test_pr29_internal_agent_does_not_pollute_whitelist(self):
        """PR #29: CC 내장 Explore 서브에이전트가 live.json을 오염시키지 않음.
        agent-gate.py가 CUSTOM_AGENTS 외 에이전트에는 쓰지 않도록 제어하므로,
        live.json에 'Explore'가 들어갈 경로가 없음."""
        ss.update_live("sA", project_root=self.root, agent="architect")
        # 다른 경로에서 'Explore'가 기록됐다고 가정 — 실제로는 hook이 막음
        # 여기선 단지 read 경로가 깨지지 않는지 확인
        live = ss.get_live("sA", project_root=self.root)
        self.assertEqual(live["agent"], "architect")

    def test_pr26_agent_tool_path_no_env_var(self):
        """PR #26: Agent 툴 경로(in-process)에서 env var가 전파 안 되어도 훅이 판정 가능해야 함.
        훅이 stdin session_id → live.json을 읽으므로 env var 불필요."""
        # agent-gate가 세션 scope에 기록
        ss.update_live("sX", project_root=self.root, agent="architect")
        # 그 다음 훅이 호출됨 — env var 없음, stdin에 session_id만 있음
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HARNESS_AGENT_NAME", None)
            os.environ.pop("HARNESS_SESSION_ID", None)
            agent = ss.active_agent({"session_id": "sX"}, project_root=self.root)
        self.assertEqual(agent, "architect")

    def test_subprocess_agent_env_var_authority(self):
        """하네스 subprocess 경로: claude CLI가 새 session_id로 stdin에 찍어도
        HARNESS_AGENT_NAME env가 권위 있는 신호로 작동해야 한다.
        (기존 live.json은 부모 세션 scope에 있어 접근 불가)"""
        ss.update_live("parent_sid", project_root=self.root, agent="architect")
        with mock.patch.dict(os.environ, {"HARNESS_AGENT_NAME": "architect"}):
            # stdin은 subprocess의 신규 session_id
            agent = ss.active_agent({"session_id": "new_subprocess_sid"},
                                    project_root=self.root)
        self.assertEqual(agent, "architect")

    def test_pr24_stale_flag_does_not_leak_to_new_session(self):
        """PR #24: 이전 세션 크래시 후 남은 잔재가 새 세션을 오인하지 않음.
        세션별 스코프라 이전 세션의 live.json은 새 세션과 무관."""
        # 이전 세션 크래시 시나리오 — 오래된 sOld의 live.json
        ss.update_live("sOld", project_root=self.root, agent="engineer")
        old = ss.live_path("sOld", project_root=self.root)
        os.utime(old, (0, 0))
        # 새 세션 시작
        ss.initialize_session("sNew", project_root=self.root)
        ss.cleanup_stale_sessions(self.root, keep="sNew")
        # 새 세션 기준 active_agent 조회 — 오래된 sOld는 이미 삭제됐거나 무관
        self.assertIsNone(
            ss.active_agent({"session_id": "sNew"}, project_root=self.root)
        )


class SkillStateTests(unittest.TestCase):
    """Phase 4: live.json.skill 상태 API 단위 테스트."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = _touch_claude(Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    def test_set_and_get_active_skill(self):
        ss.set_active_skill("sA", "ux", "medium", project_root=self.root)
        sk = ss.get_active_skill("sA", project_root=self.root)
        self.assertIsNotNone(sk)
        self.assertEqual(sk["name"], "ux")
        self.assertEqual(sk["level"], "medium")
        self.assertEqual(sk["reinforcements"], 0)
        self.assertIsInstance(sk["started_at"], int)

    def test_clear_active_skill_guarded_by_name(self):
        ss.set_active_skill("sA", "ux", "medium", project_root=self.root)
        # 다른 이름으로 청소 시도 → 거부
        self.assertFalse(
            ss.clear_active_skill("sA", expect_name="qa", project_root=self.root)
        )
        self.assertIsNotNone(ss.get_active_skill("sA", project_root=self.root))
        # 같은 이름 → 청소
        self.assertTrue(
            ss.clear_active_skill("sA", expect_name="ux", project_root=self.root)
        )
        self.assertIsNone(ss.get_active_skill("sA", project_root=self.root))

    def test_clear_active_skill_no_name_clears_anyway(self):
        ss.set_active_skill("sA", "ux", "medium", project_root=self.root)
        self.assertTrue(ss.clear_active_skill("sA", project_root=self.root))
        self.assertIsNone(ss.get_active_skill("sA", project_root=self.root))

    def test_bump_reinforcement_increments(self):
        ss.set_active_skill("sA", "ralph", "heavy", project_root=self.root)
        self.assertEqual(ss.bump_skill_reinforcement("sA", project_root=self.root), 1)
        self.assertEqual(ss.bump_skill_reinforcement("sA", project_root=self.root), 2)
        sk = ss.get_active_skill("sA", project_root=self.root)
        self.assertEqual(sk["reinforcements"], 2)

    def test_bump_no_active_skill_returns_neg(self):
        self.assertEqual(ss.bump_skill_reinforcement("sA", project_root=self.root), -1)

    def test_active_skill_helper_with_stdin(self):
        ss.set_active_skill("sA", "qa", "medium", project_root=self.root)
        sk = ss.active_skill({"session_id": "sA"}, project_root=self.root)
        self.assertIsNotNone(sk)
        self.assertEqual(sk["name"], "qa")

    def test_active_skill_isolated_per_session(self):
        ss.set_active_skill("sA", "ux", "medium", project_root=self.root)
        ss.set_active_skill("sB", "qa", "medium", project_root=self.root)
        a = ss.active_skill({"session_id": "sA"}, project_root=self.root)
        b = ss.active_skill({"session_id": "sB"}, project_root=self.root)
        self.assertEqual(a["name"], "ux")
        self.assertEqual(b["name"], "qa")

    def test_invalid_session_id_noop(self):
        ss.set_active_skill("../evil", "ux", "medium", project_root=self.root)
        self.assertIsNone(ss.get_active_skill("../evil", project_root=self.root))


class PidSlotCleanupTests(unittest.TestCase):
    """Phase 4 T4: `_pid-<pid>-<ts>` 폴백 슬롯 청소 정책."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = _touch_claude(Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    def test_pid_slot_with_alive_pid_preserved(self):
        sessions = ss.state_root(self.root) / ".sessions"
        slot = sessions / f"_pid-{os.getpid()}-1000000"
        slot.mkdir(parents=True)
        (slot / "live.json").write_text("{}")
        # 매우 오래된 mtime — 정규 슬롯이면 삭제됐을 것
        os.utime(slot / "live.json", (0, 0))
        removed = ss.cleanup_stale_sessions(self.root)
        self.assertTrue(slot.exists(), "활성 PID 슬롯은 mtime과 무관하게 보존")
        self.assertEqual(removed, 0)

    def test_pid_slot_with_dead_pid_removed(self):
        sessions = ss.state_root(self.root) / ".sessions"
        slot = sessions / "_pid-999999-1000000"  # 존재하지 않는 PID
        slot.mkdir(parents=True)
        (slot / "live.json").write_text("{}")
        removed = ss.cleanup_stale_sessions(self.root)
        self.assertFalse(slot.exists(), "죽은 PID 슬롯은 즉시 제거")
        self.assertEqual(removed, 1)

    def test_global_slot_preserved(self):
        sessions = ss.state_root(self.root) / ".sessions"
        slot = sessions / "_global"
        slot.mkdir(parents=True)
        (slot / "live.json").write_text("{}")
        os.utime(slot / "live.json", (0, 0))
        ss.cleanup_stale_sessions(self.root)
        self.assertTrue(slot.exists(), "_global은 항상 보존")

    def test_keep_session_preserved(self):
        sessions = ss.state_root(self.root) / ".sessions"
        slot = sessions / "sNow"
        slot.mkdir(parents=True)
        (slot / "live.json").write_text("{}")
        os.utime(slot / "live.json", (0, 0))
        ss.cleanup_stale_sessions(self.root, keep="sNow")
        self.assertTrue(slot.exists(), "keep 세션은 보존")


if __name__ == "__main__":
    unittest.main()
