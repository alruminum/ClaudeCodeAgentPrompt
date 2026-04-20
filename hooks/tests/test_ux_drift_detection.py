"""
test_ux_drift_detection.py — post-commit-scan.sh 의 UX 영향 파일 감지 로직 검증.

실제 셸 스크립트를 서브프로세스로 돌려 플래그 생성 여부를 확인한다.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent
SCAN_SCRIPT = HOOKS_DIR / "post-commit-scan.sh"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=10,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    )


def _run_scan(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCAN_SCRIPT)],
        cwd=str(cwd), capture_output=True, text=True, timeout=10,
    )


class UXDriftDetectionTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        (self.root / ".claude").mkdir(parents=True, exist_ok=True)
        (self.root / ".claude" / "harness.config.json").write_text(
            '{"prefix": "test", "default_branch": "main"}'
        )
        (self.root / ".claude" / "harness-state").mkdir(parents=True, exist_ok=True)
        (self.root / "docs").mkdir(parents=True, exist_ok=True)
        _git(self.root, "init", "-q", "-b", "main")
        # 초기 커밋 — scan은 HEAD~1..HEAD diff 를 보므로 baseline 필요
        (self.root / "README.md").write_text("init")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-qm", "init")

    def tearDown(self):
        self._td.cleanup()

    def _commit_change(self, relpath: str, content: str = "x"):
        target = self.root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-qm", f"change {relpath}")

    def _flag_path(self) -> Path:
        # 최상위 — `.flags/` 서브디렉토리는 migrate_legacy_flags 가 비우므로 사용 안 함
        return (self.root / ".claude" / "harness-state"
                / "test_ux_flow_drift")

    def test_screen_file_change_with_ux_flow_creates_flag(self):
        """*Screen.tsx 변경 + ux-flow.md 존재 → 플래그 생성."""
        (self.root / "docs" / "ux-flow.md").write_text("# UX Flow\n## S01\n")
        _git(self.root, "add", "docs/ux-flow.md")
        _git(self.root, "commit", "-qm", "add ux-flow")
        self._commit_change("src/screens/LoginScreen.tsx", "export const X = 1")
        result = _run_scan(self.root)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue(self._flag_path().exists(),
                        msg=f"flag missing. scan stdout={result.stdout}")
        content = self._flag_path().read_text()
        self.assertIn("LoginScreen.tsx", content)

    def test_routes_dir_change_creates_flag(self):
        """src/routes/** 변경 → 플래그 생성."""
        (self.root / "docs" / "ux-flow.md").write_text("# UX Flow")
        _git(self.root, "add", "docs/ux-flow.md")
        _git(self.root, "commit", "-qm", "add ux-flow")
        self._commit_change("src/routes/index.tsx", "export {}")
        _run_scan(self.root)
        self.assertTrue(self._flag_path().exists())

    def test_non_ux_file_no_flag(self):
        """일반 util 변경 → 플래그 생성 안 됨."""
        (self.root / "docs" / "ux-flow.md").write_text("# UX Flow")
        _git(self.root, "add", "docs/ux-flow.md")
        _git(self.root, "commit", "-qm", "add ux-flow")
        self._commit_change("src/lib/util.ts", "export const x = 1")
        _run_scan(self.root)
        self.assertFalse(self._flag_path().exists(),
                         "일반 유틸 변경은 ux 플래그를 만들면 안 됨")

    def test_no_ux_flow_doc_no_flag(self):
        """docs/ux-flow.md 없으면 screen 변경이어도 플래그 스킵."""
        # ux-flow.md 생성하지 않음
        self._commit_change("src/screens/HomeScreen.tsx", "export const X = 1")
        _run_scan(self.root)
        self.assertFalse(self._flag_path().exists())

    def test_flag_content_is_grep_friendly(self):
        """플래그 파일 내용: 주석(#) + 변경 파일 경로. 주석 제외하면 파일 목록만."""
        (self.root / "docs" / "ux-flow.md").write_text("# UX Flow")
        _git(self.root, "add", "docs/ux-flow.md")
        _git(self.root, "commit", "-qm", "add ux-flow")
        self._commit_change("src/screens/A.Screen.tsx", "a")
        _run_scan(self.root)
        lines = self._flag_path().read_text().splitlines()
        non_comment = [l for l in lines if l.strip() and not l.lstrip().startswith("#")]
        self.assertEqual(len(non_comment), 1)
        self.assertIn("Screen.tsx", non_comment[0])


if __name__ == "__main__":
    unittest.main()
