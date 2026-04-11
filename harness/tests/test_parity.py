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
from harness.helpers import append_failure, budget_check


class TestFlagEnumMatchesBash(unittest.TestCase):
    def test_flag_enum_matches_bash(self):
        """Flag enum 값이 flags.sh와 일치하는지 확인."""
        flags_sh = HARNESS_DIR / "flags.sh"
        content = flags_sh.read_text()
        sh_flags = dict(re.findall(r'FLAG_(\w+)="(\w+)"', content))
        for name, val in sh_flags.items():
            with self.subTest(flag=name):
                self.assertTrue(hasattr(Flag, name), f"Flag.{name} 누락")
                self.assertEqual(getattr(Flag, name).value, val)


class TestMarkerEnumMatchesBash(unittest.TestCase):
    def test_marker_enum_matches_bash(self):
        """Marker enum 값이 markers.sh KNOWN_MARKERS와 일치하는지 확인."""
        markers_sh = HARNESS_DIR / "markers.sh"
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


if __name__ == "__main__":
    unittest.main()
