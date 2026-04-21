# Plan Validation

`@MODE:VALIDATOR:PLAN_VALIDATION` → `PLAN_VALIDATION_PASS` / `PLAN_VALIDATION_FAIL`

```
@PARAMS: { "impl_path": "impl 계획 파일 경로" }
@OUTPUT: { "marker": "PLAN_VALIDATION_PASS / PLAN_VALIDATION_FAIL", "fail_items?": "미충족 항목 목록 (FAIL 시)" }
```

**목표**: architect가 작성한 impl 계획 파일이 구현에 착수하기에 충분한지 검증한다. 구현 루프 진입 전 공통 게이트.

### 작업 순서

1. impl 계획 파일 읽기 (`docs/milestones/vNN/epics/epic-NN-*/impl/NN-*.md`)
2. 프로젝트 루트 `CLAUDE.md` 읽기 (기술 스택, 제약 확인)
3. 관련 설계 문서 읽기 (architecture, domain-logic, db-schema 등)
4. 의존 모듈 소스 파일 읽기 (인터페이스 실재 여부 확인)
5. 아래 체크리스트 수행

### Plan Validation 체크리스트

#### A. 구현 충분성 — 하나라도 미충족 시 FAIL

| 항목 | 확인 기준 |
|---|---|
| 생성/수정 파일 목록 | 구체적 파일 경로가 명시되어 있는가 |
| 인터페이스 정의 | TypeScript 타입/Props/함수 시그니처가 명시되어 있는가 |
| 핵심 로직 | 의사코드 또는 구현 가능한 스니펫이 존재하는가 (빈 섹션이면 FAIL) |
| 에러 처리 방식 | throw/반환/상태 업데이트 중 어떤 전략인지 명시되어 있는가 |
| 의존 모듈 실재 | 계획이 참조하는 모듈/함수가 실제 소스에 존재하는가 |

#### B. 정합성 — 하나라도 불일치 시 FAIL

| 항목 | 확인 기준 |
|---|---|
| 설계 문서 일치 | 계획이 architecture/domain-logic 문서와 모순되지 않는가 |
| DB 영향도 | DB 조작이 있으면 영향도 분석이 포함되어 있는가 |
| 병렬 impl 충돌 | 같은 에픽의 다른 impl이 동일 파일을 수정하는 경우 순서가 명시되어 있는가 |

#### C. 수용 기준 메타데이터 감사 — 하나라도 미충족 시 PLAN_VALIDATION_FAIL (구현 진입 차단)

| 항목 | 확인 기준 |
|---|---|
| 수용 기준 섹션 존재 | impl 파일에 `## 수용 기준` 섹션이 있는가 (섹션 자체 없으면 즉시 FAIL) |
| 요구사항 ID 부여 | 각 행에 `REQ-NNN` 형식의 ID가 있는가 |
| 검증 방법 태그 | 각 행에 `(TEST)` / `(BROWSER:DOM)` / `(MANUAL)` 중 하나 이상 있는가 |
| MANUAL 사유 | `(MANUAL)` 태그 사용 시 자동화 불가 이유가 통과 조건 셀에 명시되어 있는가 |
| 테스트 파일 경로 명시 | `(TEST)` 태그가 하나라도 있으면 대응 테스트 파일 경로(`.test.tsx`/`.spec.ts` 등)가 `## 생성/수정 파일` 목록에 포함되어 있는가 (없으면 test-engineer가 타겟 추측해 엉뚱한 파일 덮어쓰는 사고 발생) |

> C에서 FAIL 발견 시 → `PLAN_VALIDATION_FAIL` (SPEC_GAP 반려). architect가 `## 수용 기준` 섹션 보강 후 재검증.
> 메타데이터 누락은 "스펙 불완전"으로 간주하며 engineer 진입을 차단한다.

### 판정 기준

- **PLAN_VALIDATION_PASS**: A/B/C 모두 통과
- **PLAN_VALIDATION_FAIL**: A, B, C 중 하나라도 미충족
- PARTIAL 판정 금지

### 재검증 & 에스컬레이션

- architect 재보강 후 재검증 **최대 1회**
- 재검증에서도 FAIL → `PLAN_VALIDATION_ESCALATE` 마커로 메인 Claude에 에스컬레이션

### 출력 형식

```
PLAN_VALIDATION_PASS / PLAN_VALIDATION_FAIL

### A. 구현 충분성
| 항목 | 결과 | 비고 |
|---|---|---|
| 생성/수정 파일 목록 | PASS/FAIL | ... |
...

### B. 정합성
| 항목 | 결과 | 비고 |
|---|---|---|
...

### C. 수용 기준 메타데이터
| 항목 | 결과 | 비고 |
|---|---|---|
| 수용 기준 섹션 존재 | PASS/FAIL | ... |
| 요구사항 ID 부여 | PASS/FAIL | ... |
| 검증 방법 태그 | PASS/FAIL | 태그 없는 항목: [목록] |
| MANUAL 사유 | PASS/FAIL/N/A | ... |
| 테스트 파일 경로 명시 | PASS/FAIL/N/A | (TEST) 태그 없으면 N/A |

### FAIL 원인 요약 (FAIL 시만)
1. [구체적 미충족 항목 + 보강 요청]
2. ...
```
