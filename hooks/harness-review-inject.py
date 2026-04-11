#!/usr/bin/env python3
# hooks/harness-review-inject.py
# UserPromptSubmit 훅: 미처리 리뷰 결과를 다음 사용자 메시지에 주입 (Phase D Step A)
#
# 트리거: UserPromptSubmit (global)
# 동작: STATE_DIR/*_review-result.json 감지 → 프롬프트에 리뷰 결과 주입
# 안전장치:
# - HARNESS_INTERNAL=1이면 스킵 (하네스 내부 호출 중 재트리거 방지)
# - parse_error 결과는 조용히 제거 (사용자에게 노이즈 방지)
# - 주입 후 파일 제거 (재트리거 방지)

import json
import os
import glob
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness_common import get_state_dir


def main():
    # 하네스 내부 호출이면 스킵
    if os.environ.get("HARNESS_INTERNAL") == "1":
        print(json.dumps({"continue": True}))
        return

    # stdin에서 이벤트 읽기 (UserPromptSubmit 이벤트)
    try:
        event = json.load(sys.stdin)
    except Exception:
        event = {}

    # 미처리 리뷰 파일 검색 (STATE_DIR/*_review-result.json)
    state_dir = get_state_dir()
    review_files = sorted(glob.glob(os.path.join(state_dir, "*_review-result.json")))
    if not review_files:
        print(json.dumps({"continue": True}))
        return

    # 가장 최신 파일 사용
    review_file = review_files[-1]

    try:
        review = json.loads(open(review_file).read())
    except Exception:
        try:
            os.remove(review_file)
        except Exception:
            pass
        print(json.dumps({"continue": True}))
        return

    # parse_error면 조용히 제거
    if "parse_error" in review:
        try:
            os.remove(review_file)
        except Exception:
            pass
        print(json.dumps({"continue": True}))
        return

    issues = review.get("issues", [])
    high_issues = [i for i in issues if i.get("confidence") == "HIGH"]
    medium_issues = [i for i in issues if i.get("confidence") == "MEDIUM"]
    promote_suggestions = review.get("promote_suggestions", [])

    if not high_issues and not medium_issues and not promote_suggestions:
        try:
            os.remove(review_file)
        except Exception:
            pass
        print(json.dumps({"continue": True}))
        return

    # 프롬프트에 주입
    stats = review.get("stats", {})
    inject_text = "## 하네스 리뷰 결과 (이전 실행)\n\n"
    inject_text += f"통계: {json.dumps(stats, ensure_ascii=False)}\n\n"

    if high_issues:
        inject_text += "### 즉시 수정 권장 (HIGH)\n"
        for issue in high_issues:
            inject_text += f"- [{issue.get('type', '')}]\n"
            inject_text += f"  원인: {issue.get('evidence', '')}\n"
            inject_text += f"  개선방향: {issue.get('suggested_change', '')}\n"
            inject_text += f"  수정 대상: {issue.get('target_file', '')} (위험도: {issue.get('risk', '?')})\n\n"

    if medium_issues:
        inject_text += "### 검토 제안 (MEDIUM)\n"
        for issue in medium_issues:
            inject_text += f"- [{issue.get('type', '')}]\n"
            inject_text += f"  원인: {issue.get('evidence', '')}\n"
            inject_text += f"  개선방향: {issue.get('suggested_change', '')}\n\n"

    if promote_suggestions:
        inject_text += "### 자동 승격 후보 (수동 확인 권장)\n"
        for s in promote_suggestions:
            inject_text += f"- {s}\n"
        inject_text += "\n"

    inject_text += "위 항목을 검토하시겠습니까? 승인하시면 수정합니다.\n"

    # 주입 후 파일 제거 (재트리거 방지)
    try:
        os.remove(review_file)
    except Exception:
        pass

    print(json.dumps({
        "continue": True,
        "additionalContext": inject_text
    }))


if __name__ == "__main__":
    main()
