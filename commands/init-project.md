---
description: 새 프로젝트 루트에 Harness Engineering 환경을 한 번에 구성한다. setup-harness.sh 단일 실행으로 settings.json + harness.config.json + CLAUDE.md + GitHub 마일스톤까지 완료.
argument-hint: ""
---

# /init-project

빈 폴더(또는 새 프로젝트 루트)에서 Harness Engineering 환경을 한 번에 구성한다.

---

## Step 0 — 실행 전 유저에게 2가지 질문

스크립트를 실행하기 전에 아래를 유저에게 먼저 물어본다. 모두 선택 사항이므로 "나중에" 답변도 허용한다.

```
1. GitHub repo URL이 있나요? (예: owner/repo-name)
   → 마일스톤/레이블 자동 생성 + CLAUDE.md pre-fill에 사용됩니다.
   → 없으면 엔터

2. 핵심 설계 문서 이름은 무엇인가요? (예: game-logic, domain-logic, api-spec)
   → architect SPEC_GAP 신선도 체크에 사용됩니다.
   → 없으면 엔터 (기본값: domain-logic)
```

---

## Step 1 — setup-harness.sh 실행

```bash
bash ~/.claude/setup-harness.sh [--doc-name <DOC_NAME>] [--repo <REPO>]
```

예시:
```bash
bash ~/.claude/setup-harness.sh --doc-name domain-logic --repo myorg/my-app
```

이 스크립트가 한 번에 처리하는 것:
- `.claude/settings.json` — env + allowedTools
- `.claude/harness.config.json` — prefix 자동 생성
- `.claude/agent-config/` — 프로젝트별 에이전트 지침 디렉토리
- `CLAUDE.md` — 베이스 템플릿 복사 (없을 때만)
- GitHub 마일스톤/레이블 자동 생성 (repo 제공 시)
- 낡은 `.claude/agents/` 복사본 감지 및 안내

> 에이전트 파일은 전역(`~/.claude/agents/`)에서 직접 로드된다. 프로젝트에 복사하지 않는다.
> 프로젝트별 에이전트 지침은 `.claude/agent-config/{에이전트명}.md`에 작성한다.

---

## Step 2 — 완료 후 안내

### 1. CLAUDE.md `[채우기]` 항목 작성

```
CLAUDE.md 를 열어 [채우기] 표시된 항목을 이 프로젝트에 맞게 채우세요:
- 프로젝트명, 플랫폼 설명
- 개발 명령어 (npm run dev / build 등)
- 환경변수 목록
```

### 2. 프로젝트별 에이전트 지침 작성 (선택)

에이전트별 프로젝트 컨텍스트가 필요하면 `.claude/agent-config/`에 파일을 만든다.
없으면 전역 에이전트가 기본 동작으로 진행한다.

```
.claude/agent-config/ 에 작성 가능한 파일:
- engineer.md      : SDK 래퍼 패턴, 샌드박스 분기, 의존성 규칙
- designer.md      : 브랜드/플랫폼 제약, PRD UI 키워드
- test-engineer.md : 테스트 명령어, mock 금지 여부
- architect.md     : TRD 섹션 매핑, 프로젝트 특화 설계 문서
- 기타 에이전트     : 필요할 때만 작성
```

### 3. 다음 작업

```
환경이 준비되었습니다. 일반적인 다음 단계:

1. product-planner 에이전트와 대화해서 PRD/TRD 작성
2. architect SYSTEM_DESIGN → 설계 문서 초안
3. architect TASK_DECOMPOSE → 에픽 → backlog.md + stories.md 분해
4. 구현 루프 실행 (python3 ~/.claude/harness/executor.py impl ...)
```

---

## 완료 메시지 출력 형식

```
✅ Harness Engineering 환경 구성 완료

생성된 파일:
  .claude/settings.json        — env + allowedTools
  .claude/harness.config.json  — prefix: [자동감지값]
  .claude/agent-config/        — 프로젝트별 에이전트 지침 (선택적으로 채움)
  CLAUDE.md                    — 베이스 템플릿

에이전트:
  전역 ~/.claude/agents/ 에서 직접 로드 (프로젝트 복사 없음)
  프로젝트별 지침: .claude/agent-config/{name}.md 에 작성

남은 작업:
  CLAUDE.md [채우기] 항목 작성
  → product-planner와 PRD 작업 시작
```
