"""
test_session_start_ux_drift.py — SessionStart 훅의 ux-flow drift 알림 로직 검증.

- 드리프트 플래그만 있으면 "감지, /ux-sync 로 현행화" 안내
- 센티널도 함께 있으면 "다른 세션에서 진행 중" 안내로 변경
- 플래그 없으면 해당 안내 출력 안 함
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


def _run_session_start(cwd: Path):
    """harness-session-start.py 를 서브프로세스로 실행 (auto 모드)."""
    script = HOOKS_DIR / "harness-session-start.py"
    env = os.environ.copy()
    env["HARNESS_FORCE_ENABLE"] = "1"  # 테스트: 화이트리스트 가드 우회
    env.pop("HARNESS_SESSION_ID", None)
    proc = subprocess.run(
        ["python3", str(script), "auto"],
        capture_output=True, text=True, cwd=str(cwd), env=env, timeout=10,
        input="",
    )
    return proc.returncode, proc.stdout, proc.stderr


def _additional_context(stdout: str) -> str:
    """SessionStart hookSpecificOutput 에서 additionalContext 추출."""
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
            return data.get("hookSpecificOutput", {}).get("additionalContext", "")
        except json.JSONDecodeError:
            continue
    return stdout


class UXDriftNotificationTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        (self.root / ".claude").mkdir(parents=True, exist_ok=True)
        (self.root / ".claude" / "harness.config.json").write_text(
            '{"prefix": "test", "default_branch": "main"}'
        )
        (self.root / ".claude" / "harness-state").mkdir(parents=True, exist_ok=True)
        # 플래그는 STATE_DIR 최상위에 저장됨 (`.flags/` 서브디렉토리는 migrate_legacy_flags 가 비움)
        self.flags_dir = self.root / ".claude" / "harness-state"
        # git repo 아니어도 session-start 는 동작 (git log 실패는 예외 처리됨)

    def tearDown(self):
        self._td.cleanup()

    def _write_drift_flag(self, files):
        path = self.flags_dir / "test_ux_flow_drift"
        path.write_text("# UX drift\n" + "\n".join(files))
        return path

    def _write_sentinel(self):
        path = self.flags_dir / "test_ux_sync_in_progress"
        path.write_text("# /ux-sync started at 2026-04-20T00:00:00Z\n")
        return path

    def test_drift_only_shows_sync_prompt(self):
        self._write_drift_flag(["src/screens/LoginScreen.tsx",
                                "src/screens/HomeScreen.tsx"])
        rc, out, err = _run_session_start(self.root)
        self.assertEqual(rc, 0, msg=err)
        ctx = _additional_context(out)
        self.assertIn("드리프트 감지", ctx)
        self.assertIn("/ux-sync", ctx)
        self.assertNotIn("진행 중", ctx)

    def test_drift_plus_sentinel_shows_in_progress(self):
        self._write_drift_flag(["src/screens/LoginScreen.tsx"])
        self._write_sentinel()
        rc, out, err = _run_session_start(self.root)
        self.assertEqual(rc, 0, msg=err)
        ctx = _additional_context(out)
        self.assertIn("실행 중", ctx)
        self.assertIn("/ux-sync", ctx)
        # 중복 알림 방지 — 센티널 있으면 "드리프트 감지" 메시지는 안 나감
        self.assertNotIn("드리프트 감지", ctx)

    def test_no_flag_no_notification(self):
        rc, out, err = _run_session_start(self.root)
        self.assertEqual(rc, 0, msg=err)
        ctx = _additional_context(out)
        self.assertNotIn("드리프트", ctx)
        self.assertNotIn("/ux-sync", ctx)

    def test_empty_drift_file_no_notification(self):
        """주석만 있고 변경 파일 목록이 비어 있으면 알림 없음."""
        path = self.flags_dir / "test_ux_flow_drift"
        path.write_text("# UX drift detected\n# nothing below\n")
        rc, out, err = _run_session_start(self.root)
        self.assertEqual(rc, 0, msg=err)
        ctx = _additional_context(out)
        self.assertNotIn("드리프트 감지", ctx)


if __name__ == "__main__":
    unittest.main()
