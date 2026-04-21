# [프로젝트명]

[한 줄 설명. 플랫폼, 장르, MVP 기간 등]

---

## 베이스 동기화 규칙

이 CLAUDE.md에 새 규칙·섹션을 추가할 때, 아래 기준으로 베이스도 함께 업데이트한다:

| 조건 | 처리 |
|---|---|
| 프로젝트 독립적 (에이전트 호출 방식, 워크플로우, Git 규칙 등) | `~/.claude/templates/CLAUDE-base.md`에도 동일하게 추가 |
| 프로젝트 특화 (레포 URL, 에픽 테이블, 환경변수, SDK 특화 명령어 등) | 이 CLAUDE.md에만 기록 |

---

## 개발 명령어

```bash
# [초기화] 예: npm install / pnpm install
npm install

# [개발] 예: npm run dev / next dev
npm run dev

# [빌드] 예: npm run build / next build
npm run build

# [테스트] 예: npx vitest run / npm test
npx vitest run
```

## 환경변수 (`.env`)

```
# [키=값] 예:
# DATABASE_URL=postgresql://...
# NEXT_PUBLIC_API_URL=http://localhost:3000
```

---

## GitHub Issues 마일스톤

| 용도 | 마일스톤 |
|---|---|
| 버그 (동작 오류) | `Bugs` |
| 기능 추가·개선 | `Feature` |
| 스토리 이슈 | `Story` |
| 에픽 | `Epics` |
| 현재 버전 레이블 | `v01` |

> 버전이 올라가면 "현재 버전 레이블" 항목만 업데이트.

### 이슈 생성 시 마일스톤 처리 규칙

`mcp__github__create_issue`의 `milestone` 파라미터는 **이름이 아닌 숫자(number)**를 요구한다.  
이슈 생성 전 반드시 아래 명령으로 마일스톤 이름 → 번호를 조회한다:

```bash
gh api repos/{owner}/{repo}/milestones --jq '.[] | {number: .number, title: .title}'
```

조회 결과에서 위 표의 마일스톤 이름에 해당하는 `number`를 `milestone` 파라미터에 전달한다.

### 이슈 등록 필수 항목

버그 이슈:

| 항목 | 값 |
|---|---|
| 레이블 | `bug` + 현재 버전 레이블 |
| 마일스톤 | `Bugs` |

기능/개선 이슈:

| 항목 | 값 |
|---|---|
| 레이블 | `feat` + 현재 버전 레이블 |
| 마일스톤 | `Feature` |

스토리 이슈:

| 항목 | 값 |
|---|---|
| 레이블 | 해당 에픽 레이블 + 현재 버전 레이블 |
| 마일스톤 | `Story` |

---

## 오케스트레이션 워크플로우

전역 룰: `~/.claude/orchestration-rules.md`

---

## 작업 순서 (반드시 준수)

### 버그픽스 작업 순서 (`bug` 레이블 이슈인 경우)

> 신규 기능(feat)과 다른 경로. 아래 규칙 준수.

1. **원래 이슈 번호 유지** — 새 이슈 등록 금지. 추가 수정은 원래 이슈 체크리스트에 항목 추가
2. architect 호출 시 프롬프트 첫 줄에 반드시 `버그픽스 —` 명시
3. 구현 중 추가 수정 발생 → 별개 이슈 등록 금지 → 원래 이슈에 통합
4. 커밋 메시지: 원래 이슈 번호 참조 (`Related to #NNN` 또는 `Closes #NNN`)

---

1. **GitHub Issues** 에서 해당 에픽 레이블/마일스톤으로 미완료 이슈 확인
2. **이슈 본문**에서 스토리 컨텍스트 + 태스크 체크리스트 확인
3. **`docs/epics/epic-NN-*/impl/NN-*.md`** 계획 확인 (없으면 architect에게 요청)
4. 구현 후 GitHub Issue 체크리스트 업데이트 / 모든 태스크 완료 시 이슈 close

사람이 해야 할 운영/출시 항목은 **`RELEASE.md`** 참조.

