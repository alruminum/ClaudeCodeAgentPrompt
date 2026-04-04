---
description: 현재 프로젝트 루트에 Harness Engineering 훅 세트를 .claude/settings.json에 설치한다. UserPromptSubmit 라우터 + PreToolUse/PostToolUse 에이전트 게이트 + SessionStart 초기화 포함.
argument-hint: ""
---

# /init-harness

현재 프로젝트에 Harness Engineering 훅을 설치한다.

---

## 실행

`bash ~/.claude/setup-harness.sh` 를 현재 작업 디렉토리에서 실행한다.

실행 후:
1. 설치된 훅 목록과 prefix를 유저에게 출력한다
2. 기존 settings.json이 있으면 allowedTools를 보존했음을 안내한다
3. 다음 단계(/init-agents)를 안내한다

---

## 완료 후 안내 메시지

```
Harness 훅이 .claude/settings.json에 설치되었습니다.

설치된 훅:
- UserPromptSubmit : 매 프롬프트 전 요청 분류 + 하네스 상태 자동 주입 (router.ts)
- SessionStart     : 세션 시작 시 /tmp/${PREFIX}_* 플래그 초기화
- PreToolUse       : 에이전트 실행 순서 강제 게이트 (harness_loop.ts)
- PostToolUse      : 에이전트 완료 후 플래그 자동 관리

다음 단계:
- /init-agents 로 에이전트 파일을 초기화하세요
- 각 에이전트의 '프로젝트 특화 지침' 섹션에 이 프로젝트에 맞는 내용을 추가하세요
```
