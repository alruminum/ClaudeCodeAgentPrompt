---
description: 현재 프로젝트 루트에 .claude/agents/ 디렉토리를 생성하고 9개 에이전트 파일(orchestrator, architect, engineer, test-engineer, pr-reviewer, validator, designer, design-critic, qa)을 초기화한다.
argument-hint: ""
---

# /init-agents

현재 프로젝트에 에이전트 파일을 초기화한다.

---

## 실행

`bash ~/.claude/setup-agents.sh` 를 현재 작업 디렉토리에서 실행한다.

실행 후:
1. 생성된 파일 목록을 유저에게 출력한다
2. 각 파일의 `## 프로젝트 특화 지침` 섹션에 이 프로젝트에 맞는 내용을 추가해야 함을 안내한다

---

## 완료 후 안내 메시지

```
에이전트 파일 9개가 .claude/agents/에 생성되었습니다.

다음 단계:
- product-planner 에이전트와 대화해서 PRD/TRD를 만들어 나가세요.
  예: "새 프로젝트 기획 도와줘" → product-planner 에이전트가 역질문으로 PRD/TRD 작성
- PRD/TRD 완성 후 orchestrator 에이전트로 구현을 시작하세요.
```
