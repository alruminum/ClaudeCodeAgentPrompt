---
name: ralph-loop 복잡한 프롬프트 전달 방식
description: ralph-loop에 특수문자(대괄호 등) 포함 프롬프트 전달 시 임시 파일 사용
type: feedback
---

ralph-loop:ralph-loop 호출 시 프롬프트에 `[`, `]`, `(`, `)` 등 shell 특수문자가 포함되면 파싱 오류 발생.

**Why:** setup-ralph-loop.sh가 `$ARGUMENTS`를 언쿼팅 상태로 받아서 bash가 glob 확장을 먼저 처리함.

**How to apply:**
1. 프롬프트를 `/tmp/ralph_task_YYYYMMDD.md` 에 Write 도구로 저장
2. ralph-loop에는 짧은 프롬프트 전달: `"Read /tmp/ralph_task_YYYYMMDD.md and execute the task"`
3. 루프 완료 후 임시 파일 삭제 (`rm /tmp/ralph_task_*.md`)
