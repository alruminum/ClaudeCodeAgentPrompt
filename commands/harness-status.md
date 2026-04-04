---
description: 현재 프로젝트의 harness 훅 상태와 워크플로우 플래그를 확인한다.
argument-hint: ""
---

# /harness-status

현재 harness 상태를 점검한다.

## 실행

아래 명령어를 실행하고 결과를 유저에게 출력한다:

```bash
python3 ~/.claude/hooks/harness-router.py mb <<< '{"tool_input":{"prompt":"수정"}}'
```

그리고 추가로:

```bash
ls /tmp/mb_* 2>/dev/null && echo "활성 플래그 있음" || echo "활성 플래그 없음"
```

## 출력 형식

결과를 아래 형태로 정리해서 보여준다:

```
[Harness Status]
라우터 스크립트: ~/.claude/hooks/harness-router.py ✅/❌
워크플로우 플래그:
  OK/NG plan_validation_passed
  OK/NG test_engineer_passed
  OK/NG validator_b_passed
  OK/NG pr_reviewer_lgtm
  ...
```
