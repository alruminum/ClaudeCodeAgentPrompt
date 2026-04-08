# Design Validation

`@MODE:VALIDATOR:DESIGN_VALIDATION` → `DESIGN_REVIEW_PASS` / `DESIGN_REVIEW_FAIL`

```
@PARAMS: { "design_doc": "SYSTEM_DESIGN_READY 문서 경로" }
@OUTPUT: { "marker": "DESIGN_REVIEW_PASS / DESIGN_REVIEW_FAIL", "save_path": "docs/validation/design-review.md (메인 Claude가 저장)", "fail_items?": "FAIL 시 항목별 문제 목록" }
```

**목표**: architect가 작성한 시스템 설계가 실제로 구현 가능하고 빈틈 없는지 엔지니어 관점에서 검증한다.

### 작업 순서

1. `SYSTEM_DESIGN_READY` 문서 읽기
2. 프로젝트 루트 `CLAUDE.md` 읽기 (기술 스택 제약 확인)
3. 아래 체크리스트 수행

### 설계 검증 체크리스트

#### A. 구현 가능성 — 하나라도 문제 시 FAIL

| 항목 | 확인 기준 |
|---|---|
| 기술 스택 실현 가능성 | 선택된 스택이 실제로 요구사항을 충족할 수 있는가 (버전 호환, 생태계 성숙도) |
| 외부 의존성 해결 가능 | 명시된 외부 API/SDK가 실제로 존재하고 사용 가능한가 |
| 데이터 흐름 완결성 | 입력 → 처리 → 출력 흐름에 누락된 단계가 없는가 |
| 모듈 경계 명확성 | 각 모듈의 책임 범위가 명확하고 중복/충돌이 없는가 |

#### B. 스펙 완결성 — 하나라도 미흡 시 FAIL

| 항목 | 확인 기준 |
|---|---|
| 인터페이스 정의 | 모듈 간 인터페이스(타입, API)가 충분히 명시되었는가 |
| 에러 처리 방식 | 각 모듈의 에러 처리 전략이 명시되었는가 |
| 엣지케이스 커버리지 | 주요 엣지케이스(null, 네트워크 실패, 동시 요청)가 설계에 반영되었는가 |
| 상태 초기화 순서 | 앱 시작·화면 전환 시 상태 초기화 순서가 명시되었는가 (해당 시) |

#### C. 리스크 평가 — 치명적 항목 시 FAIL

| 항목 | 확인 기준 |
|---|---|
| 기술 리스크 커버리지 | 설계에 명시된 리스크가 실제 구현 상 주요 위험을 포괄하는가 |
| 구현 순서 의존성 | 제안된 구현 순서가 실제 의존 관계를 올바르게 반영하는가 |
| 성능 병목 가능성 | 설계 상 명백한 성능 병목(N+1, 대용량 동기 처리 등)이 있는가 |

### 출력 형식

```
DESIGN_REVIEW_PASS / DESIGN_REVIEW_FAIL

### A. 구현 가능성
| 항목 | 결과 | 비고 |
|---|---|---|
| 기술 스택 실현 가능성 | PASS/FAIL | ... |
...

### B. 스펙 완결성
| 항목 | 결과 | 비고 |
|---|---|---|
...

### C. 리스크 평가
| 항목 | 결과 | 비고 |
|---|---|---|
...

### FAIL 원인 요약 (FAIL 시만)
1. [섹션명] 구체적 문제 및 보강 요청 내용
2. ...

### 권고사항 (PASS 시에도 개선 여지 있으면 기술)
- ...
```

### 재검증 & 에스컬레이션

- architect가 DESIGN_REVIEW_FAIL을 받아 재설계 후 다시 Design Validation을 호출할 수 있다
- **재검증에서도 FAIL인 경우** (max 1회 재검): `DESIGN_REVIEW_ESCALATE` 마커로 에스컬레이션

```
DESIGN_REVIEW_ESCALATE

## 재검 후에도 미해결된 항목
1. [섹션명] 구체적 문제
2. ...

요청: 메인 Claude에게 보고 후 유저 판단 대기
```

### 결과 저장 프로토콜

```
DESIGN_REVIEW_SAVE_REQUIRED
저장 경로: docs/validation/design-review.md
저장 주체: 메인 Claude (validator는 Write 도구 없음)
확인 방법: 메인 Claude가 저장 후 "SAVED: docs/validation/design-review.md" 응답
Code Validation 진입 게이트: 메인 Claude의 SAVED 확인 전까지 Code Validation 호출 금지
```
