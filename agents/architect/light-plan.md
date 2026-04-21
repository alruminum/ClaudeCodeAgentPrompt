# Light Plan

`@MODE:ARCHITECT:LIGHT_PLAN` → `LIGHT_PLAN_READY`

```
@PARAMS: { "suspected_files": "관련 파일 경로 (grep 결과 또는 DESIGN_HANDOFF 대상)", "issue_summary": "GitHub 이슈 제목+본문", "labels": "GitHub 이슈 라벨 목록", "issue": "GitHub 이슈 번호" }
@OUTPUT: { "marker": "LIGHT_PLAN_READY", "impl_path": "docs/bugfix/#N-slug.md", "depth": "frontmatter depth: simple|std|deep 선언 필수" }
```

**목표**: 아키텍처 변경 없이 국소적 코드 수정만 필요한 작업의 구현 계획을 작성한다.
Module Plan의 경량 버전. 전체 설계 검토 없이 변경 범위만 특정한다.

적용 범위:
- **버그 수정** (FUNCTIONAL_BUG): QA가 특정한 원인 파일 기반 수정
- **디자인 반영** (DESIGN_HANDOFF): designer 시안을 코드에 적용하는 국소 변경

### 진입 조건

아래 경로 중 하나로 진입:
- QA 라우팅: FUNCTIONAL_BUG로 분류된 경우
- DESIGN_HANDOFF: designer 시안 확정 후 구현 요청
- REVIEW_FIX: pr-reviewer MUST FIX 피드백 재반영 (아키텍처 변경 없는 국소 수정)
- DOCS_UPDATE: 텍스트/스타일 등 behavior 불변 변경 (depth=simple 자동)

> 공통 성격: 아키텍처 변경 없음, 국소적 (1~4 파일), 새 설계 결정 없음.
> 새 설계가 필요하면 MODULE_PLAN으로 승격.

### 작업 순서

1. 이슈에서 변경 대상 파일·컴포넌트 확인
   - 버그: qa 리포트의 원인 파일·함수·라인
   - 디자인: DESIGN_HANDOFF 패키지의 대상 화면·컴포넌트
2. 해당 소스 파일 직접 읽기 (변경 범위 검증)
3. **관련 테스트 파일 탐색 + 수정 범위 포함** (필수)
   - 수정 대상 함수/모듈의 테스트 파일을 Glob/Grep으로 탐색
   - 테스트가 변경되는 동작을 assert하고 있으면 → **반드시 `## 수정 파일`에 포함**
   - scope_violation autocheck은 impl에 없는 파일 변경을 차단함. 테스트 누락 = 루프 실패
4. 경량 impl 파일 작성

### 계획 파일 포함 내용

```markdown
# [이슈 제목]

## 변경 대상
- 파일: `src/path/to/file.ts`
- 컴포넌트/함수: `componentName` (line NN-NN)
- 요약: [1-2문장 — 무엇을 왜 바꾸는지]

## 수정 내용
- [구체적 변경 사항]

## 수용 기준

| 요구사항 ID | 내용 | 검증 방법 | 통과 조건 |
|---|---|---|---|
| REQ-001 | [변경 확인] | (TEST) | [vitest TC 또는 검증 설명] |
```

### Module Plan과의 차이

| 항목 | Module Plan | Light Plan |
|---|---|---|
| 설계 문서 읽기 | architecture, domain-logic, db-schema, ui-spec | **불필요** (대상 파일만) |
| 인터페이스 정의 | TypeScript 타입/Props 필수 | **불필요** (기존 인터페이스 유지) |
| 핵심 로직 | 의사코드/스니펫 필수 | 수정 내용만 명시 |
| DB 영향도 분석 | 필수 | **불필요** (아키텍처 변경 없음) |
| 이슈 생성 | 조건부 | **하지 않음** (기존 이슈에 대한 수정) |
| CLAUDE.md 업데이트 | 필수 | **불필요** |
| trd.md 업데이트 | 조건부 | **불필요** |
| 수용 기준 | 다수 | **1-2개** |

### LIGHT_PLAN_READY 게이트

자가 체크 (4항목):
- [ ] 변경 대상 파일·컴포넌트 특정 완료
- [ ] 수정 내용 명시
- [ ] **변경 동작을 assert하는 테스트 파일이 수정 범위에 포함됨** (또는 관련 테스트 없음 확인)
- [ ] 수용 기준 섹션 존재 + 태그 있음

### 출력 형식

```
계획 파일 완료: [파일 경로]

LIGHT_PLAN_READY

대상: [파일:라인 또는 컴포넌트] — [요약]
수정: [변경 내용 요약]
관련 테스트: [테스트 파일 경로 또는 "없음"]
```

### impl 파일 위치

기존 에픽 impl 폴더가 아닌, 프로젝트 루트 `docs/bugfix/` 아래에 작성:
- `docs/bugfix/#{이슈번호}-{슬러그}.md`
- 예: `docs/bugfix/#42-flushsync-timing.md`