| 에픽 | impl | 계획 파일 | Issue |
|---|---|---|---|
| [epic-01-xxx] | [모듈명] | [docs/epics/epic-01-xxx/impl/NN-모듈명.md] | [#N] |

---

## stories.md 작성 규칙

- **스토리 번호**: 에픽 내 독립 순번 (Story 1, Story 2 …). 전역 누적 번호 사용 금지.
- **impl 파일 번호**: 에픽 내 독립 순번 (01-*, 02-*, 03-* …). 전역 누적 번호 사용 금지.
- 새 에픽 stories.md 작성 전 직전 에픽 stories.md를 읽어 컨벤션 확인 필수.

---

## 새 마일스톤 시작 전 체크리스트

PRD/스펙이 크게 바뀌어 새 마일스톤을 시작할 때 아래 순서로 스냅샷을 보관한다.

> **원칙**: 루트 파일 = 항상 현재 최신. 과거 버전 = `docs/milestones/vNN/`에 스냅샷.

1. 루트 스펙 파일(`prd.md`, `trd.md`, `docs/ui-spec.md` 등) → `docs/milestones/vNN/`에 복사
2. 현재 에픽 폴더 → `docs/milestones/vNN/epics/`에 복사
3. 루트 파일 업데이트 (새 버전 내용으로 교체)
4. `backlog.md` + `CLAUDE.md` 경로 업데이트

> 소규모 수정(버그픽스, 단순 문구 변경)은 스냅샷 불필요. PRD 스펙 변경 수준일 때만 적용.

---

## 문서 목록

| 파일 | 내용 |
|---|---|
| [backlog.md](backlog.md) | 에픽 목록 인덱스 |
| [RELEASE.md](RELEASE.md) | 운영/출시 체크리스트 |
| [docs/epics/](docs/epics/) | 에픽별 impl/ |
| [docs/architecture.md](docs/architecture.md) | 시스템 구조·화면 흐름·ERD |
| [docs/domain-logic.md](docs/domain-logic.md) | 핵심 비즈니스 로직·상수·계산식 |
| [docs/db-schema.md](docs/db-schema.md) | DB 테이블 DDL + 주요 쿼리 |
| [docs/sdk.md](docs/sdk.md) | 외부 SDK/API 연동 |
| [docs/ui-spec.md](docs/ui-spec.md) | 화면별 컴포넌트 스펙 |
| [prd.md](prd.md) / [trd.md](trd.md) | 요구사항 정의 |

---

## Git

```
Remote: [리포 URL]
Branch: main
```

### 커밋 메시지 규칙

#### 템플릿

```
<type>(<scope>): <한 줄 요약>

[왜] <트리거 — 버그: 재현 조건 / 기능: 요구사항 출처 / 리팩: 문제 상황>
[변경]
- <파일/모듈>: <변경 내용>
[주의] <사이드이팩트·후속 작업> (없으면 생략)

Closes/Related to #NNN
```

> `.gitmessage` 파일을 프로젝트 루트에 두고 `git config commit.template .gitmessage` 로 등록하면 `git commit` 시 에디터에 자동 삽입.

#### scope 목록

`[프로젝트 모듈명들]` `harness` `agent` `docs` `test` `ci`

#### type별 [왜] 작성 기준

| type | [왜] 내용 |
|---|---|
| `fix` | 재현 조건 + 근본 원인 (한 문장) |
| `feat` | PRD/이슈 번호 + 어떤 요구사항인지 |
| `refactor` | 어떤 문제가 있었는지 (가독성/성능/결합도) |
| `chore` | 왜 이 시점에 필요했는지 |
| `docs` | 무엇이 불일치/누락됐었는지 |
| `test` | 어떤 시나리오가 커버 안 됐었는지 |

#### 커밋 분리 원칙

- 문서 변경 + 코드 변경 → 반드시 별도 커밋
- chore(harness/agent) + feat → 반드시 별도 커밋
- 실패 커밋 재시도 → push 전 `git rebase -i`로 squash

#### 이슈 연결

- 완료: `Closes #NNN`
- 참조: `Related to #NNN`

### 이슈 close 원칙 (절대 원칙)

- **GitHub API로 이슈를 직접 close 금지**
- 이슈는 반드시 **`git push` 이후** `Closes #NNN` 커밋 메시지로만 자동 close

---

## 에이전트 호출 규칙

- **서브에이전트 base 우회 금지**: 에이전트 호출 시 base 워크플로우를 우회하는 방식 금지
- **architect 호출 시 반드시 Mode 명시**: 프롬프트 첫 줄 형식 필수 → `[Mode명] — [용도 한 줄 설명]`
- **서브에이전트 포어그라운드 호출**: 백그라운드 에이전트 금지

### architect 모드 상세

| 키워드 | 용도 | 산출물 |
|---|---|---|
| **`SYSTEM_DESIGN`** | 시스템 전체 구조 설계 | `docs/architecture.md` 등 설계 문서 |
| **`MODULE_PLAN`** | 모듈별 구현 계획 파일 작성 | `docs/impl/NN-*.md` ← 기본값 |
| **`SPEC_GAP`** | SPEC_GAP 피드백 처리 | impl 파일 수정 |
| **`TASK_DECOMPOSE`** | Epic stories → 기술 태스크 분해 + impl batch 작성 | stories 업데이트 + impl 파일들 |
| **`TECH_EPIC`** | 기술 에픽 설계 (성능·보안·리팩) | `docs/` 설계 문서 |
| **`LIGHT_PLAN`** | 버그픽스·디자인 반영·pr-reviewer 피드백 반영 (경량) | `docs/bugfix/#N-*.md` |
| **`DOCS_SYNC`** | impl 완료 후 참조 docs 섹션 후행 반영 | docs/*.md 수정 |

> 프롬프트에 위 키워드 중 하나를 명시한다. 미지정 시 stderr 경고 + 에이전트가 입력으로 자가 판단.
> 알파벳 표기(Mode A-G)는 deprecate — 키워드만 사용.
> **버그픽스/리뷰 반영 시**: 프롬프트 첫 줄에 `버그픽스 —` 또는 `LIGHT_PLAN` 명시.

### designer 루프 트리거 기준

"스크린샷이 달라지는가?"가 핵심 질문.

| 요청 유형 | designer 루프 필요? |
|---|---|
| 새 화면 추가 | ✅ 필요 |
| 기존 화면 레이아웃·색상·컴포넌트 변경 | ✅ 필요 |
| 애니메이션·트랜지션 추가 | ✅ 필요 |
| 버그 픽스 (화면 변화 없음) | ❌ 불필요 |
| 로직 리팩토링 (UI 변화 없음) | ❌ 불필요 |
| 텍스트/문구 변경 | ❌ 불필요 → architect LIGHT_PLAN 직행 |

### 문서 소유권

| 파일 계열 | 담당 에이전트 | 메인 Claude |
|---|---|---|
| `docs/architecture*.md`, `docs/domain-logic.md`, `docs/sdk.md` | **architect** | 수정 금지 |
| `docs/ui-spec*.md` | **designer** | 수정 금지 |
| `src/**` | **engineer** | 수정 금지 |
| `prd.md`, `trd.md` | **product-planner** | 수정 금지 |

---

## AI 개발 (MCP) — 선택사항

```bash
# [필요한 MCP 설정]
```
