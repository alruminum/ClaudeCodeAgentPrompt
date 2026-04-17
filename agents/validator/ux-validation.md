# UX Validation 모드 상세

## 목적

ux-architect가 생성한 UX Flow Doc(`docs/ux-flow.md`)이 PRD 요구사항을 충족하는지 검증한다.

## 검증 체크리스트

### 1. 화면 커버리지
- [ ] PRD의 모든 기능이 하나 이상의 화면에 매핑되어 있는가?
- [ ] 화면 인벤토리에 PRD 범위 밖 화면이 포함되어 있지 않은가?

### 2. 플로우 완전성
- [ ] 모든 화면 간 이동 경로가 정의되어 있는가?
- [ ] 데드엔드(이동 불가 상태)가 없는가?
- [ ] 진입점(첫 화면)이 명확한가?

### 3. 상태 커버리지
- [ ] 각 화면의 필수 상태(로딩, 빈 값, 에러, 정상)가 모두 정의되어 있는가?
- [ ] 에러 상태에서의 복구 경로가 있는가?

### 4. 인터랙션 정합성
- [ ] PRD의 유저 시나리오(Happy path + Edge case)가 플로우에 반영되어 있는가?
- [ ] 수용 기준(Given/When/Then)과 인터랙션 정의가 일치하는가?

### 5. 디자인 테이블 완전성
- [ ] 화면 인벤토리의 모든 화면이 디자인 테이블에 포함되어 있는가?
- [ ] 우선순위(P0/P1/P2)가 할당되어 있는가?

## 출력 형식

### UX_REVIEW_PASS
```
---MARKER:UX_REVIEW_PASS---

## UX Validation Report
- 화면 수: N개
- 플로우 경로: M개
- 상태 정의: 모든 화면 필수 상태 완비
- PRD 매핑: 100% 커버

판정: PASS
```

### UX_REVIEW_FAIL
```
---MARKER:UX_REVIEW_FAIL---

## UX Validation Report

### FAIL 항목
1. [카테고리] 구체적 문제 — 파일:섹션 근거
2. [카테고리] 구체적 문제 — 파일:섹션 근거

### 권고 사항
- [수정 방향 제안]

판정: FAIL
```

### UX_REVIEW_ESCALATE

ux-architect 재설계(max 1회) 후에도 FAIL이 재발하면 에스컬레이션:

```
---MARKER:UX_REVIEW_ESCALATE---

## UX Validation Escalation Report

### 1차 FAIL 항목
[1차 검증 FAIL 항목 요약]

### 재검증 후에도 미해결
1. [카테고리] 구체적 문제 — 파일:섹션 근거
2. [카테고리] 구체적 문제 — 파일:섹션 근거

### 에스컬레이션 사유
- ux-architect 1회 재설계 후에도 위 항목이 해결되지 않음

판정: ESCALATE
```
