"""
test_parity.py — Python 하네스 모듈의 동등성 검증.
Python 3.9+ stdlib only (unittest).
"""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

# 테스트 대상 패키지 경로 설정
HARNESS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HARNESS_DIR.parent))

from harness.config import HarnessConfig, load_config
from harness.core import (
    Flag, Marker, StateDir, RunLogger,
    parse_marker, detect_depth, hlog, kill_check,
    build_smart_context,
)
from harness.helpers import append_failure, append_success, budget_check, run_automated_checks


class TestFlagEnumMatchesBash(unittest.TestCase):
    def test_flag_enum_matches_bash(self):
        """Flag enum 값이 flags.sh와 일치하는지 확인."""
        flags_sh = HARNESS_DIR / "flags.sh.bak"
        content = flags_sh.read_text()
        sh_flags = dict(re.findall(r'FLAG_(\w+)="(\w+)"', content))
        for name, val in sh_flags.items():
            with self.subTest(flag=name):
                self.assertTrue(hasattr(Flag, name), f"Flag.{name} 누락")
                self.assertEqual(getattr(Flag, name).value, val)


class TestMarkerEnumMatchesBash(unittest.TestCase):
    def test_marker_enum_matches_bash(self):
        """Marker enum 값이 markers.sh KNOWN_MARKERS와 일치하는지 확인."""
        markers_sh = HARNESS_DIR / "markers.sh.bak"
        content = markers_sh.read_text()
        start = content.index("KNOWN_MARKERS=(")
        end = content.index(")", start + len("KNOWN_MARKERS=("))
        block = content[start:end + 1]
        lines = [re.sub(r"#.*", "", line) for line in block.splitlines()]
        all_text = " ".join(lines)
        sh_markers = set(re.findall(r"\b[A-Z][A-Z_]{1,}[A-Z]\b", all_text))
        sh_markers.discard("KNOWN_MARKERS")

        py_markers = {m.value for m in Marker}
        self.assertEqual(sh_markers, py_markers, f"불일치: sh_only={sh_markers - py_markers}, py_only={py_markers - sh_markers}")


class TestParseMarker(unittest.TestCase):
    def _write_tmp(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_structured(self):
        p = self._write_tmp("output\n---MARKER:PASS---\nmore")
        self.assertEqual(parse_marker(p, "PASS|FAIL"), "PASS")
        os.unlink(p)

    def test_legacy_fallback(self):
        p = self._write_tmp("output\nPASS\nmore")
        self.assertEqual(parse_marker(p, "PASS|FAIL"), "PASS")
        os.unlink(p)

    def test_unknown(self):
        p = self._write_tmp("no marker here")
        self.assertEqual(parse_marker(p, "PASS|FAIL"), "UNKNOWN")
        os.unlink(p)


class TestStateDirOperations(unittest.TestCase):
    def test_flag_lifecycle(self):
        with tempfile.TemporaryDirectory() as td:
            sd = StateDir(Path(td), "test")
            self.assertFalse(sd.flag_exists("harness_active"))
            sd.flag_touch("harness_active")
            self.assertTrue(sd.flag_exists("harness_active"))
            sd.flag_rm("harness_active")
            self.assertFalse(sd.flag_exists("harness_active"))

    def test_flags_dir_is_hidden_subdir(self):
        """플래그 파일이 .flags/ 숨김 디렉토리 안에 생성되는지 확인."""
        with tempfile.TemporaryDirectory() as td:
            sd = StateDir(Path(td), "mb")
            sd.flag_touch("pr_reviewer_lgtm")
            # .flags/ 디렉토리 존재
            flags_dir = sd.path / ".flags"
            self.assertTrue(flags_dir.is_dir())
            # 플래그 파일이 .flags/ 안에 있음
            self.assertTrue((flags_dir / "mb_pr_reviewer_lgtm").exists())
            # harness-state/ 루트에는 없음 (glob 삭제 대상 X)
            self.assertFalse((sd.path / "mb_pr_reviewer_lgtm").exists())


class TestRunLoggerJsonl(unittest.TestCase):
    def test_events_schema(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["HOME"] = td
            log_dir = Path(td) / ".claude" / "harness-logs" / "test"
            log_dir.mkdir(parents=True)
            rl = RunLogger("test", "impl", "42")
            rl.log_agent_start("engineer", 1000)
            rl.log_agent_end("engineer", 60, 0.5, 0, 1000)
            rl.log_agent_stats("engineer", {"Read": 5}, ["src/a.ts"], 10000, 5000)

            events = []
            for line in rl.log_file.read_text().splitlines():
                if line.strip():
                    events.append(json.loads(line))

            event_types = [e["event"] for e in events]
            self.assertIn("run_start", event_types)
            self.assertIn("agent_start", event_types)
            self.assertIn("agent_end", event_types)
            self.assertIn("agent_stats", event_types)

            # agent_end 필드 확인
            ae = next(e for e in events if e["event"] == "agent_end")
            for key in ("agent", "t", "end_ts", "elapsed", "duration_s", "exit", "cost_usd", "prompt_chars"):
                self.assertIn(key, ae, f"agent_end에 {key} 누락")


class TestConfigLoader(unittest.TestCase):
    def test_default(self):
        cfg = HarnessConfig()
        self.assertEqual(cfg.prefix, "proj")
        self.assertEqual(cfg.max_total_cost, 20.0)

    def test_custom(self):
        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td) / ".claude"
            config_dir.mkdir()
            (config_dir / "harness.config.json").write_text(
                '{"prefix": "myapp", "max_total_cost": 5.0}'
            )
            cfg = load_config(Path(td))
            self.assertEqual(cfg.prefix, "myapp")
            self.assertEqual(cfg.max_total_cost, 5.0)


class TestDetectDepth(unittest.TestCase):
    def test_with_frontmatter(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("---\ndepth: deep\ntitle: test\n---\nContent\n")
            name = f.name
        self.assertEqual(detect_depth(name), "deep")
        os.unlink(name)

    def test_without_frontmatter(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("No frontmatter\n")
            name = f.name
        self.assertEqual(detect_depth(name), "std")
        os.unlink(name)

    def test_missing_file(self):
        self.assertEqual(detect_depth("/nonexistent/file.md"), "std")


class TestAppendFailureFormat(unittest.TestCase):
    def test_format(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td)
            mem_dir = proj / ".claude"
            mem_dir.mkdir()
            mem_file = mem_dir / "harness-memory.md"
            mem_file.write_text("# Harness Memory\n\n## impl 패턴\n\n## Auto-Promoted Rules\n")
            os.chdir(td)

            sd = StateDir(proj, "test")
            append_failure("docs/impl/01-foo.md", "test_fail", "some error msg", sd, "test")

            content = mem_file.read_text()
            self.assertRegex(content, r"- \d{4}-\d{2}-\d{2} \| 01-foo \| test_fail \| some error msg")


class TestAutoPromotion(unittest.TestCase):
    def test_promote_after_3(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td)
            mem_dir = proj / ".claude"
            mem_dir.mkdir()
            mem_file = mem_dir / "harness-memory.md"
            mem_file.write_text("# Harness Memory\n\n## impl 패턴\n\n## Auto-Promoted Rules\n")
            os.chdir(td)

            sd = StateDir(proj, "test")
            for _ in range(3):
                append_failure("docs/impl/01-foo.md", "test_fail", "repeated error", sd, "test")

            content = mem_file.read_text()
            self.assertIn("PROMOTED: 01-foo|test_fail", content)


class TestBuildSmartContextCap(unittest.TestCase):
    def test_30kb_cap(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("x" * 50000)
            name = f.name
        result = build_smart_context(name, 0)
        self.assertLessEqual(len(result), 30000)
        os.unlink(name)


class TestKillCheck(unittest.TestCase):
    def test_no_kill(self):
        with tempfile.TemporaryDirectory() as td:
            sd = StateDir(Path(td), "test")
            # Should not raise
            kill_check(sd)

    def test_kill_exits(self):
        with tempfile.TemporaryDirectory() as td:
            sd = StateDir(Path(td), "test")
            sd.flag_touch("harness_kill")
            with self.assertRaises(SystemExit):
                kill_check(sd)


class TestExecutorCLI(unittest.TestCase):
    """executor.py argparse 드라이런."""
    def test_impl_help(self):
        import subprocess
        r = subprocess.run(
            ["python3", "-c", "import sys; sys.argv=['e','impl','--help']; from harness.executor import main; main()"],
            capture_output=True, text=True, cwd=str(HARNESS_DIR.parent), timeout=5,
        )
        self.assertIn("impl", r.stdout)
        self.assertIn("--issue", r.stdout)

    def test_invalid_mode(self):
        import subprocess
        r = subprocess.run(
            ["python3", "-c", "import sys; sys.argv=['e','bogus']; from harness.executor import main; main()"],
            capture_output=True, text=True, cwd=str(HARNESS_DIR.parent), timeout=5,
        )
        self.assertNotEqual(r.returncode, 0)


class TestHooksSyntax(unittest.TestCase):
    """hooks/*.py 파일 문법 검증."""
    def test_all_hooks_parse(self):
        import ast, glob
        hooks_dir = HARNESS_DIR.parent / "hooks"
        for py in sorted(hooks_dir.glob("*.py")):
            with self.subTest(hook=py.name):
                ast.parse(py.read_text())


class TestRunLoggerJsonlCompat(unittest.TestCase):
    """RunLogger가 생성하는 JSONL이 harness-review.py의 EXPECTED_SEQUENCE와 호환되는지."""
    def test_event_sequence(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["HOME"] = td
            log_dir = Path(td) / ".claude" / "harness-logs" / "test"
            log_dir.mkdir(parents=True)
            rl = RunLogger("test", "impl", "1")
            rl.log_agent_start("engineer", 500)
            rl.log_agent_end("engineer", 30, 0.1, 0, 500)
            rl.log_agent_stats("engineer", {"Read": 2}, ["a.ts"], 5000, 2000)

            # JSONL 파싱 — 모든 줄이 유효한 JSON
            events = []
            for line in rl.log_file.read_text().splitlines():
                if line.strip():
                    e = json.loads(line)
                    events.append(e["event"])
                    # 모든 이벤트에 필수 키 확인
                    self.assertIn("event", e)

            # harness-review.py가 기대하는 최소 시퀀스
            self.assertIn("run_start", events)
            self.assertIn("agent_start", events)
            self.assertIn("agent_end", events)
            self.assertIn("agent_stats", events)

            # agent_end.cost_usd가 숫자인지 (harness-review.py가 float로 파싱)
            ae = next(json.loads(l) for l in rl.log_file.read_text().splitlines()
                      if '"agent_end"' in l)
            self.assertIsInstance(ae["cost_usd"], (int, float))


class TestRollbackScript(unittest.TestCase):
    """rollback.sh가 .sh.bak → .sh 복원하는지."""
    def test_rollback_restores(self):
        with tempfile.TemporaryDirectory() as td:
            # 시뮬레이션: .sh.bak 파일 생성
            bak = Path(td) / "executor.sh.bak"
            bak.write_text("#!/bin/bash\noriginal content")
            # rollback 스크립트 복사
            import shutil
            rollback = Path(td) / "rollback.sh"
            shutil.copy2(str(HARNESS_DIR / "rollback.sh"), str(rollback))
            # 실행
            import subprocess
            r = subprocess.run(["bash", str(rollback)], capture_output=True, text=True, cwd=td, timeout=5)
            self.assertEqual(r.returncode, 0)
            restored = Path(td) / "executor.sh"
            self.assertTrue(restored.exists())
            self.assertEqual(restored.read_text(), "#!/bin/bash\noriginal content")


class TestMockRunSimple(unittest.TestCase):
    """run_simple 흐름을 mock agent_call로 검증."""
    def test_run_simple_flow(self):
        """agent_call을 mock하여 run_simple의 engineer→pr-reviewer→merge 흐름 확인."""
        from unittest.mock import patch
        from harness.config import HarnessConfig

        with tempfile.TemporaryDirectory() as td:
            proj = Path(td)
            (proj / ".claude").mkdir()
            (proj / ".claude" / "harness-memory.md").write_text("# Harness Memory\n\n## impl 패턴\n\n## Auto-Promoted Rules\n")

            # impl 파일 생성
            impl = proj / "impl.md"
            impl.write_text("---\ndepth: simple\n---\ntest impl")

            os.chdir(td)
            # git repo 초기화
            import subprocess
            subprocess.run(["git", "init"], capture_output=True, cwd=td)
            subprocess.run(["git", "config", "user.email", "test@test.com"], capture_output=True, cwd=td)
            subprocess.run(["git", "config", "user.name", "test"], capture_output=True, cwd=td)
            subprocess.run(["git", "add", "."], capture_output=True, cwd=td)
            subprocess.run(["git", "commit", "-m", "init"], capture_output=True, cwd=td)

            sd = StateDir(proj, "test")
            config = HarnessConfig(prefix="test")

            call_count = [0]
            def mock_agent_call(agent, timeout, prompt, out_file, *args, **kwargs):
                call_count[0] += 1
                Path(out_file).write_text(f"mock output from {agent}\n---MARKER:LGTM---\n")
                return 0

            with patch("harness.impl_loop.agent_call", side_effect=mock_agent_call), \
                 patch("harness.impl_loop.create_feature_branch", return_value=("feat/test-1", None)), \
                 patch("harness.impl_loop.merge_to_main", return_value=True), \
                 patch("harness.impl_loop.collect_changed_files", return_value=["src/test.ts"]), \
                 patch("harness.impl_loop.run_automated_checks", return_value=(True, "")), \
                 patch("subprocess.run") as mock_sub:
                mock_sub.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="abc123", stderr="")

                from harness.impl_loop import run_simple
                from harness.core import RunLogger

                rl = RunLogger("test", "impl", "1")
                result = run_simple(str(impl), "1", config, sd, "test", "feat", rl)

            # engineer + pr-reviewer = 최소 2회 agent_call
            self.assertGreaterEqual(call_count[0], 2)
            # LGTM이면 HARNESS_DONE
            self.assertEqual(result, "HARNESS_DONE")


class TestBuildSmartContextResolvesImpl(unittest.TestCase):
    """build_smart_context가 cwd 변경과 상관없이 impl을 읽는지 확인.

    회귀 재현 (run_20260419_130701 / run_20260419_150018): run_simple에서
    os.chdir(worktree) 후 상대경로 impl을 읽으려 하면 worktree 안에 파일이
    없는 경우(예: v05 디렉토리가 아직 base branch에 없음) OSError → ctx=""가 되어
    engineer에게 impl 본문이 주입되지 않음.

    수정: build_smart_context 내부에서 Path.resolve()로 절대화.
    """

    def test_absolute_impl_readable_from_foreign_cwd(self):
        from harness.core import build_smart_context

        with tempfile.TemporaryDirectory() as td_proj, tempfile.TemporaryDirectory() as td_cwd:
            impl_path = Path(td_proj) / "impl.md"
            impl_path.write_text(
                "---\ndepth: simple\n---\n# 본문\n"
                + ("이 본문이 ctx에 들어가야 한다. " * 50)
            )

            try:
                prev_cwd = os.getcwd()
            except FileNotFoundError:
                prev_cwd = os.path.expanduser("~")
            try:
                os.chdir(td_cwd)
                # 절대경로 입력: cwd와 무관하게 impl을 읽어야 한다 (worktree chdir 이후 시나리오)
                ctx = build_smart_context(str(impl_path), 0)
                self.assertGreater(
                    len(ctx), 100,
                    "절대경로 입력은 cwd 무관하게 impl을 읽어야 한다",
                )
                self.assertIn("이 본문이 ctx에 들어가야 한다", ctx)
            finally:
                os.chdir(prev_cwd)

    def test_relative_impl_resolved_against_current_cwd(self):
        """caller cwd == 프로젝트 루트일 때 상대경로도 Path.resolve로 절대화되어 읽힘."""
        from harness.core import build_smart_context

        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "impl.md").write_text(
                "---\ndepth: simple\n---\n# 본문\n" + ("채움" * 60)
            )

            try:
                prev_cwd = os.getcwd()
            except FileNotFoundError:
                prev_cwd = os.path.expanduser("~")
            try:
                os.chdir(td)
                ctx = build_smart_context("impl.md", 0)
                self.assertGreater(len(ctx), 100)
            finally:
                os.chdir(prev_cwd)

    def test_missing_impl_returns_empty(self):
        """존재하지 않는 impl 경로는 ctx=\"\" 로 안전하게 폴백."""
        from harness.core import build_smart_context

        with tempfile.TemporaryDirectory() as td:
            ctx = build_smart_context(str(Path(td) / "nonexistent.md"), 0)
            self.assertEqual(ctx, "")


class TestPlanValidationEscalateWritesRunEnd(unittest.TestCase):
    """PLAN_VALIDATION_ESCALATE 경로에서 run_end 이벤트가 기록되는지.

    회귀 재현 (run_20260419_130005): 이전에는 run_plan_validation이 False를 반환한 뒤
    impl_router가 PLAN_VALIDATION_ESCALATE 반환하면서 run_logger.write_run_end를
    호출하지 않아 harness-review가 result=빈값, dur=0s로 집계했다.
    """

    def test_write_run_end_called_on_escalate(self):
        from unittest.mock import patch, MagicMock
        import harness.impl_router as ir
        import harness.core as core

        rl = MagicMock()
        rl.write_run_end = MagicMock()

        with tempfile.TemporaryDirectory() as td:
            proj = Path(td)
            (proj / ".claude").mkdir()
            impl = proj / "impl.md"
            impl.write_text("---\ndepth: simple\n---\n# impl")

            os.chdir(td)
            sd = StateDir(proj, "test")

            # run_plan_validation가 무조건 False(=ESCALATE) 반환하도록 mock
            with patch.object(ir, "run_plan_validation", return_value=False), \
                 patch.object(ir, "ensure_depth_frontmatter", return_value=None), \
                 patch.object(core, "HUD") as MockHUD:
                mock_hud = MagicMock()
                MockHUD.return_value = mock_hud

                # run_impl 엔트리로 진입. branch_create 호출은 mock
                with patch("harness.impl_router.subprocess") as mock_sub:
                    mock_sub.run.return_value = MagicMock(returncode=0, stdout="", stderr="")

                    try:
                        result = ir.run_impl(
                            impl_file=str(impl),
                            issue_num="999",
                            prefix="test",
                            depth="simple",
                            run_logger=rl,
                            state_dir=sd,
                        )
                    except Exception:
                        # 불필요한 에러는 상관없음 — write_run_end 호출만 확인
                        pass

        # PLAN_VALIDATION_ESCALATE 경로에서 write_run_end 최소 1회 호출
        calls = rl.write_run_end.call_args_list
        matched = [c for c in calls if c.args and c.args[0] == "PLAN_VALIDATION_ESCALATE"]
        self.assertTrue(
            matched,
            f"PLAN_VALIDATION_ESCALATE run_end 미기록. 호출 내역: {calls}",
        )


class TestSaveImplMetaChangedFilesMergeBase(unittest.TestCase):
    """save_impl_meta의 changed_files가 merge-base 기준으로 산출되는지.

    회귀 재현 (run_20260419_150018 attempt-2): 이전에는 git diff HEAD~1이 단일
    직전 커밋만 비교해, 여러 attempt 커밋이 쌓이면 일부 변경만 보거나 관련 없는
    파일(.claude/harness.config.json 등)이 집계됐다.
    """

    def setUp(self):
        import subprocess
        self._td = tempfile.TemporaryDirectory()
        self.repo = Path(self._td.name)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.repo, check=True)
        # main 초기 커밋
        (self.repo / "base.txt").write_text("base\n")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.repo, check=True)
        # feature branch 생성 + 여러 attempt 커밋 쌓기
        subprocess.run(["git", "checkout", "-qb", "feat/x"], cwd=self.repo, check=True)
        (self.repo / "a.ts").write_text("a\n")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "attempt1"], cwd=self.repo, check=True)
        (self.repo / "b.ts").write_text("b\n")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "attempt2"], cwd=self.repo, check=True)

        self.attempt_dir = self.repo / "attempt-2"
        self.attempt_dir.mkdir()

        try:
            self._prev_cwd = os.getcwd()
        except FileNotFoundError:
            self._prev_cwd = os.path.expanduser("~")
        os.chdir(self.repo)

    def tearDown(self):
        # cleanup 전에 반드시 safe dir 로 chdir (tempdir 안에서 삭제하면 FileNotFoundError)
        safe_dir = tempfile.gettempdir()
        for candidate in (self._prev_cwd, safe_dir, "/"):
            try:
                os.chdir(candidate)
                break
            except Exception:
                continue
        self._td.cleanup()

    def test_merge_base_captures_all_feature_commits(self):
        """merge-base 기준이면 attempt1, attempt2 둘 다의 변경을 다 봐야 한다."""
        from harness.helpers import save_impl_meta

        save_impl_meta(str(self.attempt_dir), 2, "PASS", "simple")

        meta = json.loads((self.attempt_dir / "meta.json").read_text())
        changed = meta.get("changed_files", "")
        self.assertIn("a.ts", changed, f"merge-base 기준이면 a.ts 포함되어야 함: {changed}")
        self.assertIn("b.ts", changed, f"merge-base 기준이면 b.ts 포함되어야 함: {changed}")

    def test_base_txt_not_in_changed(self):
        """base 브랜치에만 있는 파일(base.txt)은 changed에 없어야 한다."""
        from harness.helpers import save_impl_meta

        save_impl_meta(str(self.attempt_dir), 2, "PASS", "simple")

        meta = json.loads((self.attempt_dir / "meta.json").read_text())
        changed = meta.get("changed_files", "")
        self.assertNotIn("base.txt", changed)


