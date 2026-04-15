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

# 테스트 대상 패키지 경로 설정
HARNESS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HARNESS_DIR.parent))

from harness.config import HarnessConfig, load_config
from harness.core import (
    Flag, Marker, StateDir, RunLogger,
    parse_marker, detect_depth, hlog, kill_check,
    build_smart_context,
)
from harness.helpers import append_failure, append_success, budget_check


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
                 patch("harness.impl_loop.create_feature_branch", return_value="feat/test-1"), \
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

            # HUD JSON 파일 생성 확인
            hud_path = sd.path / "test_hud.json"
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


if __name__ == "__main__":
    unittest.main()
