# 오케스트레이션 루프 갭 분석 리포트

> 작성일: 2026-04-09
> 대상: `orchestration/*.md` (5개) + `orchestration-rules.md`
> 방법: 에이전트 @MODE/@PARAMS/@OUTPUT 정의 ↔ 루프 다이어그램 ↔ 마커 테이블 ↔ 정책 교차 검증

---

## A. 다이어그램 ↔ 테이블 모순 (6건)

### A-1. impl.md — `fast` depth 시퀀스에 pr-reviewer 포함

| 위치 | 내용 |
|------|------|
| depth 테이블 (line 11) | `fast: engineer → validator → pr-reviewer → commit → merge (테스트·보안 스킵)` |
| Mermaid DEPTH_CHK | `DEPTH_CHK -->|"std/fast"| COMMIT` (pr-reviewer 스킵) |
| 머지 조건 테이블 (rules line 206) | fast → 없음 (pr_reviewer_lgtm 불필요) |

**모순**: depth 테이블은 fast에 pr-reviewer를 포함하지만, 다이어그램과 머지 조건은 스킵.
fast의 올바른 시퀀스는 `engineer → validator → commit → merge` (LLM 2회).

### A-2. bugfix.md — KNOWN_ISSUE 발동 임계값 불일치

| 위치 | 임계값 |
|------|--------|
| bugfix.md 다이어그램 KI 노드 (line 31) | `원인 특정 3회 실패` |
| orchestration-rules.md 에스컬레이션 테이블 (line 36) | `1회 분석으로 원인 특정 불가` |

**모순**: qa가 몇 회 시도 후 KNOWN_ISSUE를 발행하는지 기준이 다름. 하나로 통일 필요.

### A-3. bugfix.md — BUGFIX_PLAN_READY 마커 누락

마커 테이블 (line 118)에 `BUGFIX_PLAN_READY | architect | engineer 코드 수정`이 있으나,
Mermaid 다이어그램에는 ARC_BF → ENG 직결. 중간 마커 노드 없음.

### A-4. orchestration-rules.md — VALIDATION_ESCALATE 미사용

에스컬레이션 테이블 (line 34): `VALIDATION_ESCALATE | validator Code Validation (3회 초과)`.
그러나 impl.md에서 validator CODE_VALIDATION FAIL은 FAIL_ROUTE → attempt++ 경로를 탐.
3회 초과 시 IMPLEMENTATION_ESCALATE (harness 발행). VALIDATION_ESCALATE는 어느 루프에서도 사용 안 됨.

### A-5. orchestration-rules.md — REVIEW_LOOP_ESCALATE 미사용

에스컬레이션 테이블 (line 35): `REVIEW_LOOP_ESCALATE | pr-reviewer (3라운드 초과)`.
impl.md에서 pr-reviewer CHANGES_REQUESTED → FAIL_ROUTE → attempt++ → 3회 이후 IMPLEMENTATION_ESCALATE.
pr-reviewer 자체적으로 3라운드를 세는 별도 루프가 다이어그램에 없음.

### A-6. orchestration-rules.md — PLAN_DONE 유저 게이트 미사용

정책 3 유저 게이트 (line 65): `PLAN_DONE | 유저 결정 전 다음 단계 진입 금지`.
**어느 루프 다이어그램에도 PLAN_DONE 마커가 등장하지 않음.** 발행 주체·소비 위치 불명.

---

## B. 누락된 흐름 / 불명확한 분기 (8건)

### B-1. design.md — UX_REDESIGN 전체 플로우 누락 ★

마커 테이블에 다음이 등록되어 있으나 Mermaid 다이어그램에는 해당 흐름이 전혀 없음:

| 등록되어 있으나 다이어그램 없음 |
|------|
| `@MODE:DESIGNER:UX_REDESIGN` (인풋) |
| `@MODE:CRITIC:UX_SHORTLIST` (인풋) |
| `UX_REDESIGN_SHORTLIST` (아웃풋) |

designer가 5개 와이어프레임 생성 → design-critic UX_SHORTLIST로 3개 선별 → designer Stitch 렌더링의 **전체 경로가 다이어그램에서 빠져 있음**. DEFAULT/FIGMA 흐름만 존재.