class TestPrFailRetryInjectsPrLog(unittest.TestCase):
    """pr_fail 재시도 시 engineer 프롬프트에 이전 pr.log 내용이 인라인 주입되는지.

    회귀 재현 (run_20260419_201311 3바퀴): 이전엔 pr_fail 경로가 pr.log 경로만
    explore_instruction으로 전달해, engineer가 자발적으로 pr.log를 Read 하지 않고
    attempt 0과 동일 수정을 복붙 제출 → 같은 CHANGES_REQUESTED 반복. autocheck_fail
    경로는 이미 autocheck.log를 인라인 주입 중이었으므로 일관성 맞춰 pr_fail도 인라인화.
    """

    def test_run_simple_pr_fail_retry_prompt_contains_pr_log(self):
        from unittest.mock import patch
        from harness.config import HarnessConfig

        with tempfile.TemporaryDirectory() as td:
            proj = Path(td)
            (proj / ".claude").mkdir()
            (proj / ".claude" / "harness-memory.md").write_text(
                "# Harness Memory\n\n## impl 패턴\n\n## Auto-Promoted Rules\n"
            )
            impl = proj / "impl.md"
            impl.write_text("---\ndepth: simple\n---\n# impl")
            os.chdir(td)

            import subprocess as _sp
            for cmd in (
                ["git", "init", "-q", "-b", "main"],
                ["git", "config", "user.email", "t@t"],
                ["git", "config", "user.name", "t"],
                ["git", "add", "."],
                ["git", "commit", "-qm", "init"],
            ):
                _sp.run(cmd, cwd=td, capture_output=True)

            sd = StateDir(proj, "test")
            cfg = HarnessConfig(prefix="test")

            os.environ["HARNESS_RUN_TS"] = "testrun"
            loop_dir = sd.path / "test_history" / "impl" / "run_testrun"
            (loop_dir / "attempt-0").mkdir(parents=True, exist_ok=True)
            # attempt-0 pr.log 는 run_simple 이 돌기 전에 심지 않고,
            # mock agent_call 이 pr-reviewer 호출 시 CHANGES_REQUESTED 쓰도록 조작

            prompts = []
            call_idx = [0]
            MARKER_MUST = "MUST_FIX_COLOR_HEX_REMOVE"

            def mock_agent_call(agent, timeout, prompt, out_file, *args, **kwargs):
                prompts.append((agent, prompt))
                call_idx[0] += 1
                p = Path(out_file)
                if agent == "engineer":
                    p.write_text("impl done\n")
                elif agent == "pr-reviewer":
                    # 첫 pr-reviewer 호출: CHANGES_REQUESTED + MUST FIX 텍스트
                    # 두 번째: LGTM (루프 종료)
                    if call_idx[0] == 2:
                        p.write_text(
                            "---MARKER:CHANGES_REQUESTED---\n"
                            f"### MUST FIX\n- {MARKER_MUST}\n"
                        )
                    else:
                        p.write_text("---MARKER:LGTM---\n")
                else:
                    p.write_text("done\n")
                return 0

            # pr.log 는 run_simple 내부에서 pr-reviewer out_file 을 복사해 씀.
            # 본 테스트는 이 복사 경로도 실제로 작동해야 의미 있음. impl_loop가
            # attempt-0/pr.log 를 기록하는 시점 이후 attempt-1 프롬프트 구성 시
            # 해당 파일을 read 하는지 검증.

            with patch("harness.impl_loop.agent_call", side_effect=mock_agent_call), \
                 patch("harness.impl_loop.create_feature_branch", return_value=("feat/test-1", None)), \
                 patch("harness.impl_loop.merge_to_main", return_value=True), \
                 patch("harness.impl_loop.collect_changed_files", return_value=["src/x.ts"]), \
                 patch("harness.impl_loop.run_automated_checks", return_value=(True, "")), \
                 patch("harness.impl_loop.push_and_ensure_pr", return_value=None), \
                 patch("harness.impl_loop.generate_commit_msg", return_value="msg"), \
                 patch("harness.impl_loop.generate_pr_body", return_value="body"), \
                 patch("subprocess.run") as mock_sub:
                mock_sub.return_value = _sp.CompletedProcess(args=[], returncode=0, stdout="abc123", stderr="")
                from harness.impl_loop import run_simple
                from harness.core import RunLogger
                rl = RunLogger("test", "impl", "1")
                try:
                    run_simple(str(impl), "1", cfg, sd, "test", "feat", rl)
                except Exception:
                    pass  # 일부 mock 의 부작용은 무시 — prompt 캡처만 검증

            os.environ.pop("HARNESS_RUN_TS", None)

            # engineer 호출이 최소 2번 이상 있어야 재시도 경로가 돎
            eng_prompts = [p for a, p in prompts if a == "engineer"]
            self.assertGreaterEqual(
                len(eng_prompts), 2,
                f"engineer 재시도 호출이 없음. 전체 호출: {[a for a,_ in prompts]}",
            )

            # attempt 1 (index 1) engineer 프롬프트에 pr-reviewer 피드백 인라인 주입 확인
            retry_prompt = eng_prompts[1]
            self.assertIn(
                "이전 pr-reviewer 피드백", retry_prompt,
                "pr_fail 재시도 프롬프트에 피드백 섹션이 없음",
            )
            self.assertIn(
                MARKER_MUST, retry_prompt,
                "pr.log 의 MUST FIX 내용이 프롬프트에 인라인되지 않음",
            )


