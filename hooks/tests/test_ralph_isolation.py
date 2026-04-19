"""test_ralph_isolation.py — ralph-loop claim 탈취 차단 (T1) 검증.

오피셜 ralph-loop stop-hook은 state 파일의 frontmatter `session_id:` 필드와
hook session_id를 비교해 다르면 exit 0 (격리). 빈 값이면 fall-through.

ralph-session-stop.py가 root cause를 우회한다 — live.json.skill로 시작자를
식별해 state.session_id를 박는다.

Run: python3 -m unittest discover -s ~/.claude/hooks/tests -p 'test_ralph_isolation.py' -v
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HOOKS_DIR))

import session_state as ss  # noqa: E402

PYTHON = sys.executable
HOOK = HOOKS_DIR / "ralph-session-stop.py"

STATE_REL = ".claude/ralph-loop.local.md"


def _make_project(td: Path) -> Path:
    (td / ".claude").mkdir(parents=True, exist_ok=True)
    return td


def _make_state(root: Path, frontmatter_extra: str = "") -> Path:
    """오피셜 setup-ralph-loop.sh가 만드는 형태와 동일한 state 파일 생성."""
    state = root / STATE_REL
    state.parent.mkdir(parents=True, exist_ok=True)
    fm = "iteration: 1\nmax_iterations: 5\nsession_id: \n" + frontmatter_extra
    state.write_text(f"---\n{fm}---\n\nRalph loop activated\n\nPROMPT BODY\n")
    return state


def _parse_state_session_id(content: str) -> str:
    m = re.search(r"^session_id:[ \t]*(\S*)[ \t]*$", content, flags=re.MULTILINE)
    return m.group(1) if m else ""


def _run_hook(payload: dict, cwd: Path) -> tuple[str, str, int]:
    here = os.getcwd()
    os.chdir(cwd)
    try:
        p = subprocess.run(
            [PYTHON, str(HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return p.stdout, p.stderr, p.returncode
    finally:
        os.chdir(here)


class RalphIsolationTests(unittest.TestCase):

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = _make_project(Path(self._td.name))
        ss.ensure_skeleton(self.root)

    def tearDown(self):
        self._td.cleanup()

    # ── Case A: state.session_id 비어있음 ───────────────────────────────

    def test_initiator_first_fire_claims_self(self):
        """시작 세션이 첫 Stop fire하면 자기 SID를 박는다."""
        ss.set_active_skill("sessA", "ralph-loop:ralph-loop", "heavy",
                            project_root=self.root)
        state = _make_state(self.root)
        out, err, rc = _run_hook({"session_id": "sessA"}, self.root)
        self.assertEqual(rc, 0, err)
        recorded = _parse_state_session_id(state.read_text())
        self.assertEqual(recorded, "sessA")

    def test_non_initiator_first_fire_writes_placeholder(self):
        """비시작 세션이 첫 fire하면 placeholder 박아 fall-through 차단."""
        # sessB는 ralph 시작자 아님 (live.json.skill 없거나 다른 스킬)
        state = _make_state(self.root)
        out, err, rc = _run_hook({"session_id": "sessB"}, self.root)
        self.assertEqual(rc, 0, err)
        recorded = _parse_state_session_id(state.read_text())
        self.assertTrue(
            recorded.startswith("__pending_") and recorded.endswith("__"),
            f"placeholder 기대: {recorded}"
        )
        # 실제 SID는 박히지 않음 (claim 안 함)
        self.assertNotEqual(recorded, "sessB")

    # ── Case B: placeholder 박혀있음 ─────────────────────────────────────

    def test_initiator_promotes_placeholder(self):
        """시작 세션이 placeholder를 보면 자기 SID로 교체."""
        ss.set_active_skill("sessA", "ralph-loop:ralph-loop", "heavy",
                            project_root=self.root)
        state = _make_state(self.root)
        # 먼저 다른 세션이 placeholder 박았다고 가정
        content = state.read_text().replace(
            "session_id: \n", "session_id: __pending_abc12345__\n"
        )
        state.write_text(content)
        out, err, rc = _run_hook({"session_id": "sessA"}, self.root)
        self.assertEqual(rc, 0, err)
        recorded = _parse_state_session_id(state.read_text())
        self.assertEqual(recorded, "sessA", "placeholder가 시작자 SID로 교체돼야 함")

    def test_non_initiator_keeps_placeholder(self):
        """비시작 세션은 placeholder 유지 (자기 SID로 덮지 않음)."""
        state = _make_state(self.root)
        content = state.read_text().replace(
            "session_id: \n", "session_id: __pending_abc12345__\n"
        )
        state.write_text(content)
        out, err, rc = _run_hook({"session_id": "sessB"}, self.root)
        self.assertEqual(rc, 0, err)
        recorded = _parse_state_session_id(state.read_text())
        self.assertEqual(recorded, "__pending_abc12345__", "placeholder 유지 기대")

    # ── Case C: 다른 진짜 SID 점유 ──────────────────────────────────────

    def test_other_session_claim_logged(self):
        """이미 다른 세션이 정식 claim했으면 cross-session JSONL 박제."""
        state = _make_state(self.root)
        content = state.read_text().replace(
            "session_id: \n", "session_id: realSidA\n"
        )
        state.write_text(content)
        out, err, rc = _run_hook({"session_id": "sessB"}, self.root)
        self.assertEqual(rc, 0)
        # state 변경 안 됨
        recorded = _parse_state_session_id(state.read_text())
        self.assertEqual(recorded, "realSidA")
        # JSONL 박제 됐는지
        log = ss.state_root(self.root) / ".logs" / "ralph-cross-session.jsonl"
        self.assertTrue(log.exists())
        events = [json.loads(l) for l in log.read_text().splitlines()]
        self.assertTrue(any(
            e.get("event") == "cross_session_state_attempt" and
            e.get("current_sid") == "sessB" and
            e.get("recorded_sid") == "realSidA"
            for e in events
        ))

    def test_same_session_no_op(self):
        """같은 세션이 다시 fire되면 아무것도 안 함."""
        state = _make_state(self.root)
        content = state.read_text().replace(
            "session_id: \n", "session_id: sessA\n"
        )
        state.write_text(content)
        original = state.read_text()
        out, err, rc = _run_hook({"session_id": "sessA"}, self.root)
        self.assertEqual(rc, 0)
        self.assertEqual(state.read_text(), original)

    # ── 가장자리: state 파일 없음, ralph 미실행 ─────────────────────────

    def test_no_state_file_passes(self):
        """state 파일 없으면 즉시 통과."""
        out, err, rc = _run_hook({"session_id": "sessA"}, self.root)
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")

    # ── 실측 시나리오: T1 race ─────────────────────────────────────────

    def test_T1_race_scenario(self):
        """
        시나리오: 세션 A가 ralph 시작 → 세션 B에서 무관한 Stop이 먼저 fire
        → 세션 A의 첫 Stop이 나중에 fire.

        기대:
        1. B의 Stop → ralph-session-stop이 placeholder 박음. 오피셜 STATE != HOOK
           → exit 0 (claim 차단).
        2. A의 Stop → placeholder를 sessA로 교체. 오피셜 STATE == HOOK → 정상 진행.
        """
        ss.set_active_skill("sessA", "ralph-loop:ralph-loop", "heavy",
                            project_root=self.root)
        state = _make_state(self.root)

        # 1. B 첫 fire
        _run_hook({"session_id": "sessB"}, self.root)
        recorded = _parse_state_session_id(state.read_text())
        self.assertTrue(recorded.startswith("__pending_"),
                        f"B fire 후 placeholder 기대: {recorded}")
        # B는 자기 SID로 안 박음
        self.assertNotEqual(recorded, "sessB")

        # 오피셜 격리 시뮬레이션: STATE_SESSION = recorded, HOOK_SESSION = sessB
        # → 다르므로 exit 0 (claim 차단). 실제 셸 시뮬은 안 함, 의미 검증만.
        self.assertNotEqual(recorded, "sessB")

        # 2. A 늦은 fire
        _run_hook({"session_id": "sessA"}, self.root)
        recorded = _parse_state_session_id(state.read_text())
        self.assertEqual(recorded, "sessA",
                         "A fire 후 placeholder가 sessA로 교체돼야 함")


if __name__ == "__main__":
    unittest.main()
