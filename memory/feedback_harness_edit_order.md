---
name: 하네스 수정 순서 규칙
description: 하네스 관련 파일 수정 시 반드시 지켜야 할 3단계 순서
type: feedback
---

백로그 먼저 → 실제 수정 → state 문서 업데이트 순서를 반드시 지킬 것.

**Why:** 코드 먼저 수정하고 문서 나중에 기록하는 패턴 방지.
backlog는 "무엇을 할지" 계획, state는 "무엇이 됐는지" 결과 기록이므로 순서가 의미를 가짐.

**How to apply:** harness-executor.sh / harness-loop.sh / hooks/*.py / settings.json(hooks 섹션) /
에이전트 파일 수정 전 항상 harness-backlog.md 먼저 업데이트.
수정 완료 후 harness-state.md 현행화.