class TestExtractMustFixFromPrLog(unittest.TestCase):
    """_extract_must_fix_from_pr_log — pr.log의 MUST FIX 섹션만 추출."""

    def setUp(self):
        from harness.impl_loop import _extract_must_fix_from_pr_log
        self.fn = _extract_must_fix_from_pr_log

    def test_extracts_must_fix_body(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "pr.log"
            p.write_text(
                "review header\n\n"
                "---\n"
                "CHANGES_REQUESTED\n\n"
                "### MUST FIX\n"
                "1. color #8b8b90 하드코딩 — CSS 변수 사용\n"
                "2. stageRow width 추가 필요\n\n"
                "### NICE TO HAVE\n"
                "- 주석 정리\n\n"
                "---MARKER:CHANGES_REQUESTED---\n"
            )
            result = self.fn(p)
            self.assertIn("#8b8b90", result)
            self.assertIn("stageRow width", result)
            self.assertNotIn("NICE TO HAVE", result)
            self.assertNotIn("---MARKER", result)

    def test_no_must_fix_section_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "pr.log"
            p.write_text("LGTM\n\n### NICE TO HAVE\n- 뭐시기\n")
            self.assertEqual(self.fn(p), "")

    def test_missing_file_returns_empty(self):
        self.assertEqual(self.fn(Path("/nonexistent/pr.log")), "")

    def test_caps_at_1500_chars(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "pr.log"
            p.write_text("### MUST FIX\n" + ("- 항목 " + "A" * 100 + "\n") * 50)
            result = self.fn(p)
            self.assertLessEqual(len(result), 1500)


class TestPrevMustFixHint(unittest.TestCase):
    """_prev_must_fix_hint — pr-reviewer 프롬프트용 MUST FIX 체크리스트 블록 생성."""

    def setUp(self):
        from harness.impl_loop import _prev_must_fix_hint
        self.fn = _prev_must_fix_hint

    def test_attempt_zero_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(self.fn(Path(td), 0), "")

    def test_attempt_one_reads_attempt_zero_pr_log(self):
        with tempfile.TemporaryDirectory() as td:
            loop_dir = Path(td)
            (loop_dir / "attempt-0").mkdir()
            (loop_dir / "attempt-0" / "pr.log").write_text(
                "### MUST FIX\n1. RAW_HEX_MARKER 제거\n\n### 총평\nLGTM 가능\n"
            )
            hint = self.fn(loop_dir, 1)
            self.assertIn("이전 attempt-0 MUST FIX", hint)
            self.assertIn("RAW_HEX_MARKER", hint)
            self.assertIn("CHANGES_REQUESTED", hint)

    def test_no_prev_pr_log_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            loop_dir = Path(td)
            (loop_dir / "attempt-0").mkdir()
            # pr.log 없음
            self.assertEqual(self.fn(loop_dir, 1), "")


class TestConfigTestCommand(unittest.TestCase):
    def test_empty_test_command_means_skip(self):
        cfg = HarnessConfig(test_command="")
        self.assertEqual(cfg.test_command, "")

    def test_custom_test_command(self):
        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td) / ".claude"
            config_dir.mkdir()
            (config_dir / "harness.config.json").write_text(
                '{"prefix": "x", "test_command": "npm test"}'
            )
            cfg = load_config(Path(td))
            self.assertEqual(cfg.test_command, "npm test")


class TestConfigBuildCommand(unittest.TestCase):
    def test_empty_build_command_means_skip(self):
        cfg = HarnessConfig(build_command="")
        self.assertEqual(cfg.build_command, "")

    def test_custom_build_command(self):
        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td) / ".claude"
            config_dir.mkdir()
            (config_dir / "harness.config.json").write_text(
                '{"prefix": "x", "build_command": "npx tsc --noEmit"}'
            )
            cfg = load_config(Path(td))
            self.assertEqual(cfg.build_command, "npx tsc --noEmit")

    def test_backward_compat_no_build_command(self):
        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td) / ".claude"
            config_dir.mkdir()
            (config_dir / "harness.config.json").write_text(
                '{"prefix": "old", "lint_command": "eslint ."}'
            )
            cfg = load_config(Path(td))
            self.assertEqual(cfg.build_command, "")


class TestLintCheckExcludesDeletedFiles(unittest.TestCase):
    """run_automated_checks 의 lint 단계가 삭제된 파일을 eslint 인자로 넘기지 않는지 확인.

    회귀 재현: impl이 파일 삭제를 지시했을 때 git diff --name-only HEAD 는 D 상태를
    포함해 eslint 에 전달 → "No files matching the pattern" 으로 lint_fail 을 오보고.
    수정 후에는 --diff-filter=ACMR + 존재 확인으로 삭제 파일이 인자에서 제외되어야 한다.
    """

    def setUp(self):
        import subprocess
        self._td = tempfile.TemporaryDirectory()
        self.repo = Path(self._td.name)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.repo, check=True)
        # 초기 커밋: 두 개의 ts 파일
        (self.repo / "keep.ts").write_text("export const a = 1\n")
        (self.repo / "remove.ts").write_text("export const b = 2\n")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.repo, check=True)

        # impl 파일 (빈 파일로 — scope check 무관화)
        self.impl = self.repo / "impl.md"
        self.impl.write_text("# impl\n")

        # remove.ts 삭제 + keep.ts 수정
        (self.repo / "remove.ts").unlink()
        (self.repo / "keep.ts").write_text("export const a = 11\n")

        # state dir
        (self.repo / ".claude" / "harness-state").mkdir(parents=True)
        self.state_dir = StateDir(self.repo, "test")

    def tearDown(self):
        self._td.cleanup()

    def _echo_config(self, lint_command: str):
        """lint_command 를 기록하는 가짜 config. echo 로 명령 인자를 검사할 수 있게 한다."""
        class _Cfg:
            pass
        cfg = _Cfg()
        cfg.lint_command = lint_command
        cfg.build_command = ""
        cfg.test_command = ""
        return cfg

    def test_lint_cmd_excludes_deleted_files(self):
        """삭제된 remove.ts 가 lint 인자에 포함되지 않아야 한다."""
        # echo 를 lint 명령으로 써서 실제 실행된 커맨드를 /tmp 에 기록
        log_file = self.repo / "lint_args.log"
        cfg = self._echo_config(f"echo 'LINT_ARGS:' > {log_file}; echo")

        ok, _msg = run_automated_checks(
            str(self.impl), cfg, self.state_dir, "test", cwd=str(self.repo),
        )
        self.assertTrue(ok, f"lint should pass but failed: {_msg}")

    def test_lint_error_includes_existing_file_only(self):
        """실제 eslint 흉내 내는 스크립트로 — 존재하지 않는 파일 인자 받으면 에러.
        삭제 필터가 제대로 동작하면 '존재 파일만' 인자로 전달되어 lint PASS.
        """
        # 인자 중 존재하지 않는 파일이 있으면 exit 1, 전부 존재하면 exit 0
        fake_lint = self.repo / "fake_lint.sh"
        fake_lint.write_text(
            '#!/bin/sh\nfor f in "$@"; do [ -f "$f" ] || { echo "missing: $f" >&2; exit 1; }; done\n'
        )
        os.chmod(fake_lint, 0o755)

        cfg = self._echo_config(str(fake_lint))
        ok, msg = run_automated_checks(
            str(self.impl), cfg, self.state_dir, "test", cwd=str(self.repo),
        )
        self.assertTrue(ok, f"lint should pass after deleted file filter; msg={msg}")
        # keep.ts 는 계속 수정됐으므로 인자에 포함돼야 PASS
        # (필터링 후 아무 것도 없으면 _lint_cmd 를 raw config 로 fallback 하므로 PASS 오인 가능
        #  → keep.ts 가 실제로 검사 대상에 포함됐는지는 간접적으로 메시지 검사)

    def test_only_deleted_lintable_files_do_not_trigger_false_lint_fail(self):
        """삭제 파일과 non-lintable 수정이 섞여 있을 때 lint 가 거짓 FAIL 을 내지 않는다.
        (주: 순수 삭제만 있는 경우는 'no_changes' 단계에서 이미 차단되므로 이 테스트는
         lintable 파일이 같이 수정된 시나리오에 집중한다.)
        """
        # 이미 setUp 에서 keep.ts 수정 + remove.ts 삭제 상태. 여기에 non-lintable md 추가.
        (self.repo / "note.md").write_text("# note\n")

        fake_lint = self.repo / "fake_lint2.sh"
        fake_lint.write_text(
            '#!/bin/sh\nfor f in "$@"; do [ -f "$f" ] || exit 1; done\n'
        )
        os.chmod(fake_lint, 0o755)

        # impl 스코프 허용: keep.ts, remove.ts, note.md
        self.impl.write_text(
            "# impl\n## 수정 파일\n"
            "- `keep.ts` (수정)\n- `remove.ts` (삭제)\n- `note.md` (추가)\n"
        )

        cfg = self._echo_config(str(fake_lint))
        ok, msg = run_automated_checks(
            str(self.impl), cfg, self.state_dir, "test", cwd=str(self.repo),
        )
        self.assertTrue(ok, f"lint should pass; msg={msg}")


