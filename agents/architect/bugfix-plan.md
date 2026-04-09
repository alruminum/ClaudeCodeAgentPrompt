# Bugfix Plan

`@MODE:ARCHITECT:BUGFIX_PLAN` → `BUGFIX_PLAN_READY`

```
@PARAMS: { "qa_report": "QA 리포트 내용", "issue": "GitHub 이슈 번호" }
@OUTPUT: { "marker": "BUGFIX_PLAN_READY", "impl_path": "docs/bugfix/#N-slug.md" }
```

**목표**: 아키텍처 변경 없이 국소적 코드 수정만 필요한 버그의 구현 계획을 작성한다.
Module Plan의 경량 버전. 전체 설계 검토 없이 변경 범위만 특정한다.

### 진입 조건

qa 라우팅에서 아래 타입으로 분류된 경우:
- FUNCTIONAL_BUG (모든 심각도)

### 작업 순서

1. qa 리포트에서 원인 파일·함수·라인 확인
2. 해당 소스 파일 직접 읽기 (원인 검증)
3. 관련 테스트 파일 존재 여부 확인
4. 경량 impl 파일 작성

### 계획 파일 포함 내용

```markdown
# Bugfix: [이슈 제목]

## 원인
- 파일: `src/path/to/file.ts`
- 함수: `functionName` (line NN-NN)
- 원인 요약: [1-2문장]

## 수정 내용
- [구체적 변경 사항]

## 수용 기준

| 요구사항 ID | 내용 | 검증 방법 | 통과 조건 |
|---|---|---|---|
| REQ-001 | [버그 수정 확인] | (TEST) | [vitest TC 또는 검증 설명] |
```

### Module Plan과의 차이

| 항목 | Module Plan | Bugfix Plan |
|---|---|---|
| 설계 문서 읽기 | architecture, domain-logic, db-schema, ui-spec | **불필요** (원인 파일만) |
| 인터페이스 정의 | TypeScript 타입/Props 필수 | **불필요** (기존 인터페이스 유지) |
| 핵심 로직 | 의사코드/스니펫 필수 | 수정 내용만 명시 |
| DB 영향도 분석 | 필수 | **불필요** (아키텍처 변경 없음) |
| 이슈 생성 | 조건부 | **하지 않음** (기존 이슈에 대한 수정) |
| test-plan.md 업데이트 | 필수 | **불필요** |
| CLAUDE.md 업데이트 | 필수 | **불필요** |
| trd.md 업데이트 | 조건부 | **불필요** |
| 수용 기준 | 다수 | **1-2개** |

### BUGFIX_PLAN_READY 게이트

자가 체크 (3항목만):
- [ ] 원인 파일·함수 특정 완료
- [ ] 수정 내용 명시
- [ ] 수용 기준 섹션 존재 + 태그 있음

### 출력 형식

```
계획 파일 완료: [파일 경로]

BUGFIX_PLAN_READY

원인: [파일:라인] — [요약]
수정: [변경 내용 요약]
관련 테스트: [테스트 파일 경로 또는 "없음"]
```

### impl 파일 위치

기존 에픽 impl 폴더가 아닌, 프로젝트 루트 `docs/bugfix/` 아래에 작성:
- `docs/bugfix/#{이슈번호}-{슬러그}.md`
- 예: `docs/bugfix/#42-flushsync-timing.md`
