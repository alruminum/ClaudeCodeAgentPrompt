# 버그픽스 루프 (Bugfix)

진입 조건: 버그 보고

---

## 재진입 상태 감지

버그픽스 루프 재진입 시 이전 실행의 완료 단계를 감지해 스킵한다.

```
진입 시 역순 체크:
  1. impl 파일 존재? → QA + architect 스킵 → engineer 직접 진입
  2. GitHub issue에 QA 리포트? → QA 스킵 → issue body를 qa_out으로 → architect
  3. 둘 다 없음 → QA부터 시작 (기본)
```

## 흐름

```
진입: bug 레이블 이슈 OR 유저 버그 직접 보고
      │
      ↓
  [재진입 감지] ─── impl 있음 ──→ engineer 직접 진입
      │               │
      │          QA 리포트 있음 ──→ architect부터
      │
      ↓ (신규)
  qa (원인 분석 + 타입 분류 + 이슈 등록 + 라우팅 추천)
      │ 원인 특정 3회 실패 → KNOWN_ISSUE → 메인 Claude 보고 후 대기
      │
      ↓ qa가 분류 결과에 따라 이슈 등록 (전 경로 공통)
      │
  ┌───┴──────────────────────────┐
  ↓                    ↓          ↓
architect 경유    engineer 직접   DESIGN_ISSUE
                  (구현 루프 미진입)  → 디자인 루프
SPEC_ISSUE        FUNCTIONAL_BUG
  │                    │
  ↓                    ↓
architect              architect
[Module Plan]          [Bugfix Plan(Mode F)]
  "버그픽스 —" 명시      경량 impl 작성
  │                    │
  ↓                    ↓
validator              engineer (코드 수정)
[Plan Validation]        │
  │                    vitest run (직접 실행)
  ↓                      │
→ 구현 루프 진입       validator [Bugfix Validation(Mode D)]
                         │
                     ┌───┴───┐
                   PASS     FAIL
                   │       → engineer 재시도 (max 2회)
                   ↓
                 commit
                 HARNESS_DONE
```

## qa 분류 → 분기 매핑

| qa 분류 | 경로 | 실행 단계 |
|---------|------|----------|
| FUNCTIONAL_BUG | engineer 직접 | architect Mode F → engineer → vitest → validator Mode D → commit |
| SPEC_ISSUE | architect 경유 | architect Mode B → validator Mode C → 구현 루프 |
| DESIGN_ISSUE | → 디자인 루프 | designer → design-critic |

## qa 이슈 등록 규칙

qa는 분석 완료 후 **모든 경로에서** GitHub 이슈를 등록한다.

| qa 분류 | 이슈 등록 위치 | 비고 |
|---------|---------------|------|
| FUNCTIONAL_BUG | Bugs 마일스톤 (라벨: `bug`) | 코드 버그 |
| SPEC_ISSUE (PRD 명세 있음) | Feature 마일스톤 (해당 epic 라벨) | PRD 명세 누락 구현. 본문에 해당 epic 경로 명시 |
| SPEC_ISSUE (PRD 명세 없음) | Feature 마일스톤 | 신규 요구사항 |
| DESIGN_ISSUE | Feature 마일스톤 | UI/UX 문제 |

---

## 마커 레퍼런스

### 인풋 마커 (이 루프에서 호출하는 @MODE)

| @MODE | 대상 에이전트 | 호출 시점 |
|---|---|---|
| `@MODE:QA:ANALYZE` | qa | 버그 접수 → 원인 분석 + 분류 |
| `@MODE:ARCHITECT:BUGFIX_PLAN` | architect | FUNCTIONAL_BUG → 경량 impl 작성 |
| `@MODE:ARCHITECT:MODULE_PLAN` | architect | SPEC_ISSUE → 구현 루프 경유 |
| `@MODE:ENGINEER:IMPL` | engineer | 코드 수정 |
| `@MODE:VALIDATOR:BUGFIX_VALIDATION` | validator | engineer 직접 경로 후 검증 |
| `@MODE:VALIDATOR:PLAN_VALIDATION` | validator | SPEC_ISSUE 경로 impl 검증 |

### 아웃풋 마커 (이 루프에서 발생하는 시그널)

| 마커 | 발행 주체 | 다음 행동 |
|------|-----------|-----------|
| `FUNCTIONAL_BUG` | qa | architect Bugfix Plan → engineer 직접 |
| `SPEC_ISSUE` | qa | architect Module Plan → 구현 루프 |
| `DESIGN_ISSUE` | qa | → 디자인 루프 |
| `KNOWN_ISSUE` | qa (3회 실패) | 메인 Claude 보고 후 대기 |
| `BUGFIX_PLAN_READY` | architect | engineer 코드 수정 |
| `BUGFIX_PASS` | validator | commit → HARNESS_DONE |
| `BUGFIX_FAIL` | validator | engineer 재시도 (max 2회) |
| `HARNESS_DONE` | harness | 메인 Claude 보고 |