### B-2. impl.md — fast depth 테스트 스킵 경로 미반영

다이어그램에서 SRC_CHK → YES는 무조건 TE (test-engineer) 진입. depth에 따른 분기가 없음.
fast depth는 test-engineer와 vitest를 스킵해야 하는데, 다이어그램에는 이 분기 노드가 없음.
(하네스 스크립트 레벨에서 처리될 수 있으나 다이어그램 명세로는 불명확)

### B-3. impl.md — TE_SELF 자체 수정 한도 초과 시 종착점 없음

`TE_SELF["test-engineer 자체 수정\n(max 2회, attempt 불변)"]` → TE로만 재연결.
**max 2회 초과 후 어디로 가는지 미정의.** FAIL_ROUTE? IMPLEMENTATION_ESCALATE? 경로 없음.

### B-4. bugfix.md — ENG_RETRY 한도 초과 시 에스컬레이션 없음

`ENG_RETRY["engineer 재시도\n(max 2회)"]` → ENG로만 재연결.
**max 2회 초과 후 에스컬레이션 경로 없음.** impl.md에는 `attempt >= 3 → IMPL_ESC`가 있으나 bugfix에는 없음.

### B-5. bugfix.md — SPEC_ISSUE 경로의 VAL_PV 실패 분기 없음

`ARC_MP --> VAL_PV --> IMPL_ENTRY` 직결. VAL_PV에서 PLAN_VALIDATION_FAIL 시 어떻게 되는지 미정의.
plan.md에는 PVF → ARC_RE (재보강 max 1회) → PVE (에스컬레이션) 경로가 있으나 bugfix에는 없음.

### B-6. bugfix.md — merge 단계 누락

impl.md: `COMMIT → MERGE → 충돌 시 MCE / 성공 시 HD`
bugfix.md: `COMMIT → HD` (merge 없이 직결)

orchestration-rules.md 브랜치 전략에 따르면 bugfix도 feature branch 사용 → merge 필요.
`bugfix 머지 조건: validator_b_passed` (rules line 209). merge 단계 다이어그램에 반영 필요.

### B-7. tech-epic.md — Plan Validation 없이 impl 진입

`ARC_MP ×N → RFI ×N → SEQ → IMPL_ENTRY`

Module Plan이 impl 파일을 생성하지만, Plan Validation을 거치지 않고 바로 IMPL_ENTRY.
plan.md에서는 Module Plan → IMPL_GATE → VAL_PV → RFI 경로가 있음.

> 참고: impl.md 재진입 감지에서 plan_validation_passed 미설정 시 자동으로 VAL_PV를 수행하므로,
> impl 루프 내부에서 암묵적으로 처리될 수 있음. 그러나 tech-epic 다이어그램에 명시되어 있지 않아 불명확.

### B-8. tech-epic.md — 순차 실행(×N) 중 실패 처리 미정의

SEQ 노드가 N개 impl을 순차 실행하지만, 중간에 IMPLEMENTATION_ESCALATE가 발생하면:
- 나머지 impl 계속 진행?
- 전체 중단?
- 실패 건만 스킵?

어떤 전략인지 다이어그램·본문 어디에도 정의 없음.

---

## C. 루프 간 일관성 이슈 (4건)

### C-1. Plan Validation 적용 불일치

| 루프 | Module Plan → Plan Validation? |
|------|------|
| plan.md (EPIC=NO 경로) | ✅ ARC_MP → IMPL_GATE → VAL_PV |
| plan.md (SCOPE=NO 경로) | ❌ ARC_MP_SKIP → RFI (VAL_PV 스킵) |
| tech-epic.md | ❌ ARC_MP → RFI (VAL_PV 스킵, impl 재진입에 암묵 의존) |
| design.md | ❌ ARC_MP → RFI (VAL_PV 스킵) |
| bugfix.md (SPEC_ISSUE) | ✅ ARC_MP → VAL_PV → IMPL_ENTRY |

**같은 architect MODULE_PLAN 호출인데 Plan Validation 적용 여부가 루프마다 다름.**
의도적 설계라면 각 루프에 "Plan Validation 스킵 사유" 주석 필요.
비의도적이라면 통일 필요.

