#!/usr/bin/env python3
# hooks/harness-review-inject.py
# UserPromptSubmit 훅: 미처리 리뷰 결과를 다음 사용자 메시지에 주입
#
# 트리거: UserPromptSubmit (global)
# 동작: STATE_DIR/*_review-result.json 감지 → 프롬프트에 리뷰 리포트 원문 주입
# 안전장치:
# - HARNESS_INTERNAL=1이면 스킵 (하네스 내부 호출 중 재트리거 방지)
# - 주입 후 파일 제거 (재트리거 방지)

import json
import os
import glob
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness_common import get_state_dir, is_harness_enabled


def main():
    # 화이트리스트 가드 — `~/.claude/harness-projects.json` 등록된 프로젝트에서만 동작.
    if not is_harness_enabled():
        sys.exit(0)

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

    # 리포트 원문이 있으면 그대로 주입
    report = review.get("report", "")
    if not report:
        # 이전 포맷 호환 (issues 기반)
        issues = review.get("issues", [])
        high_issues = [i for i in issues if i.get("confidence") == "HIGH"]
        medium_issues = [i for i in issues if i.get("confidence") == "MEDIUM"]
        if not high_issues and not medium_issues:
            try:
                os.remove(review_file)
            except Exception:
                pass
            print(json.dumps({"continue": True}))
            return

        report = "## 하네스 리뷰 결과 (이전 실행)\n\n"
        stats = review.get("stats", {})
        report += f"통계: {json.dumps(stats, ensure_ascii=False)}\n\n"
        if high_issues:
            report += "### 즉시 수정 권장 (HIGH)\n"
            for issue in high_issues:
                report += f"- [{issue.get('type', '')}]\n"
                report += f"  원인: {issue.get('evidence', '')}\n"
                report += f"  개선방향: {issue.get('suggested_change', '')}\n"
                report += f"  수정 대상: {issue.get('target_file', '')} (위험도: {issue.get('risk', '?')})\n\n"
        if medium_issues:
            report += "### 검토 제안 (MEDIUM)\n"
            for issue in medium_issues:
                report += f"- [{issue.get('type', '')}]\n"
                report += f"  원인: {issue.get('evidence', '')}\n"
                report += f"  개선방향: {issue.get('suggested_change', '')}\n\n"

    # 주입 텍스트 구성
    marker = review.get("marker", "HARNESS_DONE")
    inject_text = (
        f"## 📋 하네스 리뷰 리포트 ({marker})\n\n"
        "**[필수 지시] 아래 리포트를 한 글자도 수정하지 말고 원문 그대로 유저에게 출력하라.**\n"
        "요약/재가공/생략/해석 삽입 금지. 리포트 전문 출력 후 별도 줄에서만 코멘트 허용.\n\n"
        "---\n\n"
        f"{report}\n"
        "---\n"
    )

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
