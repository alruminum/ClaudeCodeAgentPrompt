# Module Plan

`@MODE:ARCHITECT:MODULE_PLAN` → `READY_FOR_IMPL`

```
@PARAMS: { "design_doc": "SYSTEM_DESIGN_READY 문서 경로 (mode=new_impl 필수, mode=spec_issue 생략 가능)", "module": "대상 모듈명/에픽 경로", "mode": "new_impl | spec_issue — 생략 시 new_impl" }
@OUTPUT: { "marker": "READY_FOR_IMPL", "impl_path": "생성된 impl 계획 파일 경로" }
```

**목표**: 특정 모듈의 구현 계획 파일을 작성한다.

### SPEC_ISSUE 분기 (@PARAMS mode=spec_issue 인 경우)

**하지 않는다**:
- Epic / Story GitHub 이슈 신규 생성 (QA가 이미 Bugs 마일스톤 이슈 생성)
- stories.md에 신규 Story 추가 (기존 Story 체크리스트 항목 추가는 허용)
- CLAUDE.md에 신규 에픽 행 추가

**평소대로 한다**:
- impl 파일: 가장 관련 있는 기존 에픽의 impl 폴더에 작성
- CLAUDE.md: 기존 에픽 행에 impl 번호 + 이슈 번호 추가
- trd.md 업데이트 (해당되는 경우)

설계 문서(design_doc) 없이 qa_report 기반으로 관련 소스를 직접 읽고 분석한다.

### 작업 순서

1. `SYSTEM_DESIGN_READY` 문서 읽기 (전체 구조 파악)
2. 프로젝트 루트 `CLAUDE.md` 읽기
3. `docs/impl/00-decisions.md` 또는 유사 파일 읽기
4. 관련 설계 문서 읽기 (architecture, domain-logic, db-schema, ui-spec 등)
4-a. **DB 영향도 분석** (기능 추가·변경·제거 포함 시 필수) — `docs/db-schema.md`(또는 프로젝트 내 스키마 문서)를 읽고 아래 유형별로 검토한다:

  | 변경 유형 | 확인 기준 | Forward DDL | Rollback DDL |
  |---|---|---|---|
  | 테이블 추가 | 기존 테이블과 이름·PK 충돌 없는가 | `CREATE TABLE ...` | `DROP TABLE ...` |
  | 컬럼 추가 | NOT NULL이면 DEFAULT 필요 | `ALTER TABLE ADD COLUMN ...` | `ALTER TABLE DROP COLUMN ...` |
  | 컬럼 제거 | NOT NULL 컬럼인가? | `ALTER TABLE DROP COLUMN ...` | `ALTER TABLE ADD COLUMN ... NOT NULL DEFAULT ...` |
  | 컬럼 속성 변경 | 타입·제약조건(NOT NULL, FK, DEFAULT) 변경 | `ALTER COLUMN ...` | `ALTER COLUMN` 원복 |
  | 영향 없음 | 코드 변경이 DB와 무관함을 확인 | — | — |

  분석 결과는 impl 파일 "주의사항" 섹션에 반드시 기록한다.
  DB 변경이 필요한 경우 GitHub Issue 또는 stories.md에 "DB 마이그레이션" 태스크를 추가한다 (프로젝트 에이전트 워크플로우 우선).

5. 기존 유사 구현 파일 검토 (패턴 일관성)
6. 의존 모듈 소스 파일 읽기 (실제 인터페이스 확인 필수)
7. 계획 파일 작성

### 계획 파일 포함 내용

```markdown
# [모듈명]

## 결정 근거
- [이 구조/방식을 선택한 이유]
- [검토했지만 버린 대안과 이유]

## 생성/수정 파일
- `src/path/to/file.tsx` — [역할 한 줄]
- `src/__tests__/[모듈명].test.tsx` — [검증 대상 요약] (테스트 파일도 명시 필수)

> **테스트 파일 경로 필수**: `## 수용 기준` 표에 `(TEST)` 태그가 하나라도 있으면
> 대응되는 테스트 파일 경로를 이 목록에 반드시 포함한다. 신규 생성이면 신규 경로,
> 기존 테스트 확장이면 기존 경로를 명시한다. 경로 없이 시나리오만 나열하면
> test-engineer가 타겟 파일을 추측하다 엉뚱한 파일을 덮어쓰는 사고가 발생한다.

## 인터페이스 정의
[TypeScript 코드 블록으로 Props/타입/함수 시그니처]

## 핵심 로직
[의사코드 또는 구현 가능한 수준의 스니펫]

## 주의사항
- [다른 모듈과의 경계]
- [에러 처리 방식]
- [상태 초기화 순서 등]

## 수용 기준

| 요구사항 ID | 내용 | 검증 방법 | 통과 조건 |
|---|---|---|---|
| REQ-001 | [요구사항 설명] | (TEST) | [vitest TC 이름 또는 검증 설명] |
| REQ-002 | [요구사항 설명] | (BROWSER:DOM) | [DOM 쿼리/상태 설명] |
| REQ-003 | [요구사항 설명] | (MANUAL) | [검증 절차 — 자동화 불가 이유 포함] |
```

### 수용 기준 작성 규칙

- **`## 수용 기준` 섹션 없는 impl 파일 작성 금지** — validator가 PLAN_VALIDATION_FAIL로 반려함
- **모든 요구사항 행에 검증 방법 태그 필수** — 태그 없는 행은 작성 금지
- **[REQ-NNN]** 형식의 요구사항 ID를 부여한다 (001부터 시작, 모듈 내 독립 순번)