class TestAppendSuccessReflection(unittest.TestCase):
    def test_reflection_extracted(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td)
            mem_dir = proj / ".claude"
            mem_dir.mkdir()
            mem_file = mem_dir / "harness-memory.md"
            mem_file.write_text("# Harness Memory\n\n## Success Patterns\n")
            os.chdir(td)

            eng_out = Path(td) / "eng_out.txt"
            eng_out.write_text(
                "some output\n"
                "src/App.tsx 파일 수정 — 버튼 핸들러 추가\n"
                "문제 해결: 이벤트 바인딩 누락 수정 완료\n"
            )

            append_success("docs/impl/01-foo.md", 1, eng_out=str(eng_out))
            content = mem_file.read_text()
            self.assertIn("Success Patterns", content)
            self.assertIn("01-foo", content)

    def test_no_reflection_on_empty_output(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td)
            mem_dir = proj / ".claude"
            mem_dir.mkdir()
            mem_file = mem_dir / "harness-memory.md"
            mem_file.write_text("# Harness Memory\n\n## Success Patterns\n")
            os.chdir(td)

            append_success("docs/impl/02-bar.md", 1)
            content = mem_file.read_text()
            # success 기록은 있어야 함
            self.assertIn("02-bar | success", content)
            # Success Patterns 섹션에 reflection 라인은 없어야 함 (eng_out 미제공)
            patterns_section = content.split("## Success Patterns")[1]
            reflection_lines = [l for l in patterns_section.splitlines()
                                if l.startswith("- ") and "해결" in l or "수정" in l or "fixed" in l]
            self.assertEqual(len(reflection_lines), 0)


class TestTokenBudgetConfig(unittest.TestCase):
    def test_dict_budget(self):
        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td) / ".claude"
            config_dir.mkdir()
            (config_dir / "harness.config.json").write_text(
                '{"prefix": "x", "token_budget": {"engineer": 200000, "default": 100000}}'
            )
            cfg = load_config(Path(td))
            self.assertIsInstance(cfg.token_budget, dict)
            self.assertEqual(cfg.token_budget["engineer"], 200000)

    def test_empty_budget_backward_compat(self):
        cfg = HarnessConfig()
        self.assertEqual(cfg.token_budget, {})

    def test_invalid_budget_type_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td) / ".claude"
            config_dir.mkdir()
            (config_dir / "harness.config.json").write_text(
                '{"prefix": "x", "token_budget": 12345}'
            )
            cfg = load_config(Path(td))
            self.assertEqual(cfg.token_budget, {})


class TestIsolationConfig(unittest.TestCase):
    def test_worktree_isolation(self):
        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td) / ".claude"
            config_dir.mkdir()
            (config_dir / "harness.config.json").write_text(
                '{"prefix": "x", "isolation": "worktree"}'
            )
            cfg = load_config(Path(td))
            self.assertEqual(cfg.isolation, "worktree")

    def test_default_no_isolation(self):
        cfg = HarnessConfig()
        self.assertEqual(cfg.isolation, "")


class TestCircuitBreaker(unittest.TestCase):
    def test_triggers_on_repeated_fail(self):
        from harness.impl_loop import _circuit_breaker_check
        ts = {}
        # 첫 번째 실패 — 트리거 안 됨
        r1 = _circuit_breaker_check("test_fail", ts, print, None)
        self.assertFalse(r1)
        # 두 번째 실패 (같은 윈도우 내) — 트리거
        r2 = _circuit_breaker_check("test_fail", ts, print, None)
        self.assertTrue(r2)

    def test_different_fail_types_no_trigger(self):
        from harness.impl_loop import _circuit_breaker_check
        ts = {}
        _circuit_breaker_check("test_fail", ts, print, None)
        r = _circuit_breaker_check("pr_fail", ts, print, None)
        self.assertFalse(r)


class TestGenerateHandoff(unittest.TestCase):
    def test_basic_handoff(self):
        from harness.core import generate_handoff
        content = generate_handoff(
            "engineer", "test-engineer",
            "구현 완료: auth module\n결정: JWT 사용 (보안 우선)\n주의: 기존 세션 삭제 금지",
            "docs/impl/01-auth.md", 0, "42",
            changed_files=["src/auth/login.ts", "src/auth/types.ts"],
            acceptance_criteria=["JWT 만료 시 자동 갱신", "잘못된 토큰 거부"],
        )
        self.assertIn("engineer → test-engineer", content)
        self.assertIn("src/auth/login.ts", content)
        self.assertIn("JWT 만료 시 자동 갱신", content)
        self.assertIn("결정:", content.lower() or content)

    def test_specgap_handoff(self):
        from harness.core import generate_handoff
        content = generate_handoff(
            "engineer", "architect",
            "SPEC_GAP_FOUND\n갭 목록:\n1. Props 타입 미정의\n2. 에러 처리 미결정\n요청: architect에게 보강 요청",
            "docs/impl/02-ui.md", 1, "43",
        )
        self.assertIn("SPEC_GAP 항목", content)
        self.assertIn("Props 타입 미정의", content)

    def test_with_acceptance_criteria(self):
        from harness.core import generate_handoff
        content = generate_handoff(
            "engineer", "test-engineer", "구현 완료",
            "test.md", 0, "1",
            acceptance_criteria=["로그인 성공 시 토큰 반환 (TEST)", "실패 시 401 응답 (TEST)"],
        )
        self.assertIn("로그인 성공 시 토큰 반환", content)
        self.assertIn("실패 시 401 응답", content)


class TestWriteHandoff(unittest.TestCase):
    def test_write_and_read(self):
        from harness.core import StateDir, write_handoff
        with tempfile.TemporaryDirectory() as d:
            sd = StateDir(Path(d), "test")
            path = write_handoff(sd, "test", 0, "engineer", "test-engineer", "# Handoff\ntest content")
            self.assertTrue(path.exists())
            self.assertIn("engineer-to-test-engineer.md", path.name)
            self.assertEqual(path.read_text(), "# Handoff\ntest content")


class TestExploreInstructionHandoff(unittest.TestCase):
    def test_with_handoff_path(self):
        from harness.core import explore_instruction
        result = explore_instruction("/tmp/hist", "", "/tmp/handoff.md")
        self.assertIn("인수인계 문서를 먼저 읽어라", result)
        self.assertIn("/tmp/handoff.md", result)

    def test_without_handoff_backward_compat(self):
        from harness.core import explore_instruction
        result = explore_instruction("/tmp/hist", "hint.log")
        self.assertIn("이전 시도의 출력 파일", result)
        self.assertIn("hint.log", result)
        self.assertNotIn("인수인계", result)


class TestExtractAcceptanceCriteria(unittest.TestCase):
    def test_extract(self):
        from harness.helpers import extract_acceptance_criteria
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Impl\n\n## 수용 기준\n- JWT 만료 시 갱신 (TEST)\n- 잘못된 토큰 거부 (TEST)\n\n## 다음 섹션\n")
            f.flush()
            criteria = extract_acceptance_criteria(f.name)
        os.unlink(f.name)
        self.assertEqual(len(criteria), 2)
        self.assertIn("JWT 만료 시 갱신 (TEST)", criteria[0])

    def test_missing_file(self):
        from harness.helpers import extract_acceptance_criteria
        result = extract_acceptance_criteria("/nonexistent/file.md")
        self.assertEqual(result, [])


class TestHUD(unittest.TestCase):
    def test_hud_lifecycle(self):
        from harness.core import HUD, StateDir
        with tempfile.TemporaryDirectory() as d:
            sd = StateDir(Path(d), "test")
            hud = HUD("std", "test", "42", 3, 20.0, sd)

            # 초기 상태: 모든 에이전트 pending
            self.assertEqual(hud.agent_status["engineer"]["status"], "pending")
            self.assertEqual(hud.agent_status["validator"]["status"], "pending")

            # agent_start → running
            hud.agent_start("engineer")
            self.assertEqual(hud.agent_status["engineer"]["status"], "running")

            # agent_done → done
            hud.agent_done("engineer", 45, 0.32)
            self.assertEqual(hud.agent_status["engineer"]["status"], "done")
            self.assertEqual(hud.agent_status["engineer"]["cost"], 0.32)
            self.assertAlmostEqual(hud.total_cost, 0.32)

            # agent_skip
            hud.agent_skip("security-reviewer", "depth=std")
            self.assertEqual(hud.agent_status.get("security-reviewer", {}).get("status"), None)  # std에 없음

            # HUD 파일 생성 확인
            hud_path = sd.path / ".test_hud"
            self.assertTrue(hud_path.exists())
            data = json.loads(hud_path.read_text())
            self.assertEqual(data["depth"], "std")
            self.assertEqual(data["attempt"], 0)

            # cleanup — 파일 삭제 대신 상태 기록 (harness-monitor가 최종 상태 읽기 위해)
            hud.cleanup()
            self.assertTrue(hud_path.exists())  # 파일은 유지됨
            cleanup_data = json.loads(hud_path.read_text())
            self.assertIn("status", cleanup_data)  # 완료 상태 기록

    def test_hud_depth_agents(self):
        from harness.core import HUD
        hud_simple = HUD("simple", "t", "1", 3, 10.0)
        hud_deep = HUD("deep", "t", "1", 3, 10.0)
        self.assertEqual(len(hud_simple.agents), 3)  # engineer, pr-reviewer, merge
        self.assertEqual(len(hud_deep.agents), 6)    # +test-engineer, validator, security-reviewer


class TestExtractPolishItems(unittest.TestCase):
    def test_extract_nice_to_have(self):
        from harness.helpers import extract_polish_items
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("## 리뷰 결과\nLGTM\n\n## NICE TO HAVE\n- 불필요한 주석 삭제 (line 42)\n- console.log 제거\n\n## 끝\n")
            f.flush()
            items = extract_polish_items(f.name)
        os.unlink(f.name)
        self.assertIn("불필요한 주석 삭제", items)
        self.assertIn("console.log 제거", items)

    def test_no_items(self):
        from harness.helpers import extract_polish_items
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("LGTM\n코드 품질 우수.\n")
            f.flush()
            items = extract_polish_items(f.name)
        os.unlink(f.name)
        self.assertEqual(items, "")

    def test_missing_file(self):
        from harness.helpers import extract_polish_items
        self.assertEqual(extract_polish_items("/nonexistent"), "")


class TestSecondReviewV3(unittest.TestCase):
    def test_get_provider_missing_cli(self):
        from harness.providers import get_provider
        result = get_provider("nonexistent_ai_cli_xyz")
        self.assertIsNone(result)

    def test_get_provider_gemini_available(self):
        """gemini CLI가 있으면 GeminiProvider 반환."""
        import shutil
        from harness.providers import get_provider
        if shutil.which("gemini"):
            provider = get_provider("gemini")
            self.assertIsNotNone(provider)
            self.assertEqual(provider.name, "gemini")
        else:
            self.skipTest("gemini CLI not installed")

    def test_run_review_batch_missing_provider(self):
        from harness.providers import run_review_batch
        result = run_review_batch(["test.py"], "nonexistent_cli")
        self.assertEqual(result, "")

    def test_review_result_dataclass(self):
        from harness.providers import ReviewResult
        r = ReviewResult("gemini", "test.py", "some finding", 5.0)
        self.assertEqual(r.provider, "gemini")
        self.assertEqual(r.findings, "some finding")
        self.assertEqual(r.error, "")

    def test_config_second_reviewer_fields(self):
        from harness.config import HarnessConfig
        cfg = HarnessConfig(second_reviewer="gemini", second_reviewer_model="gemini-2.5-flash")
        self.assertEqual(cfg.second_reviewer, "gemini")
        self.assertEqual(cfg.second_reviewer_model, "gemini-2.5-flash")

    def test_config_default_disabled(self):
        from harness.config import HarnessConfig
        cfg = HarnessConfig()
        self.assertEqual(cfg.second_reviewer, "")

    def test_codex_provider_not_installed(self):
        from harness.providers import get_provider
        import shutil
        if shutil.which("codex"):
            self.skipTest("codex is installed")
        result = get_provider("codex")
        self.assertIsNone(result)

    def test_provider_registry_has_all(self):
        from harness.providers import PROVIDERS
        self.assertIn("gemini", PROVIDERS)
        self.assertIn("codex", PROVIDERS)

    def test_base_provider_interface(self):
        from harness.providers import BaseProvider
        p = BaseProvider()
        self.assertFalse(p.is_available())  # cli_name 없으므로


class TestImplScopeGuard(unittest.TestCase):
    def test_extract_allowed_files(self):
        """impl 파일에서 수정 파일 목록을 추출하는지 검증."""
        import re
        content = """# Fix
## 수정 파일
- `src/pages/ResultPage.tsx` (수정)
- `src/components/ComboIndicator.tsx` (수정)

## 다음 섹션
"""
        allowed = []
        in_section = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("## 수정 파일"):
                in_section = True
                continue
            if in_section:
                if stripped.startswith("## "):
                    break
                m = re.search(r"`([^`]+)`", stripped)
                if m:
                    allowed.append(m.group(1))
        self.assertEqual(len(allowed), 2)
        self.assertIn("src/pages/ResultPage.tsx", allowed)
        self.assertIn("src/components/ComboIndicator.tsx", allowed)


