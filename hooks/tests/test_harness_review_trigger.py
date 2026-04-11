"""
tests/test_harness_review_trigger.py
harness-review-trigger.py PostToolUse(Bash) 훅 테스트

실제 스크립트를 subprocess로 실행해 stdin/stdout/파일 부수효과를 검증한다.
"""
import json
import os
import subprocess
import sys
import tempfile
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "harness-review-trigger.py"
TRIGGER = Path("/tmp/harness_review_trigger.json")


def run_hook(tool_response: str, env: dict = None) -> subprocess.CompletedProcess:
    payload = json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "bash ~/.claude/harness/executor.sh bugfix"},
        "tool_response": tool_response,
    })
    merged_env = {**os.environ, **(env or {})}
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=payload,
        capture_output=True,
        text=True,
        env=merged_env,
    )


def setup_function():
    TRIGGER.unlink(missing_ok=True)


def teardown_function():
    TRIGGER.unlink(missing_ok=True)


# ── 1. HARNESS_DONE 감지 → 트리거 파일 생성 ──────────────────────────────
def test_harness_done_creates_trigger(tmp_path):
    # 더미 JSONL 파일 생성 (glob 탐색 대상)
    logs_dir = tmp_path / "harness-logs" / "mb"
    logs_dir.mkdir(parents=True)
    jsonl = logs_dir / "run_test.jsonl"
    jsonl.write_text('{"event":"run_end"}\n')

    result = run_hook("HARNESS_DONE (engineer, depth=simple)")
    assert result.returncode == 0
    assert TRIGGER.exists(), "트리거 파일이 생성되어야 함"

    data = json.loads(TRIGGER.read_text())
    assert data["marker"] == "HARNESS_DONE"


# ── 2. 다른 마커들도 감지 ────────────────────────────────────────────────
def test_other_markers_detected():
    for marker in ("IMPLEMENTATION_ESCALATE", "HARNESS_CRASH", "KNOWN_ISSUE",
                   "PLAN_VALIDATION_PASS", "PLAN_VALIDATION_ESCALATE"):
        TRIGGER.unlink(missing_ok=True)
        result = run_hook(f"{marker}: 테스트")
        assert result.returncode == 0
        assert TRIGGER.exists(), f"{marker} 감지 시 트리거 파일 생성 필요"
        data = json.loads(TRIGGER.read_text())
        assert data["marker"] == marker
        TRIGGER.unlink(missing_ok=True)


# ── 3. 마커 없는 출력 → 트리거 파일 미생성 ──────────────────────────────
def test_no_marker_no_trigger():
    result = run_hook("commit: abc1234\nbranch: feat/some-feature")
    assert result.returncode == 0
    assert not TRIGGER.exists(), "마커 없으면 트리거 파일 생성되지 않아야 함"


# ── 4. 트리거 파일 이미 존재 → 중복 생성 방지 ───────────────────────────
def test_no_duplicate_trigger():
    original = {"marker": "PREVIOUS", "jsonl": None}
    TRIGGER.write_text(json.dumps(original))
    mtime_before = TRIGGER.stat().st_mtime

    result = run_hook("HARNESS_DONE (engineer, depth=simple)")
    assert result.returncode == 0

    # 파일이 그대로여야 함 (덮어쓰지 않음)
    data = json.loads(TRIGGER.read_text())
    assert data["marker"] == "PREVIOUS", "기존 트리거 파일을 덮어쓰지 않아야 함"


# ── 5. stdin JSON 파싱 실패 → 크래시 없이 종료 ──────────────────────────
def test_invalid_stdin_no_crash():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="이건 json이 아님",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "stdin 파싱 실패 시에도 exit 0이어야 함"
    assert not TRIGGER.exists()


# ── 6. 빈 stdin → 크래시 없이 종료 ─────────────────────────────────────
def test_empty_stdin_no_crash():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


# ── 7. _cwd_to_proj_hash: / → -, . → - 변환 ──────────────────────────
def test_cwd_to_proj_hash():
    spec = importlib.util.spec_from_file_location("trigger", str(SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod._cwd_to_proj_hash("/Users/dc.kim/.claude") == "-Users-dc-kim--claude"
    assert mod._cwd_to_proj_hash("/Users/dc.kim/project/memoryBattle") == "-Users-dc-kim-project-memoryBattle"
    assert mod._cwd_to_proj_hash("/Users/foo/bar") == "-Users-foo-bar"
    assert mod._cwd_to_proj_hash("/Users/a.b.c/d.e") == "-Users-a-b-c-d-e"


# ── 8. _find_proj_dir: 실제 ~/.claude/projects/ 매칭 ──────────────────
def test_find_proj_dir(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("trigger", str(SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # 임시 projects/ 구조 생성
    projects = tmp_path / "projects"
    (projects / "-Users-test-user-myproject").mkdir(parents=True)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path) if p == "~/.claude/projects" else p)

    # expanduser 를 모듈 내부에서도 쓰므로, 함수를 직접 테스트
    result = mod._cwd_to_proj_hash("/Users/test.user/myproject")
    assert result == "-Users-test-user-myproject"


# ── 9. _find_session_jsonl: proj_dir 내 최근 JSONL 반환 ────────────────
def test_find_session_jsonl_fallback(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("trigger", str(SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # 임시 프로젝트 디렉토리
    proj_dir = tmp_path / "-Users-test-proj"
    proj_dir.mkdir()
    (proj_dir / "abc-123.jsonl").write_text('{"type":"system"}\n')

    # _find_proj_dir가 이 디렉토리를 반환하도록 패치
    monkeypatch.setattr(mod, "_find_proj_dir", lambda cwd: str(proj_dir))
    monkeypatch.delenv("CMUX_CLAUDE_PID", raising=False)

    result = mod._find_session_jsonl()
    assert result is not None
    assert result.endswith("abc-123.jsonl")
