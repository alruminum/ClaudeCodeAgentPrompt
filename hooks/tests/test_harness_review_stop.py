"""
tests/test_harness_review_stop.py
harness-review-stop.py Stop 훅 테스트

실제 스크립트를 subprocess로 실행해 stdout JSON 출력과 파일 정리를 검증한다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "harness-review-stop.py"
TRIGGER = Path("/tmp/harness_review_trigger.json")
HARNESS_LOGS_BASE = Path.home() / ".claude" / "harness-logs"


def run_hook() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="",
        capture_output=True,
        text=True,
    )


def write_trigger(jsonl=None, marker: str = "HARNESS_DONE"):
    TRIGGER.write_text(json.dumps({"marker": marker, "jsonl": jsonl}))


def setup_function():
    TRIGGER.unlink(missing_ok=True)


def teardown_function():
    TRIGGER.unlink(missing_ok=True)


# ── 1. 트리거 파일 존재 → {"continue": true, "prompt": "..."} 출력 ────────
def test_trigger_present_outputs_continue():
    write_trigger()
    result = run_hook()
    assert result.returncode == 0
    assert result.stdout.strip(), "stdout이 비어있으면 안 됨"

    out = json.loads(result.stdout.strip())
    assert out["continue"] is True
    assert "/harness-review" in out["prompt"]


# ── 2. 트리거 파일 없으면 아무것도 출력하지 않고 exit 0 ──────────────────
def test_no_trigger_no_output():
    result = run_hook()
    assert result.returncode == 0
    assert result.stdout.strip() == "", "트리거 없으면 stdout 비어있어야 함"


# ── 3. 트리거 파일 실행 후 삭제 ─────────────────────────────────────────
def test_trigger_deleted_after_run():
    write_trigger()
    assert TRIGGER.exists()
    run_hook()
    assert not TRIGGER.exists(), "트리거 파일이 실행 후 삭제되어야 함"


# ── 4. harness-logs/ 기준 상대경로 변환 ─────────────────────────────────
def test_relative_path_conversion():
    jsonl_abs = str(HARNESS_LOGS_BASE / "mb" / "run_20260409_223459.jsonl")
    write_trigger(jsonl=jsonl_abs)

    result = run_hook()
    out = json.loads(result.stdout.strip())
    # 상대경로 "mb/run_20260409_223459.jsonl" 가 prompt에 포함되어야 함
    assert "mb/run_20260409_223459.jsonl" in out["prompt"], (
        f"상대경로 변환 실패. prompt: {out['prompt']}"
    )
    # 절대경로가 그대로 들어가지 않아야 함
    assert str(HARNESS_LOGS_BASE) not in out["prompt"]


# ── 5. harness-logs 외 경로 → 그대로 사용 ───────────────────────────────
def test_other_path_used_as_is(tmp_path):
    # 실제로 존재하는 파일이어야 os.path.exists() 통과
    jsonl_other = str(tmp_path / "run.jsonl")
    Path(jsonl_other).write_text('{"event":"test"}\n')
    write_trigger(jsonl=jsonl_other)

    result = run_hook()
    out = json.loads(result.stdout.strip())
    assert jsonl_other in out["prompt"], (
        f"harness-logs 외 경로는 그대로 사용해야 함. prompt: {out['prompt']}"
    )


# ── 6. jsonl 경로가 None이면 "/harness-review"만 출력 ────────────────────
def test_no_jsonl_path_default_prompt():
    write_trigger(jsonl=None)
    result = run_hook()
    out = json.loads(result.stdout.strip())
    assert out["prompt"].strip() == "/harness-review"


# ── 7. jsonl 파일이 실제로 없는 경로 → "/harness-review"만 출력 ──────────
def test_nonexistent_jsonl_default_prompt():
    write_trigger(jsonl="/tmp/does_not_exist.jsonl")
    result = run_hook()
    out = json.loads(result.stdout.strip())
    # 존재하지 않는 파일이면 경로 없이 /harness-review만
    assert out["prompt"].strip() == "/harness-review"


# ── 8. 트리거 JSON 파싱 실패 → exit 0, 파일 삭제, 출력 없음 ─────────────
def test_corrupt_trigger_no_crash():
    TRIGGER.write_text("이건 유효한 json이 아님")
    result = run_hook()
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert not TRIGGER.exists(), "파싱 실패한 트리거 파일도 삭제되어야 함"