### C-2. 정책 8 수용 기준 메타데이터 감사 — 다이어그램 미반영

orchestration-rules.md 정책 8 (line 90-112):
```
validator [Plan Validation]
  ↓ PASS
validator [수용 기준 메타데이터 감사]  ← 정책 8 게이트
  태그 없는 요구사항 → PLAN_VALIDATION_FAIL
  ↓ PASS
READY_FOR_IMPL
```

**이 2단계 검증이 어느 루프 다이어그램에도 반영되어 있지 않음.**
Plan Validation과 메타데이터 감사가 validator 내부에서 한 번에 처리되는 것인지,
별도 호출인지 불명확.

### C-3. bugfix.md — test-engineer 부재

| 루프 | 테스트 작성자 |
|------|--------------|
| impl.md | test-engineer (별도 에이전트) → vitest (ground truth) |
| bugfix.md | (없음) → vitest (직접 실행) |

bugfix에서 테스트는 누가 작성하는가?
- engineer가 수정 코드 + 테스트를 동시에 작성?
- 기존 테스트만으로 검증?
- 의도적으로 test-engineer를 생략한 것이라면 사유 명시 필요.

### C-4. READY_FOR_IMPL 발행 주체 혼재

| 경로 | 실질 발행 주체 |
|------|--------------|
| plan.md ARC_MP_SKIP | architect (MODULE_PLAN 직접) |
| plan.md IMPL_GATE | validator PVP → RFI (validator 체인) |
| tech-epic.md | architect (MODULE_PLAN 직접) |
| design.md | architect (MODULE_PLAN 직접) |

마커 테이블에서 `READY_FOR_IMPL`의 발행 주체는 일관되게 "architect"로 기재되어 있으나,
plan.md의 IMPL_GATE 경로에서는 validator가 PLAN_VALIDATION_PASS를 발행한 후 RFI에 도달.
실질적으로 "누가" RFI를 발행하는지 경로마다 다름.

---

## D. 경미한 이슈 (3건)

### D-1. design.md — IMPL_CHK 판단 주체 미명시

`IMPL_CHK{{"impl 파일 영향 있음?"}}` — 누가 판단하는가? 메인 Claude? 자동 감지?
plan.md의 `SCOPE{{"메인 Claude 판단"}}`, `EPIC{{"메인 Claude 판단"}}`과 달리 주체 미기재.

### D-2. design.md — FLAG 파일 네이밍의 {prefix} 미정의

`/tmp/{prefix}_design_critic_passed` — prefix 규칙 미정의. 다른 루프의 플래그 파일과 충돌 가능성.

### D-3. impl.md — vitest 실패 시 fail_type 미지정

실패 유형별 수정 전략 테이블에 `test_fail`이 있으나, 다이어그램의 `VITEST -->|실패| FAIL_ROUTE`에서
이 fail_type이 자동 지정되는지, 하네스가 설정하는지 불명확.
test-engineer IMPLEMENTATION_BUG와 vitest 직접 실패의 fail_type이 동일(`test_fail`)인지도 미정의.

---

## 요약 대시보드

| 카테고리 | 건수 | 심각도 |
|----------|------|--------|
| A. 다이어그램 ↔ 테이블 모순 | 6 | 🔴 높음 (명세 불일치) |
| B. 누락된 흐름 / 불명확 분기 | 8 | 🔴 높음 (실행 불가 경로) |
| C. 루프 간 일관성 | 4 | 🟡 중간 (의도 확인 필요) |
| D. 경미한 이슈 | 3 | 🟢 낮음 (명확화 수준) |
| **합계** | **21** | |

### Top 5 우선 수정 권장

1. **B-1** design.md UX_REDESIGN 플로우 누락 — 마커 테이블에 등록된 3개 마커의 흐름이 통째로 없음
2. **C-1** Plan Validation 적용 일관성 — 같은 MODULE_PLAN인데 루프마다 검증 유무가 다름
3. **A-1** impl.md fast depth 테이블 오류 — pr-reviewer 포함/제외가 모순
4. **B-4** bugfix.md ENG_RETRY 에스컬레이션 누락 — 무한 루프 가능
5. **B-6** bugfix.md merge 단계 누락 — 브랜치 전략과 불일치
