---
description: 새 프로젝트 루트에 Harness Engineering 훅 + 에이전트 파일을 한 번에 설치한다. 실행 전 3가지 질문 수집 → setup-harness.sh → setup-agents.sh 순으로 실행.
argument-hint: ""
---

# /init-project

빈 폴더(또는 새 프로젝트 루트)에서 Harness Engineering 환경을 한 번에 구성한다.

---

## Step 0 — 실행 전 유저에게 3가지 질문

스크립트를 실행하기 전에 아래 3가지를 유저에게 먼저 물어본다. 모두 선택 사항이므로 "나중에 채울게" 답변도 허용한다.

```
1. GitHub repo URL이 있나요? (예: owner/repo-name)
   → architect/qa 에이전트와 마일스톤 자동 생성에 사용됩니다.
   → 없으면 엔터 (나중에 수동으로 채울 수 있음)

2. 핵심 설계 문서 이름은 무엇인가요? (예: game-logic, domain-logic, api-spec)
   → architect Mode C 완료 후 신선도 체크에 사용됩니다.
   → 없으면 엔터 (기본값: domain-logic)

3. 개발 서버 포트는 무엇인가요? (예: 5173, 3000)
   → design-critic 에이전트의 Playwright URL에 사용됩니다.
   → 없으면 엔터 (기본값: 5173)
```

수집된 값을 바탕으로 아래 Step 1에서 인수를 구성한다.

---

## Step 1 — 실행 순서

수집한 값을 인수로 전달해 아래 두 명령어를 **순서대로** 실행한다.

```bash
# REPO, DOC_NAME, PORT는 Step 0에서 수집한 값으로 대체
bash ~/.claude/setup-harness.sh [--doc-name <DOC_NAME>] [--repo <REPO>]
bash ~/.claude/setup-agents.sh [--repo <REPO>]
```

예시 (repo=myorg/my-app, doc-name=domain-logic):
```bash
bash ~/.claude/setup-harness.sh --doc-name domain-logic --repo myorg/my-app
bash ~/.claude/setup-agents.sh --repo myorg/my-app
```

repo나 doc-name이 없으면 해당 인수 생략 (기본값 자동 적용).

---

## Step 2 — design-critic Playwright URL 업데이트 (포트 수집 시)

포트를 수집했다면, 생성된 `.claude/agents/design-critic.md` 파일의 프로젝트 특화 지침에 URL을 추가한다:

```
- Playwright localhost URL: http://localhost:<PORT>
```

---

## 각 스크립트 역할

| 스크립트 | 생성/수정 파일 | 역할 |
|---|---|---|
| `setup-harness.sh` | `.claude/settings.json`, `.claude/harness.config.json` | PreToolUse/PostToolUse 게이트 훅 설치, prefix 자동 생성, doc_name 신선도 체크 |
| `setup-agents.sh` | `.claude/agents/*.md`, `CLAUDE.md` | 에이전트 10종 생성 + repo pre-fill + CLAUDE.md 베이스 복사 + GitHub 마일스톤/레이블 자동 생성 |

> UserPromptSubmit(harness-router) + SessionStart(harness-session-start)는 **전역** `~/.claude/settings.json`에서 이미 실행됨. 프로젝트별 재설치 불필요.

---

## 실행 후 체크리스트

실행이 완료되면 아래 항목을 유저에게 안내한다.

### 1. CLAUDE.md `[채우기]` 항목 작성 (repo 미제공 시)
```
CLAUDE.md 를 열어 [채우기] 표시된 항목을 이 프로젝트에 맞게 채우세요:
- 프로젝트명, 플랫폼 설명
- 개발 명령어 (npm run dev / build 등)
- 환경변수 목록
- GitHub repo URL (repo 인수로 제공했으면 자동 입력됨)
```

### 2. 남은 에이전트 특화 지침 작성

> `architect.md`, `qa.md`는 repo가 제공되면 자동으로 pre-fill됩니다.
> 아래는 수동으로 채워야 하는 파일들입니다.

```
.claude/agents/ 에서 아직 주석인 항목:
- engineer.md      : SDK 래퍼 패턴, 샌드박스 분기, 의존성 규칙
- validator.md     : 금지 패턴, impl 파일 경로 패턴
- test-engineer.md : 테스트 명령어, mock 금지 여부
- pr-reviewer.md   : 프로젝트 컨벤션, 금지 패턴
- designer.md      : 브랜드/플랫폼 제약, PRD UI 키워드
- design-critic.md : PICK 기준 세부 조건 (Playwright URL은 Step 2에서 자동)
- architect.md     : SDK MCP 확인 여부, 프로젝트 특화 설계 문서 이름
- qa.md            : CRITICAL 버그 기준, 라우팅 결정 기준
```

### 3. 다음 작업
```
환경이 준비되었습니다. 일반적인 다음 단계:

1. product-planner 에이전트와 대화해서 PRD/TRD 작성

2. architect Mode A → 설계 문서 초안
   (docs/architecture.md, docs/domain-logic.md 등)

3. architect Mode D → 에픽 → backlog.md + stories.md 분해

4. architect Mode B → validator Mode A → engineer 루프
   (또는 bash .claude/harness/executor.sh로 자동화)
```

---

## 완료 메시지 출력 형식

```
✅ Harness Engineering 환경 구성 완료

생성된 파일:
  .claude/settings.json        — PreToolUse/PostToolUse 게이트 훅 (doc: docs/<DOC_NAME>.md)
  .claude/harness.config.json  — prefix: [자동감지값]
  .claude/agents/engineer.md
  .claude/agents/validator.md
  .claude/agents/architect.md         ← repo pre-filled: <REPO>
  .claude/agents/designer.md
  .claude/agents/design-critic.md     ← Playwright URL: http://localhost:<PORT>
  .claude/agents/test-engineer.md
  .claude/agents/pr-reviewer.md
  .claude/agents/qa.md                ← repo pre-filled: <REPO>
  .claude/harness/executor.sh
  CLAUDE.md                    — 베이스 템플릿 복사

GitHub 마일스톤 (<REPO>):
  ✅ Story  ✅ Bugs  ✅ Epics  ✅ Feature
  ✅ v01 레이블  ✅ bug 레이블  ✅ feat 레이블

남은 작업:
  engineer.md / validator.md / test-engineer.md / pr-reviewer.md / designer.md 특화 지침 채우기
  → product-planner와 PRD 작업 시작
```