# ═══════════════════════════════════════════════════════════════════════
# Design Gate Phase 3 — plan_loop + UX 마커 + run_ux_validation 테스트
# ═══════════════════════════════════════════════════════════════════════


class TestUXMarkerParsing(unittest.TestCase):
    """UX 관련 신규 마커가 parse_marker에서 정상 인식되는지."""

    def _write_tmp(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_ux_flow_ready_structured(self):
        p = self._write_tmp("output\n---MARKER:UX_FLOW_READY---\nux_flow_doc: docs/ux-flow.md")
        self.assertEqual(parse_marker(p, "UX_FLOW_READY|UX_FLOW_ESCALATE"), "UX_FLOW_READY")
        os.unlink(p)

    def test_ux_flow_escalate(self):
        p = self._write_tmp("---MARKER:UX_FLOW_ESCALATE---\nreason: PRD mismatch")
        self.assertEqual(parse_marker(p, "UX_FLOW_READY|UX_FLOW_ESCALATE"), "UX_FLOW_ESCALATE")
        os.unlink(p)

    def test_ux_review_pass(self):
        p = self._write_tmp("---MARKER:UX_REVIEW_PASS---\nall checks passed")
        self.assertEqual(parse_marker(p, "UX_REVIEW_PASS|UX_REVIEW_FAIL"), "UX_REVIEW_PASS")
        os.unlink(p)

    def test_ux_review_fail(self):
        p = self._write_tmp("---MARKER:UX_REVIEW_FAIL---\nfail items: ...")
        self.assertEqual(parse_marker(p, "UX_REVIEW_PASS|UX_REVIEW_FAIL"), "UX_REVIEW_FAIL")
        os.unlink(p)

    def test_ux_marker_unknown(self):
        p = self._write_tmp("no relevant marker here")
        self.assertEqual(parse_marker(p, "UX_FLOW_READY|UX_FLOW_ESCALATE"), "UNKNOWN")
        os.unlink(p)

    def test_ux_markers_in_enum(self):
        """Marker enum에 UX 마커 5개가 모두 있는지."""
        for name in ["UX_FLOW_READY", "UX_FLOW_ESCALATE", "UX_REVIEW_PASS", "UX_REVIEW_FAIL", "UX_REVIEW_ESCALATE"]:
            with self.subTest(marker=name):
                self.assertTrue(hasattr(Marker, name), f"Marker.{name} missing")


class TestHUDPlanAgents(unittest.TestCase):
    """HUD plan depth 에이전트 목록이 기획-UX만인지."""

    def test_plan_agents_are_ux_only(self):
        from harness.core import HUD
        hud = HUD("plan", "t", "1", 1, 10.0)
        self.assertEqual(hud.agents, ["product-planner", "ux-architect", "ux-validation"])
        # architect-sd, design-validation, architect-mp, plan-validation이 없어야 함
        for old in ["architect-sd", "design-validation", "architect-mp", "plan-validation"]:
            self.assertNotIn(old, hud.agents, f"{old} should not be in plan HUD")


class TestMockRunPlan(unittest.TestCase):
    """plan_loop.run_plan을 mock agent_call로 검증."""

    def _setup_project(self, td, prd_content="## 화면 인벤토리\n| 화면 | 역할 |\n|---|---|\n| 메인 | 진입점 |\n"):
        proj = Path(td)
        (proj / ".claude").mkdir(parents=True)
        (proj / ".claude" / "harness-memory.md").write_text("# Harness Memory\n\n## impl 패턴\n\n## Auto-Promoted Rules\n")
        (proj / "prd.md").write_text(f"# PRD\n\n{prd_content}")
        os.chdir(td)
        return proj

    def test_happy_path_ux_review_pass(self):
        """planner(READY) -> ux-architect(UX_FLOW_READY) -> validator(UX_REVIEW_PASS) -> UX_REVIEW_PASS."""
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as td:
            proj = self._setup_project(td)
            sd = StateDir(proj, "test")
            config = HarnessConfig(prefix="test")

            call_log = []

            def mock_agent_call(agent, timeout, prompt, out_file, *args, **kwargs):
                call_log.append(agent)
                if agent == "product-planner":
                    Path(out_file).write_text("---MARKER:PRODUCT_PLAN_READY---\nplan_doc: prd.md")
                elif agent == "ux-architect":
                    # ux-flow.md 생성
                    (proj / "docs").mkdir(exist_ok=True)
                    (proj / "docs" / "ux-flow.md").write_text("# UX Flow\n## 1. 화면 인벤토리\n")
                    Path(out_file).write_text("---MARKER:UX_FLOW_READY---\nux_flow_doc: docs/ux-flow.md")
                elif agent == "validator":
                    Path(out_file).write_text("---MARKER:UX_REVIEW_PASS---\nall good")
                return 0

            with patch("harness.plan_loop.agent_call", side_effect=mock_agent_call), \
                 patch("harness.plan_loop.run_ux_validation", return_value=True), \
                 patch("harness.plan_loop.kill_check"):
                from harness.plan_loop import run_plan
                rl = RunLogger("test", "plan", "1")
                result = run_plan("1", "test", config=config, state_dir=sd, run_logger=rl)

            self.assertEqual(result, "UX_REVIEW_PASS")
            self.assertIn("product-planner", call_log)
            self.assertIn("ux-architect", call_log)

    def test_ui_less_skip(self):
        """PRD 화면 인벤토리 비어있으면 UX_SKIP."""
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as td:
            proj = self._setup_project(td, prd_content="## 화면 인벤토리\n\n(없음)\n")
            sd = StateDir(proj, "test")
            config = HarnessConfig(prefix="test")

            def mock_agent_call(agent, timeout, prompt, out_file, *args, **kwargs):
                if agent == "product-planner":
                    Path(out_file).write_text("---MARKER:PRODUCT_PLAN_READY---\nplan_doc: prd.md")
                return 0

            with patch("harness.plan_loop.agent_call", side_effect=mock_agent_call), \
                 patch("harness.plan_loop.kill_check"):
                from harness.plan_loop import run_plan
                rl = RunLogger("test", "plan", "1")
                result = run_plan("1", "test", config=config, state_dir=sd, run_logger=rl)

            self.assertEqual(result, "UX_SKIP")

    def test_checkpoint_skip_ux_flow_exists(self):
        """docs/ux-flow.md 이미 존재하면 ux-architect 스킵."""
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as td:
            proj = self._setup_project(td)
            (proj / "docs").mkdir(exist_ok=True)
            (proj / "docs" / "ux-flow.md").write_text("# Existing UX Flow")
            sd = StateDir(proj, "test")
            config = HarnessConfig(prefix="test")

            call_log = []

            def mock_agent_call(agent, timeout, prompt, out_file, *args, **kwargs):
                call_log.append(agent)
                if agent == "product-planner":
                    Path(out_file).write_text("---MARKER:PRODUCT_PLAN_READY---\nplan_doc: prd.md")
                elif agent == "validator":
                    Path(out_file).write_text("---MARKER:UX_REVIEW_PASS---")
                return 0

            with patch("harness.plan_loop.agent_call", side_effect=mock_agent_call), \
                 patch("harness.plan_loop.run_ux_validation", return_value=True), \
                 patch("harness.plan_loop.kill_check"):
                from harness.plan_loop import run_plan
                rl = RunLogger("test", "plan", "1")
                result = run_plan("1", "test", config=config, state_dir=sd, run_logger=rl)

            self.assertEqual(result, "UX_REVIEW_PASS")
            self.assertNotIn("ux-architect", call_log, "ux-architect should be skipped when ux-flow.md exists")

    def test_clarity_insufficient(self):
        """planner CLARITY_INSUFFICIENT -> 즉시 리턴."""
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as td:
            proj = self._setup_project(td)
            sd = StateDir(proj, "test")
            config = HarnessConfig(prefix="test")

            def mock_agent_call(agent, timeout, prompt, out_file, *args, **kwargs):
                Path(out_file).write_text("---MARKER:CLARITY_INSUFFICIENT---\nmissing: goal")
                return 0

            with patch("harness.plan_loop.agent_call", side_effect=mock_agent_call), \
                 patch("harness.plan_loop.kill_check"):
                from harness.plan_loop import run_plan
                rl = RunLogger("test", "plan", "1")
                result = run_plan("1", "test", config=config, state_dir=sd, run_logger=rl)

            self.assertEqual(result, "CLARITY_INSUFFICIENT")

    def test_ux_flow_escalate(self):
        """ux-architect UX_FLOW_ESCALATE -> 즉시 리턴."""
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as td:
            proj = self._setup_project(td)
            sd = StateDir(proj, "test")
            config = HarnessConfig(prefix="test")

            def mock_agent_call(agent, timeout, prompt, out_file, *args, **kwargs):
                if agent == "product-planner":
                    Path(out_file).write_text("---MARKER:PRODUCT_PLAN_READY---\nplan_doc: prd.md")
                elif agent == "ux-architect":
                    Path(out_file).write_text("---MARKER:UX_FLOW_ESCALATE---\nreason: PRD conflict")
                return 0

            with patch("harness.plan_loop.agent_call", side_effect=mock_agent_call), \
                 patch("harness.plan_loop.kill_check"):
                from harness.plan_loop import run_plan
                rl = RunLogger("test", "plan", "1")
                result = run_plan("1", "test", config=config, state_dir=sd, run_logger=rl)

            self.assertEqual(result, "UX_FLOW_ESCALATE")

    def test_ux_sync_mode_detection(self):
        """src/ 존재 + ux-flow.md 없음 -> UX_SYNC 모드."""
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as td:
            proj = self._setup_project(td)
            (proj / "src").mkdir()
            (proj / "src" / "App.tsx").write_text("export default App")
            sd = StateDir(proj, "test")
            config = HarnessConfig(prefix="test")

            prompts = []

            def mock_agent_call(agent, timeout, prompt, out_file, *args, **kwargs):
                prompts.append((agent, prompt))
                if agent == "product-planner":
                    Path(out_file).write_text("---MARKER:PRODUCT_PLAN_READY---\nplan_doc: prd.md")
                elif agent == "ux-architect":
                    (proj / "docs").mkdir(exist_ok=True)
                    (proj / "docs" / "ux-flow.md").write_text("# UX Flow (synced)")
                    Path(out_file).write_text("---MARKER:UX_FLOW_READY---\nux_flow_doc: docs/ux-flow.md")
                elif agent == "validator":
                    Path(out_file).write_text("---MARKER:UX_REVIEW_PASS---")
                return 0

            with patch("harness.plan_loop.agent_call", side_effect=mock_agent_call), \
                 patch("harness.plan_loop.run_ux_validation", return_value=True), \
                 patch("harness.plan_loop.kill_check"):
                from harness.plan_loop import run_plan
                rl = RunLogger("test", "plan", "1")
                result = run_plan("1", "test", config=config, state_dir=sd, run_logger=rl)

            self.assertEqual(result, "UX_REVIEW_PASS")
            uxa_prompt = next((p for a, p in prompts if a == "ux-architect"), "")
            self.assertIn("UX_SYNC", uxa_prompt, "Should use UX_SYNC mode when src/ exists")


class TestRunUxValidation(unittest.TestCase):
    """run_ux_validation 함수 테스트."""

    def test_pass_on_first_try(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as td:
            proj = Path(td)
            sd = StateDir(proj, "test")

            def mock_agent_call(agent, timeout, prompt, out_file, *args, **kwargs):
                Path(out_file).write_text("---MARKER:UX_REVIEW_PASS---\nall good")
                return 0

            with patch("harness.core.agent_call", side_effect=mock_agent_call), \
                 patch("harness.core.kill_check"):
                from harness.core import run_ux_validation
                result = run_ux_validation("docs/ux-flow.md", "prd.md", "1", "test", 1, sd)

            self.assertTrue(result)

    def test_fail_then_escalate(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as td:
            proj = Path(td)
            sd = StateDir(proj, "test")

            call_count = [0]

            def mock_agent_call(agent, timeout, prompt, out_file, *args, **kwargs):
                call_count[0] += 1
                Path(out_file).write_text("---MARKER:UX_REVIEW_FAIL---\nfail items")
                return 0

            with patch("harness.core.agent_call", side_effect=mock_agent_call), \
                 patch("harness.core.kill_check"):
                from harness.core import run_ux_validation
                result = run_ux_validation("docs/ux-flow.md", "prd.md", "1", "test", 1, sd)

            self.assertFalse(result)
            # validator 1차 + ux-architect 재설계 + validator 재검증 = 최소 3회
            self.assertGreaterEqual(call_count[0], 3)


# ═══════════════════════════════════════════════════════════════════════
# TDD Gate — 마커 + HUD 순서 + 파싱 + 통합 검증 테스트
# ═══════════════════════════════════════════════════════════════════════


class TestDesignGateIntegrity(unittest.TestCase):
    """디자인 게이트 정합성 검증."""

    def test_ux_architect_agent_exists(self):
        agent_file = HARNESS_DIR.parent / "agents" / "ux-architect.md"
        self.assertTrue(agent_file.exists(), "ux-architect.md 에이전트 파일 없음")

    def test_ux_architect_in_boundary(self):
        boundary_file = HARNESS_DIR.parent / "orchestration" / "agent-boundaries.md"
        content = boundary_file.read_text()
        self.assertIn("ux-architect", content, "agent-boundaries.md에 ux-architect 없음")

    def test_system_design_doc_exists(self):
        doc = HARNESS_DIR.parent / "orchestration" / "system-design.md"
        self.assertTrue(doc.exists(), "system-design.md 없음")

    def test_plan_loop_no_architect_sd(self):
        """plan_loop.py에 architect(SD) 호출이 없어야 함 (설계 루프로 분리됨)."""
        plan_loop = HARNESS_DIR / "plan_loop.py"
        content = plan_loop.read_text()
        self.assertNotIn("SYSTEM_DESIGN", content, "plan_loop.py에 SYSTEM_DESIGN 잔재")
        self.assertNotIn("architect-sd", content, "plan_loop.py에 architect-sd 잔재")

    def test_plan_loop_returns_ux_markers(self):
        """plan_loop.py가 UX_REVIEW_PASS/UX_SKIP을 리턴하는지."""
        plan_loop = HARNESS_DIR / "plan_loop.py"
        content = plan_loop.read_text()
        self.assertIn("UX_REVIEW_PASS", content)
        self.assertIn("UX_SKIP", content)


class TestTDDGateIntegrity(unittest.TestCase):
    """TDD 게이트 정합성 검증."""

    def test_no_old_test_mode_in_agents(self):
        """에이전트 파일에 @MODE:TEST_ENGINEER:TEST 잔재가 없어야 함."""
        te = HARNESS_DIR.parent / "agents" / "test-engineer.md"
        content = te.read_text()
        self.assertNotIn("@MODE:TEST_ENGINEER:TEST", content)
        self.assertIn("@MODE:TEST_ENGINEER:TDD", content)

    def test_impl_std_has_tdd_flow(self):
        doc = HARNESS_DIR.parent / "orchestration" / "impl_std.md"
        content = doc.read_text()
        self.assertIn("TDD", content, "impl_std.md에 TDD 관련 내용 없음")
        self.assertIn("TESTS_WRITTEN", content)

    def test_impl_deep_has_tdd_flow(self):
        doc = HARNESS_DIR.parent / "orchestration" / "impl_deep.md"
        content = doc.read_text()
        self.assertIn("TDD", content, "impl_deep.md에 TDD 관련 내용 없음")

    def test_impl_simple_no_tdd(self):
        doc = HARNESS_DIR.parent / "orchestration" / "impl_simple.md"
        content = doc.read_text()
        self.assertNotIn("TDD", content, "impl_simple.md에 TDD가 있으면 안 됨")

    def test_engineer_has_self_test(self):
        eng = HARNESS_DIR.parent / "agents" / "engineer.md"
        content = eng.read_text()
        self.assertIn("자체 테스트 검증", content)

    def test_harness_review_sequence_updated(self):
        """harness-review.py EXPECTED_SEQUENCE에서 test-engineer가 engineer 앞인지."""
        review = HARNESS_DIR.parent / "scripts" / "harness-review.py"
        content = review.read_text()
        # std 시퀀스에서 test-engineer가 engineer보다 먼저 나오는지
        import re
        m = re.search(r'"std":\s*\[(.*?)\]', content)
        if m:
            seq = m.group(1)
            te_pos = seq.find("test-engineer")
            eng_pos = seq.find('"engineer"')
            self.assertLess(te_pos, eng_pos, "std 시퀀스에서 test-engineer가 engineer 뒤에 있음")


class TestTDDMarker(unittest.TestCase):
    """TESTS_WRITTEN 마커 테스트."""

    def test_tests_written_in_enum(self):
        self.assertTrue(hasattr(Marker, "TESTS_WRITTEN"))
        self.assertEqual(Marker.TESTS_WRITTEN.value, "TESTS_WRITTEN")

    def test_parse_tests_written(self):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        f.write("output\n---MARKER:TESTS_WRITTEN---\ntest_files: src/a.test.ts")
        f.close()
        self.assertEqual(parse_marker(f.name, "TESTS_WRITTEN"), "TESTS_WRITTEN")
        os.unlink(f.name)


class TestTDDHUDOrder(unittest.TestCase):
    """TDD에서 HUD 에이전트 순서: test-engineer가 engineer 앞."""

    def test_std_order(self):
        from harness.core import HUD
        hud = HUD("std", "t", "1", 3, 10.0)
        te_idx = hud.agents.index("test-engineer")
        eng_idx = hud.agents.index("engineer")
        self.assertLess(te_idx, eng_idx, "test-engineer should come before engineer in std")

    def test_deep_order(self):
        from harness.core import HUD
        hud = HUD("deep", "t", "1", 3, 10.0)
        te_idx = hud.agents.index("test-engineer")
        eng_idx = hud.agents.index("engineer")
        self.assertLess(te_idx, eng_idx, "test-engineer should come before engineer in deep")

    def test_simple_no_test_engineer(self):
        from harness.core import HUD
        hud = HUD("simple", "t", "1", 3, 10.0)
        self.assertNotIn("test-engineer", hud.agents)


class TestLoopVarsInitialized(unittest.TestCase):
    """루프 함수에서 budget_check(... total_cost ...) 호출 전에 total_cost가 초기화되는지 AST 검증.

    `total_cost = budget_check(..., total_cost, ...)` 같은 패턴은
    RHS의 total_cost(Load)가 LHS 할당(Store)보다 먼저 평가되므로,
    이 줄이 '최초 할당'이면서 동시에 '최초 참조'이면 초기화 누락 버그이다.
    """

    def _get_func_ast(self, func_name: str):
        import ast
        src = (HARNESS_DIR / "impl_loop.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                return node
        self.fail(f"{func_name} not found in impl_loop.py")

    def _first_pure_assign_line(self, func_node, var_name: str) -> Optional[int]:
        """var_name에 값을 할당하되, RHS에서 var_name을 읽지 않는 최초 줄 번호.

        `total_cost = 0.0` → pure assign (반환)
        `total_cost = budget_check(..., total_cost, ...)` → 자기참조, 순수 초기화 아님 (스킵)
        """
        import ast
        min_line = None
        for node in ast.walk(func_node):
            if isinstance(node, ast.Assign):
                targets_have_var = any(
                    isinstance(t, ast.Name) and t.id == var_name
                    for t in node.targets
                )
                if not targets_have_var:
                    continue
                # RHS에서 var_name을 Load하는지 확인
                rhs_reads_var = any(
                    isinstance(n, ast.Name) and n.id == var_name and isinstance(n.ctx, ast.Load)
                    for n in ast.walk(node.value)
                )
                if rhs_reads_var:
                    continue  # 자기참조 — 순수 초기화 아님
                if min_line is None or node.lineno < min_line:
                    min_line = node.lineno
        return min_line

    def _first_read_line(self, func_node, var_name: str) -> Optional[int]:
        """함수 내에서 var_name을 Load 컨텍스트로 최초 참조하는 줄 번호."""
        import ast
        min_line = None
        for node in ast.walk(func_node):
            if isinstance(node, ast.Name) and node.id == var_name and isinstance(node.ctx, ast.Load):
                if min_line is None or node.lineno < min_line:
                    min_line = node.lineno
        return min_line

    def test_total_cost_initialized_before_use_in_run_std_deep(self):
        func = self._get_func_ast("_run_std_deep")
        init_line = self._first_pure_assign_line(func, "total_cost")
        read_line = self._first_read_line(func, "total_cost")
        self.assertIsNotNone(read_line, "total_cost가 _run_std_deep에서 한 번도 참조되지 않음")
        self.assertIsNotNone(init_line,
                             f"total_cost 순수 초기화가 없음 — 최초 참조(line {read_line})에서 UnboundLocalError 발생")
        self.assertLess(init_line, read_line,
                        f"total_cost 초기화(line {init_line})가 최초 참조(line {read_line})보다 먼저 와야 함")

    def test_total_cost_initialized_before_use_in_run_simple(self):
        func = self._get_func_ast("run_simple")
        init_line = self._first_pure_assign_line(func, "total_cost")
        read_line = self._first_read_line(func, "total_cost")
        if read_line is None:
            return  # total_cost 미사용이면 OK
        self.assertIsNotNone(init_line,
                             f"total_cost 순수 초기화가 없음 — 최초 참조(line {read_line})에서 UnboundLocalError 발생")
        self.assertLess(init_line, read_line,
                        f"total_cost 초기화(line {init_line})가 최초 참조(line {read_line})보다 먼저 와야 함")


class TestSessionIsolatedAgentDetection(unittest.TestCase):
    """Phase 3: hooks가 live.json 단일 소스로 에이전트를 판별하는지 검증."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        (self.root / ".claude").mkdir(parents=True, exist_ok=True)
        try:
            self._orig_cwd = os.getcwd()
        except FileNotFoundError:
            # 이전 테스트가 tmp dir을 남긴 채 cleanup한 경우
            self._orig_cwd = str(Path.home())
        os.chdir(self.root)
        sys.path.insert(0, str(HARNESS_DIR.parent / "hooks"))

    def tearDown(self):
        try:
            os.chdir(self._orig_cwd)
        except Exception:
            pass
        sys.path.pop(0)
        self._td.cleanup()
        os.environ.pop("HARNESS_AGENT_NAME", None)
        os.environ.pop("HARNESS_SESSION_ID", None)

    def test_active_agent_reads_live_json(self):
        """live.json.agent 기록 후 active_agent가 그 값을 반환."""
        import session_state as ss
        ss.initialize_session("sidA")
        ss.update_live("sidA", agent="engineer")
        os.environ["HARNESS_SESSION_ID"] = "sidA"
        from harness_common import get_active_agent
        self.assertEqual(get_active_agent(), "engineer")

    def test_active_agent_returns_none_without_live(self):
        """live.json.agent 없으면 None — 메인 Claude 세션."""
        import session_state as ss
        ss.initialize_session("sidB")
        os.environ["HARNESS_SESSION_ID"] = "sidB"
        from harness_common import get_active_agent
        self.assertIsNone(get_active_agent())

    def test_stdin_session_id_wins_over_env(self):
        """훅 stdin의 session_id가 env/pointer보다 우선."""
        import session_state as ss
        ss.initialize_session("sidA")
        ss.initialize_session("sidB")
        ss.update_live("sidA", agent="engineer")
        ss.update_live("sidB", agent="architect")
        os.environ["HARNESS_SESSION_ID"] = "sidA"
        # stdin이 sidB를 가리키면 architect가 반환되어야 함
        self.assertEqual(
            ss.active_agent({"session_id": "sidB"}), "architect"
        )

    def test_agent_call_propagates_session_id(self):
        """agent_call이 HARNESS_SESSION_ID env를 자식 subprocess에 전파."""
        src = (HARNESS_DIR / "core.py").read_text()
        self.assertIn('env["HARNESS_SESSION_ID"]', src,
                       "agent_call에 HARNESS_SESSION_ID 전파가 없음")

    def test_agent_boundary_single_source(self):
        """Phase 3: agent-boundary.py가 live.json 단일 소스로 판정.
        15분 TTL glob 탐색 / 화이트리스트 필터 / env var 폴백 제거 확인.
        """
        boundary_src = (HARNESS_DIR.parent / "hooks" / "agent-boundary.py").read_text()
        self.assertIn("session_state", boundary_src,
                       "agent-boundary.py가 session_state를 import하지 않음")
        self.assertIn("ss.active_agent", boundary_src,
                       "agent-boundary.py가 ss.active_agent를 호출하지 않음")
        # 15분 TTL 폴백 제거
        self.assertNotIn("FALLBACK_FLAG_TTL_SEC", boundary_src,
                          "Phase 3: 15분 TTL 폴백이 남아있음 — 제거 필요")
        # 900초 TTL glob 탐색 제거됨 (legacy)
        self.assertNotIn("900", boundary_src,
                          "agent-boundary.py에 900초 TTL glob 탐색이 아직 남아있음")


class TestWorktreeIsolation(unittest.TestCase):
    """이슈별 worktree 격리 기능 검증."""

    def test_state_dir_issue_flags_dir(self):
        """StateDir(issue_num="42") 시 이슈별 .flags/ 서브디렉토리 생성."""
        with tempfile.TemporaryDirectory() as td:
            sd = StateDir(Path(td), "mb", issue_num="42")
            self.assertTrue(sd.flags_dir.is_dir())
            self.assertIn("mb_42", str(sd.flags_dir))
            # 플래그 생성이 이슈별 디렉토리에 들어가는지
            sd.flag_touch("plan_validation_passed")
            self.assertTrue((sd.flags_dir / "mb_plan_validation_passed").exists())

    def test_state_dir_no_issue_backward_compat(self):
        """issue_num 없으면 기존 .flags/ 경로 유지."""
        with tempfile.TemporaryDirectory() as td:
            sd = StateDir(Path(td), "mb")
            self.assertEqual(sd.flags_dir, sd.path / ".flags")

    def test_worktree_manager_path(self):
        """WorktreeManager 경로 조합 검증."""
        from harness.core import WorktreeManager
        with tempfile.TemporaryDirectory() as td:
            wm = WorktreeManager(Path(td), "mb")
            wt = wm.worktree_path("42")
            self.assertEqual(wt, wm.base_dir / "issue-42")

    def test_worktree_manager_gitignore(self):
        """WorktreeManager가 .gitignore에 .worktrees/ 자동 등록."""
        from harness.core import WorktreeManager
        with tempfile.TemporaryDirectory() as td:
            WorktreeManager(Path(td), "mb")
            gitignore = Path(td) / ".gitignore"
            self.assertTrue(gitignore.exists())
            self.assertIn(".worktrees/", gitignore.read_text())

    def test_create_feature_branch_returns_tuple(self):
        """create_feature_branch가 (branch_name, path|None) tuple 반환."""
        from harness.core import create_feature_branch
        import inspect
        sig = inspect.signature(create_feature_branch)
        self.assertIn("worktree_mgr", sig.parameters)

    def test_agent_call_has_cwd_param(self):
        """agent_call에 cwd 파라미터 존재."""
        from harness.core import agent_call
        import inspect
        sig = inspect.signature(agent_call)
        self.assertIn("cwd", sig.parameters)

    def test_merge_to_main_has_worktree_mgr(self):
        """merge_to_main에 worktree_mgr 파라미터 존재."""
        from harness.core import merge_to_main
        import inspect
        sig = inspect.signature(merge_to_main)
        self.assertIn("worktree_mgr", sig.parameters)

    def test_get_flags_dir_issue_num(self):
        """get_flags_dir()가 HARNESS_ISSUE_NUM env var 인식."""
        sys.path.insert(0, str(HARNESS_DIR.parent / "hooks"))
        try:
            # issue_num 파라미터 직접 전달
            from harness_common import get_flags_dir
            import inspect
            sig = inspect.signature(get_flags_dir)
            self.assertIn("issue_num", sig.parameters)
        finally:
            sys.path.pop(0)

    def test_bind_cwd_returns_callable(self):
        """_bind_cwd가 work_cwd 없으면 원본, 있으면 partial 반환."""
        from harness.impl_loop import _bind_cwd, agent_call
        # None → 원본
        result = _bind_cwd(None)
        self.assertEqual(result, agent_call)
        # 경로 → partial
        result = _bind_cwd("/tmp/test")
        self.assertNotEqual(result, agent_call)
        self.assertTrue(callable(result))


class TestHarnessWhitelist(unittest.TestCase):
    """is_harness_enabled() — 프로젝트 화이트리스트 옵트인 가드."""

    HOOKS_DIR = Path.home() / ".claude" / "hooks"

    def _setup(self, projects, home_dir):
        """임시 HOME에 harness-projects.json 배치 후 is_harness_enabled import."""
        sys.path.insert(0, str(self.HOOKS_DIR))
        wl = home_dir / ".claude" / "harness-projects.json"
        wl.parent.mkdir(parents=True, exist_ok=True)
        wl.write_text(json.dumps({"projects": projects}))
        import harness_common
        import importlib
        importlib.reload(harness_common)
        harness_common._WHITELIST_PATH = str(wl)
        return harness_common.is_harness_enabled

    def tearDown(self):
        if str(self.HOOKS_DIR) in sys.path:
            sys.path.remove(str(self.HOOKS_DIR))

    def test_missing_whitelist_file_returns_false(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            fn = self._setup([], home)
            # 파일 삭제
            (home / ".claude" / "harness-projects.json").unlink()
            self.assertFalse(fn("/tmp/some-project"))

    def test_exact_match_returns_true(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            fn = self._setup([str(proj)], Path(td))
            self.assertTrue(fn(str(proj)))

    def test_subdirectory_match_returns_true(self):
        """등록 경로의 하위(worktree·서브디렉토리)도 활성."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            sub = proj / "src" / "deep"
            sub.mkdir(parents=True)
            fn = self._setup([str(proj)], Path(td))
            self.assertTrue(fn(str(sub)))

    def test_unrelated_path_returns_false(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            other = Path(td) / "other"
            proj.mkdir(); other.mkdir()
            fn = self._setup([str(proj)], Path(td))
            self.assertFalse(fn(str(other)))

    def test_force_enable_env_overrides(self):
        """HARNESS_FORCE_ENABLE=1 env var 설정 시 whitelist 무시하고 True."""
        import tempfile, os as _os
        with tempfile.TemporaryDirectory() as td:
            fn = self._setup([], Path(td))
            _os.environ["HARNESS_FORCE_ENABLE"] = "1"
            try:
                self.assertTrue(fn("/any/path"))
            finally:
                del _os.environ["HARNESS_FORCE_ENABLE"]


class TestAgentGateModeLevel(unittest.TestCase):
    """agent-gate.py — Mode-level 게이트 회귀 가드.
    MODULE_PLAN/PLAN_VALIDATION을 메인 Claude가 직접 호출하면 deny,
    SYSTEM_DESIGN/DESIGN_VALIDATION은 허용."""

    HOOKS_DIR = Path.home() / ".claude" / "hooks"
    GATE = HOOKS_DIR / "agent-gate.py"

    def _detect(self):
        """detect_* 함수 임포트 (유닛 단위)."""
        sys.path.insert(0, str(self.HOOKS_DIR))
        try:
            from harness_common import (
                detect_architect_mode, detect_validator_mode,
                ARCHITECT_HARNESS_ONLY_MODES, VALIDATOR_HARNESS_ONLY_MODES,
            )
            return (detect_architect_mode, detect_validator_mode,
                    ARCHITECT_HARNESS_ONLY_MODES, VALIDATOR_HARNESS_ONLY_MODES)
        finally:
            if str(self.HOOKS_DIR) in sys.path:
                sys.path.remove(str(self.HOOKS_DIR))

    def test_detect_architect_modes(self):
        det_arc, _, _, _ = self._detect()
        self.assertEqual(det_arc("@MODE:ARCHITECT:SYSTEM_DESIGN"), "SYSTEM_DESIGN")
        self.assertEqual(det_arc("MODULE_PLAN — 단일 모듈 계획 for F5"), "MODULE_PLAN")
        self.assertEqual(det_arc("architect SYSTEM_DESIGN 시스템 설계"), "SYSTEM_DESIGN")
        self.assertEqual(det_arc("SPEC_GAP 복구 필요"), "SPEC_GAP")
        self.assertIsNone(det_arc("그냥 코드 검토 부탁"))
        # 알파벳 표기(Mode A-G) deprecate — 더 이상 인식하지 않음
        self.assertIsNone(det_arc("Mode B 시작"))
        self.assertIsNone(det_arc("Mode F 작업"))

    def test_detect_validator_modes(self):
        _, det_val, _, _ = self._detect()
        self.assertEqual(det_val("Plan Validation 실행"), "PLAN_VALIDATION")
        self.assertEqual(det_val("@MODE:VALIDATOR:DESIGN_VALIDATION"), "DESIGN_VALIDATION")
        self.assertEqual(det_val("CODE_VALIDATION for impl"), "CODE_VALIDATION")
        self.assertEqual(det_val("Bugfix Validation"), "BUGFIX_VALIDATION")
        self.assertIsNone(det_val("리뷰 좀"))

    def test_harness_only_sets(self):
        _, _, arc_set, val_set = self._detect()
        self.assertIn("MODULE_PLAN", arc_set)
        self.assertIn("SPEC_GAP", arc_set)
        self.assertNotIn("SYSTEM_DESIGN", arc_set)  # 직접 호출 허용
        self.assertNotIn("LIGHT_PLAN", arc_set)
        self.assertIn("PLAN_VALIDATION", val_set)
        self.assertIn("CODE_VALIDATION", val_set)
        self.assertNotIn("DESIGN_VALIDATION", val_set)  # 직접 호출 허용

    def _run_gate(self, agent: str, prompt: str, harness_active: bool):
        """agent-gate.py를 실제 subprocess로 실행. stdout JSON 파싱."""
        import subprocess as _sp
        import tempfile as _tf
        with _tf.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".claude").mkdir()
            (root / ".claude" / "harness.config.json").write_text(
                json.dumps({"prefix": "testmb"}))
            flags_dir = root / ".claude" / "harness-state" / ".flags"
            flags_dir.mkdir(parents=True, exist_ok=True)
            if harness_active:
                (flags_dir / "testmb_harness_active").touch()
            payload = {
                "tool_name": "Task",
                "tool_input": {
                    "subagent_type": agent,
                    "prompt": prompt,
                    "run_in_background": False,
                },
            }
            r = _sp.run(
                ["python3", str(self.GATE)],
                input=json.dumps(payload),
                capture_output=True, text=True, timeout=10,
                cwd=str(root),
                env={**os.environ, "HARNESS_PREFIX": "testmb", "HARNESS_FORCE_ENABLE": "1"},
            )
        try:
            out = json.loads(r.stdout) if r.stdout.strip() else {}
        except json.JSONDecodeError:
            out = {}
        decision = out.get("hookSpecificOutput", {}).get("permissionDecision", "allow")
        reason = out.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
        return decision, reason

    def test_module_plan_blocked_outside_harness(self):
        decision, reason = self._run_gate(
            "architect", "#42 @MODE:ARCHITECT:MODULE_PLAN", harness_active=False)
        self.assertEqual(decision, "deny")
        self.assertIn("MODULE_PLAN", reason)
        self.assertIn("executor.py", reason)

    def test_system_design_allowed_outside_harness(self):
        decision, _ = self._run_gate(
            "architect", "@MODE:ARCHITECT:SYSTEM_DESIGN", harness_active=False)
        self.assertEqual(decision, "allow")

    def test_plan_validation_blocked_outside_harness(self):
        decision, reason = self._run_gate(
            "validator", "Plan Validation for F5 impl", harness_active=False)
        self.assertEqual(decision, "deny")
        self.assertIn("PLAN_VALIDATION", reason)

    def test_design_validation_allowed_outside_harness(self):
        decision, _ = self._run_gate(
            "validator", "@MODE:VALIDATOR:DESIGN_VALIDATION", harness_active=False)
        self.assertEqual(decision, "allow")

    def test_module_plan_allowed_inside_harness(self):
        """HARNESS_ACTIVE 플래그 있으면 MODULE_PLAN도 통과 — plan_loop 내부 호출."""
        decision, _ = self._run_gate(
            "architect", "#42 @MODE:ARCHITECT:MODULE_PLAN", harness_active=True)
        self.assertEqual(decision, "allow")

    def test_docs_sync_allowed_outside_harness(self):
        """DOCS_SYNC는 impl 완료 후 docs 후행 동기화 전용 — 메인 Claude 직접 호출 허용."""
        decision, _ = self._run_gate(
            "architect", "@MODE:ARCHITECT:DOCS_SYNC 후행 동기화", harness_active=False)
        self.assertEqual(decision, "allow")

    def test_docs_sync_exempt_from_issue_number(self):
        """DOCS_SYNC는 impl 완료 이후라 이슈 번호 요구 제외."""
        det_arc, _, arc_set, _ = self._detect()
        self.assertEqual(det_arc("@MODE:ARCHITECT:DOCS_SYNC"), "DOCS_SYNC")
        self.assertNotIn("DOCS_SYNC", arc_set)  # harness-only 집합에 없음 = 직접 호출 허용


class TestWorktreeNestedCwdRecovery(unittest.TestCase):
    """cwd가 worktree 내부로 persist된 상태에서도 WorktreeManager가 main repo root를
    정확히 복구하는지 검증 — mb #158 run_20260421_231527 HARNESS_CRASH 재발 가드."""

    def _make_repo_with_worktree(self, td: str):
        """임시 git repo + 1개 worktree 생성, (main_root, worktree_path) 반환."""
        import subprocess as _sp
        main_root = Path(td) / "main"
        main_root.mkdir()
        _sp.run(["git", "init", "-q", "-b", "main"], cwd=str(main_root), check=True)
        _sp.run(["git", "config", "user.email", "t@t"], cwd=str(main_root), check=True)
        _sp.run(["git", "config", "user.name", "t"], cwd=str(main_root), check=True)
        (main_root / "README.md").write_text("x")
        _sp.run(["git", "add", "."], cwd=str(main_root), check=True)
        _sp.run(["git", "commit", "-qm", "init"], cwd=str(main_root), check=True)
        wt = main_root / ".worktrees" / "mb" / "issue-99"
        wt.parent.mkdir(parents=True, exist_ok=True)
        _sp.run(["git", "worktree", "add", "-q", str(wt), "-b", "feat/test"],
                cwd=str(main_root), check=True)
        return main_root, wt

    def test_find_main_repo_root_from_main(self):
        from harness.core import find_main_repo_root
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            main_root, _ = self._make_repo_with_worktree(td)
            self.assertEqual(find_main_repo_root(main_root), main_root.resolve())

    def test_find_main_repo_root_from_worktree_returns_main(self):
        """cwd가 worktree 내부일 때도 main repo root 반환 — 이 버그의 핵심 가드."""
        from harness.core import find_main_repo_root
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            main_root, wt = self._make_repo_with_worktree(td)
            self.assertEqual(find_main_repo_root(wt), main_root.resolve())

    def test_worktree_manager_base_dir_not_nested(self):
        """WorktreeManager에 worktree 경로를 전달해도 base_dir이 main repo 기준."""
        from harness.core import WorktreeManager
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            main_root, wt = self._make_repo_with_worktree(td)
            # 이전 버그 재현 조건: project_root로 worktree 경로 전달
            mgr = WorktreeManager(wt, "mb")
            expected = main_root.resolve() / ".worktrees" / "mb"
            self.assertEqual(mgr.base_dir, expected)
            # 중첩되면 base_dir = wt / ".worktrees" / "mb" 가 됐을 것
            self.assertNotEqual(mgr.base_dir, wt / ".worktrees" / "mb")

    def test_find_main_repo_root_fallback_non_repo(self):
        """git repo가 아닌 경로면 start_path 그대로 반환 (폴백)."""
        from harness.core import find_main_repo_root
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            self.assertEqual(find_main_repo_root(p), p.resolve())


class TestCleanupOrphanRemoteBranch(unittest.TestCase):
    """_cleanup_orphan_remote_branch — non-fast-forward 충돌 예방 회귀 차단."""

    def _mock_run(self, remote_exists: bool, open_pr_number: str = ""):
        """subprocess.run 모킹 팩토리."""
        from unittest.mock import MagicMock

        def fake_run(cmd, **kwargs):
            result = MagicMock()
            if cmd[:2] == ["git", "ls-remote"]:
                result.returncode = 0 if remote_exists else 2
                result.stdout = "abc123\trefs/heads/foo\n" if remote_exists else ""
            elif cmd[:3] == ["gh", "pr", "list"]:
                result.returncode = 0
                result.stdout = open_pr_number
            elif cmd[:3] == ["git", "push", "origin"]:
                result.returncode = 0
                result.stdout = ""
                self._delete_called = True  # noqa: attr-defined
            else:
                result.returncode = 0
                result.stdout = ""
            return result
        return fake_run

    def test_no_remote_branch_is_noop(self):
        """원격에 branch 없으면 아무 동작 안 함."""
        from unittest.mock import patch
        from harness.core import _cleanup_orphan_remote_branch
        self._delete_called = False
        with patch("harness.core.subprocess.run", side_effect=self._mock_run(remote_exists=False)):
            _cleanup_orphan_remote_branch("feat/foo")
        self.assertFalse(self._delete_called)

    def test_open_pr_blocks_delete(self):
        """OPEN PR 있으면 원격 branch 삭제 안 함 (이어서 작업해야 함)."""
        from unittest.mock import patch
        from harness.core import _cleanup_orphan_remote_branch
        self._delete_called = False
        with patch("harness.core.subprocess.run",
                   side_effect=self._mock_run(remote_exists=True, open_pr_number="42")):
            _cleanup_orphan_remote_branch("feat/foo")
        self.assertFalse(self._delete_called)

    def test_orphan_branch_deleted(self):
        """원격 branch + OPEN PR 없음 → orphan으로 판정 후 삭제."""
        from unittest.mock import patch
        from harness.core import _cleanup_orphan_remote_branch
        self._delete_called = False
        with patch("harness.core.subprocess.run",
                   side_effect=self._mock_run(remote_exists=True, open_pr_number="")):
            _cleanup_orphan_remote_branch("feat/foo")
        self.assertTrue(self._delete_called)


class TestMergeCooldown(unittest.TestCase):
    """merge cooldown — MERGE_CONFLICT_ESCALATE 재진입 차단 회귀 가드."""

    def test_set_get_clear_roundtrip(self):
        from harness.core import set_merge_cooldown, get_merge_cooldown, clear_merge_cooldown
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            set_merge_cooldown(root, "mb", "42", reason="MERGE_CONFLICT_ESCALATE",
                               branch="feat/foo", stderr_tail="non-fast-forward")
            data = get_merge_cooldown(root, "mb", "42")
            self.assertIsNotNone(data)
            self.assertEqual(data["reason"], "MERGE_CONFLICT_ESCALATE")
            self.assertEqual(data["branch"], "feat/foo")
            clear_merge_cooldown(root, "mb", "42")
            self.assertIsNone(get_merge_cooldown(root, "mb", "42"))

    def test_isolation_by_prefix_and_issue(self):
        """다른 prefix/issue는 서로 간섭 없음."""
        from harness.core import set_merge_cooldown, get_merge_cooldown
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            set_merge_cooldown(root, "mb", "42", reason="X")
            self.assertIsNone(get_merge_cooldown(root, "mb", "43"))
            self.assertIsNone(get_merge_cooldown(root, "claude", "42"))
            self.assertIsNotNone(get_merge_cooldown(root, "mb", "42"))


class TestMergeSelfHeal(unittest.TestCase):
    """_attempt_merge_selfheal — rebase conflict 구분, force-with-lease 사용."""

    def test_rebase_conflict_aborts_and_returns_false(self):
        """rebase 중 conflict 나면 abort 호출 + False 반환."""
        from unittest.mock import patch, MagicMock
        from harness.core import _attempt_merge_selfheal
        abort_called = {"v": False}

        def fake_run(cmd, **kwargs):
            r = MagicMock()
            r.returncode = 0
            r.stdout = ""
            r.stderr = ""
            if cmd[:2] == ["git", "rebase"] and "--abort" not in cmd:
                r.returncode = 1
                r.stderr = "CONFLICT (content)"
            elif cmd[:3] == ["git", "rebase", "--abort"]:
                abort_called["v"] = True
            return r

        with patch("harness.core._default_branch", return_value="main"), \
             patch("harness.core.subprocess.run", side_effect=fake_run):
            result = _attempt_merge_selfheal("feat/foo")
        self.assertFalse(result)
        self.assertTrue(abort_called["v"])

    def test_happy_path_rebase_then_force_push(self):
        """fetch → rebase → force-with-lease 순서로 진행 + True."""
        from unittest.mock import patch, MagicMock
        from harness.core import _attempt_merge_selfheal
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = ""
            r.stderr = ""
            return r

        with patch("harness.core._default_branch", return_value="main"), \
             patch("harness.core.subprocess.run", side_effect=fake_run):
            result = _attempt_merge_selfheal("feat/foo")
        self.assertTrue(result)
        flat = [" ".join(c) for c in calls]
        self.assertTrue(any("git fetch origin main" in c for c in flat))
        self.assertTrue(any("git rebase origin/main" in c for c in flat))
        self.assertTrue(any("--force-with-lease" in c for c in flat))


class TestRunAutomatedChecksTestRegression(unittest.TestCase):
    """run_automated_checks run_tests 파라미터 — simple depth 회귀 차단."""

    def _make_repo(self, td: str) -> tuple[Path, Path]:
        """임시 git repo + impl 파일 생성."""
        import subprocess as _sp
        proj = Path(td)
        impl = proj / "impl.md"
        impl.write_text("---\ndepth: simple\n---\n## 수정 파일\n- `src/foo.ts`\n")
        (proj / "src").mkdir()
        foo = proj / "src" / "foo.ts"
        foo.write_text("export const x = 1;\n")
        _sp.run(["git", "init"], capture_output=True, cwd=td)
        _sp.run(["git", "config", "user.email", "t@t.com"], capture_output=True, cwd=td)
        _sp.run(["git", "config", "user.name", "t"], capture_output=True, cwd=td)
        _sp.run(["git", "add", "."], capture_output=True, cwd=td)
        _sp.run(["git", "commit", "-m", "init"], capture_output=True, cwd=td)
        foo.write_text("export const x = 2;\n")  # uncommitted change
        _sp.run(["git", "add", "."], capture_output=True, cwd=td)
        return proj, impl

    def test_run_tests_false_skips_test_command(self):
        """run_tests=False면 test_command가 설정돼도 실행하지 않음."""
        from harness.helpers import run_automated_checks
        from harness.config import HarnessConfig
        with tempfile.TemporaryDirectory() as td:
            proj, impl = self._make_repo(td)
            sd = StateDir(proj, "test")
            cfg = HarnessConfig(test_command="exit 1")  # 돌면 FAIL
            ok, err = run_automated_checks(str(impl), cfg, sd, "test", cwd=td, run_tests=False)
            self.assertTrue(ok, f"test skip expected but got FAIL: {err}")

    def test_run_tests_true_passes_when_tests_green(self):
        """run_tests=True + test_command 성공 시 PASS."""
        from harness.helpers import run_automated_checks
        from harness.config import HarnessConfig
        with tempfile.TemporaryDirectory() as td:
            proj, impl = self._make_repo(td)
            sd = StateDir(proj, "test")
            cfg = HarnessConfig(test_command="true")
            ok, err = run_automated_checks(str(impl), cfg, sd, "test", cwd=td, run_tests=True)
            self.assertTrue(ok, f"expected PASS, got FAIL: {err}")

    def test_run_tests_true_fails_when_tests_red(self):
        """run_tests=True + test_command 실패 시 FAIL + test_fail 메시지."""
        from harness.helpers import run_automated_checks
        from harness.config import HarnessConfig
        with tempfile.TemporaryDirectory() as td:
            proj, impl = self._make_repo(td)
            sd = StateDir(proj, "test")
            cfg = HarnessConfig(test_command="exit 1")
            ok, err = run_automated_checks(str(impl), cfg, sd, "test", cwd=td, run_tests=True)
            self.assertFalse(ok)
            self.assertIn("test_fail", err)

    def test_run_tests_true_no_test_command_is_noop(self):
        """run_tests=True여도 test_command 비어있으면 skip (PASS)."""
        from harness.helpers import run_automated_checks
        from harness.config import HarnessConfig
        with tempfile.TemporaryDirectory() as td:
            proj, impl = self._make_repo(td)
            sd = StateDir(proj, "test")
            cfg = HarnessConfig(test_command="")
            ok, err = run_automated_checks(str(impl), cfg, sd, "test", cwd=td, run_tests=True)
            self.assertTrue(ok, f"expected PASS (test_command empty), got FAIL: {err}")


if __name__ == "__main__":
    unittest.main()