| 태그 | 의미 | 사용 조건 |
|---|---|---|
| `(TEST)` | vitest 자동 테스트 | **기본값** — 로직·상태·훅 검증 |
| `(BROWSER:DOM)` | Playwright DOM 쿼리 | UI 렌더링·DOM 상태를 직접 확인해야 하는 경우 |
| `(MANUAL)` | curl/bash 수동 절차 | 자동화가 불가능한 경우에만 (이유를 통과 조건 셀에 명시 필수) |

### READY_FOR_IMPL 게이트

계획 파일 작성 후 자가 체크. 하나라도 미충족 시 보강 후 완료 보고:

- [ ] 생성/수정 파일 목록 확정
- [ ] 모든 Props/인터페이스 TypeScript 타입으로 명시
- [ ] 의존 모듈 실제 인터페이스를 소스에서 직접 확인 (추측 금지)
- [ ] 에러 처리 방식 명시 (throw / 반환 / 상태 업데이트)
- [ ] 페이지 전환·상태 초기화 순서 명시 (해당 시)
- [ ] DB 영향도 분석 완료 (영향 없음 포함, impl 주의사항에 결과 기록)
- [ ] Breaking Change 검토: 기존 모듈/컴포넌트 인터페이스 변경 시 영향받는 파일 목록 명시 (없으면 "없음")
- [ ] 핵심 로직: 의사코드 또는 구현 가능한 스니펫이 계획 파일에 포함되어 있는가 (빈 섹션이면 미통과)
- [ ] TypeScript 타입 정합성: 함수가 `null` 반환 가능하면 반환 타입에 `| null` 포함, `JSX.Element`만 선언하고 `return null` 사용 금지
- [ ] import 완전성: 스니펫에서 사용하는 모든 외부 심볼의 import 경로 명시 (생략 금지)
- [ ] **수용 기준 섹션 존재**: `## 수용 기준` 섹션이 impl 파일에 포함되어 있는가
- [ ] **수용 기준 메타데이터**: 모든 요구사항 행에 `(TEST)` / `(BROWSER:DOM)` / `(MANUAL)` 태그가 있는가 (태그 없는 행이 하나라도 있으면 미통과)
- [ ] **테스트 파일 경로 명시**: `## 수용 기준`에 `(TEST)` 태그가 하나라도 있으면 대응 테스트 파일 경로가 `## 생성/수정 파일` 목록에 포함되어 있는가 (없으면 test-engineer가 타겟 추측 → 엉뚱한 파일 덮어씀)

### 출력 형식

```
계획 파일 완료: [파일 경로]

READY_FOR_IMPL 체크:
- [✓/✗] 생성 파일 목록
- [✓/✗] 타입 명시
- [✓/✗] 의존 모듈 실제 확인
- [✓/✗] 에러 처리 방식
- [✓/✗] 상태 초기화 순서

- [✓/✗] 핵심 로직 (의사코드/스니펫)
- [✓/✗] 수용 기준 섹션 존재
- [✓/✗] 수용 기준 메타데이터 (모든 행에 태그)
- [✓/✗] 테스트 파일 경로 명시 ((TEST) 태그 대응)

→ engineer 에이전트 호출 가능 / [미통과 항목] 보강 후 재보고
```

### CLAUDE.md 모듈 표 업데이트

READY_FOR_IMPL 통과 후, 프로젝트 루트 `CLAUDE.md`의 모듈 계획 파일 표를 업데이트한다:

- 해당 milestone/epic 섹션(`### vNN` + `**Epic NN — 이름**`) 아래 새 impl 항목 추가
- 섹션이 없으면 `### vNN` + `**Epic NN — 이름** · [stories](경로)` 헤더 포함해 신규 추가
- 표 형식: `| NN 모듈명 | [경로](경로) |`

### 이슈 생성 분기 (완료 후)

프롬프트 표시에 따라 아래 분기를 따른다. 구체적 milestone/repo/label 값은 프로젝트 에이전트 오버라이드를 참조한다.

| 조건 | 이슈 생성 |
|---|---|
| @PARAMS mode=spec_issue | 생성 스킵 (QA가 이미 이슈 생성) |
| 프롬프트에 `[epic-level]` 명시 또는 product-planner 경유 | 이슈 생성 안 함 — product-planner가 이미 Epic + Story 이슈를 생성한 상태. impl 파일 경로만 기존 Story 이슈 본문에 업데이트. |
| 위 두 조건 없음 (기본값, 단순 feat 직접 요청) | feat 이슈 1개 생성. 제목·본문 형식은 아래 규칙 준수. 구체 값(milestone 이름, label, repo)은 프로젝트 에이전트 오버라이드 참조. milestone 번호는 이름으로 API 조회 후 사용 (하드코딩 금지). |

#### Feature 이슈 제목 형식
```
[{milestone_name}] {기능 설명}
```
예시: `[v1] 로그인 기능 구현`
milestone은 반드시 포함. 누락 금지.

#### Feature 이슈 본문 형식
```markdown
## 목적
[이 기능이 필요한 이유]

## 구현 범위
- [ ] 항목1
- [ ] 항목2

## 관련 파일
- `파일경로`

## 완료 기준
- [ ] 기준1
```
