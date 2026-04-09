# 오케스트레이션 루프 최종 통합 리뷰

> 작성일: 2026-04-09
> 대상: Plan / Tech Epic / Impl / Bugfix 루프 (Design 제외)
> 방법: 4개 독립 리뷰 → 교차 검증 → 통합
> 벤치마크: Google CL/Presubmit/TAP, Meta Phabricator/Sandcastle/SEV

---

## 1. 루프별 리뷰 요약

| 루프 | 발견 건수 | P0 | P1 | P2+ | 핵심 이슈 |
|------|-----------|----|----|-----|-----------|
| Plan | 17 | 2 | 5 | 10 | Plan Validation 바이패스, PLAN_DONE 미사용 |
| Tech Epic | 15 | 3 | 3 | 9 | Plan Validation 누락, ×N 실패 전략 부재, 유저 게이트 누락 |
| Impl | 16 | 2 | 3 | 11 | 단일 attempt 카운터 문제, TE_SELF 무한루프, fast depth 모순 |
| Bugfix | 19 | 3 | 4 | 12 | ENG_RETRY 에스컬레이션 없음, merge 누락, test-engineer 부재 |
| **합계** | **67** | **10** | **15** | **42** | |

> 상세: [plan-loop-review.md](plan-loop-review.md) · [tech-epic-loop-review.md](tech-epic-loop-review.md) · [impl-loop-review.md](impl-loop-review.md) · [bugfix-loop-review.md](bugfix-loop-review.md)

---

## 2. 교차 검증 — 루프 간 공통 패턴

4개 리뷰를 교차 검증한 결과, 개별 루프가 아닌 **시스템 전체** 수준의 구조적 이슈 6건을 식별했다.

### CP-1. Plan Validation 적용 불일치 — 시스템 설계 결함

**4개 리뷰 모두**에서 지적. 동일한 `@MODE:ARCHITECT:MODULE_PLAN` 호출인데 검증 유무가 루프마다 다르다.

| 경로 | Plan Validation |
|------|:---:|
| plan.md EPIC=YES/NO | ✅ |
| plan.md SCOPE=NO (ARC_MP_SKIP) | ❌ |
| tech-epic.md ARC_MP ×N | ❌ |
| design.md ARC_MP (DESIGN_HANDOFF 후) | ❌ (리뷰 대상 외이나 동일 패턴) |
| bugfix.md SPEC_ISSUE | ✅ |

**판단**: MODULE_PLAN의 출력물(impl 파일)은 동일한 검증이 필요하다. Plan Validation을 스킵하면 정책 8(수용 기준 메타데이터)도 자동 미적용. 이는 "빠른 경로"가 아니라 **게이트 우회**.

**권장**: MODULE_PLAN 호출 후에는 예외 없이 Plan Validation 필수. 경량화가 필요하면 validator에 `--quick` 모드를 추가하되 게이트 자체를 제거하지 않는다. Google/Meta 모두 리뷰 강도는 조절하되 리뷰 자체를 스킵하지 않는다.

### CP-2. 에스컬레이션 = 데드엔드 — 복귀 경로 전무

Plan 리뷰(B-3)에서 지적. **모든 루프**의 에스컬레이션 노드(`DRE`, `PVE`, `IMPL_ESC`, `KNOWN_ISSUE` 등)가 다이어그램에서 종착점이다. 에스컬레이션 후 유저가 어떤 선택지를 가지는지 정의되어 있지 않다.

Google에서 에스컬레이션은 3-way 분기: `재시도 / 설계 롤백 / 중단`. Meta SEV에서도 `fix forward / revert / mitigate`.

**권장**: 각 에스컬레이션 노드에 유저 선택 분기를 추가하되, 공통 패턴으로 표준화:
```
ESCALATION → USER_DECIDE
  → "재시도 (카운터 리셋)" → 이전 단계
  → "이전 페이즈 롤백" → 상위 에이전트
  → "중단" → END
```

### CP-3. 유저 게이트 정책(정책 3)과 다이어그램 불일치

| 정책 3 게이트 | plan | tech-epic | impl | bugfix |
|---|:---:|:---:|:---:|:---:|
| READY_FOR_IMPL | ✅ | ❌ (G-5) | ✅ (진입 조건) | N/A |
| PLAN_DONE | ❌ (G-2) | ❌ | N/A | N/A |
| HARNESS_DONE | N/A | N/A | ✅ | ✅ |
| DESIGN_HANDOFF | (design 루프) | N/A | N/A | N/A |
| PLAN_VALIDATION_PASS | ✅ | ❌ (Plan Val 자체 없음) | N/A | ✅ (SPEC_ISSUE) |

**판단**: 정책 3은 5개 유저 게이트를 정의하지만, 루프 다이어그램에 일관되게 반영되지 않았다. 특히 tech-epic에서 READY_FOR_IMPL 유저 게이트가 완전히 빠져 있다. PLAN_DONE은 어느 루프에서도 사용되지 않는다.

**권장**: 
- PLAN_DONE의 정의를 확정: "PPR/PPU 직후 유저 PRD 확인" → plan.md에 배치. 또는 제거.
- tech-epic에 READY_FOR_IMPL 유저 게이트 추가.

### CP-4. 재시도 한도 초과 시 에스컬레이션 누락 (bugfix + impl TE_SELF)

**bugfix**: ENG_RETRY max 2회 → 초과 시 경로 없음 (무한루프)
**impl**: TE_SELF max 2회 → 초과 시 경로 없음 (무한루프)

두 곳 모두 **다이어그램에 카운터 체크 노드가 없다**. 텍스트로만 "max N회"라고 적혀 있고 분기가 없다.

**권장**: 모든 재시도 루프에 `LIMIT_CHK{{"count > max?"}}` 분기 노드를 다이어그램에 추가. YES 경로를 에스컬레이션 또는 FAIL_ROUTE에 연결.

### CP-5. 에이전트 내부 카운터 vs 루프 attempt 카운터 — 이중 관리

**impl 리뷰**(G-4, G-5)에서 발견. validator와 pr-reviewer가 에이전트 내부에 자체 재시도 카운터(각 3회)를 가지면서, 루프의 attempt 카운터(3회)도 별도로 존재. 최악의 경우 3×3=9회 반복.

orchestration-rules.md에 `VALIDATION_ESCALATE`와 `REVIEW_LOOP_ESCALATE`가 정의되어 있지만, impl.md 다이어그램에는 이 마커들이 소비되는 경로가 없다.

**권장**: 에이전트 내부 카운터를 폐기하고 루프 attempt 카운터로 통합. 또는 에이전트 내부 카운터를 유지하되 다이어그램에 명시. 혼재는 금지.

### CP-6. fast/경량 경로에서 게이트 스킵 — 일관된 최소 게이트 필요

| 경로 | 테스트 | Plan Val | 코드 리뷰 |
|------|:---:|:---:|:---:|
| plan ARC_MP_SKIP | N/A | ❌ | N/A |
| impl fast | ❌ | N/A | ❌ |
| bugfix LOW (제안) | ❌ | N/A | ❌ |

빅테크에서는 경량 경로라도 최소 게이트(lint + affected tests)를 반드시 유지한다. "단순 변경이라 검증 불필요"는 존재하지 않는다.

**권장**: 모든 경량 경로에 최소 게이트 정의:
- `tsc --noEmit` (타입 체크)
- `vitest --related` (영향 테스트만)
- 수용 기준 메타데이터 감사 (정책 8)

---

## 3. 루프별 핵심 수정 제안 (교차 검증 후 정제)

### Plan 루프

| # | 수정 | 난이도 | 영향도 |
|---|------|--------|--------|
| 1 | ARC_MP_SKIP 경로에 Plan Validation 추가 (CP-1) | 낮음 | 높음 |
| 2 | PLAN_DONE 마커 위치 확정 (PPR 직후) 또는 정책 3에서 삭제 (CP-3) | 낮음 | 높음 |
| 3 | SCOPE 결정 기준표 추가 (affected_areas 기반) | 낮음 | 중간 |
| 4 | EPIC 결정을 자동 분기로 전환 (모듈 수 기준) | 낮음 | 낮음 |
| 5 | PPR → 유저 확인 게이트 → ARC_SD (PLAN_DONE 활용) | 낮음 | 중간 |
| 6 | 에스컬레이션 후 복귀 3-way 분기 추가 (CP-2) | 중간 | 중간 |

### Tech Epic 루프

| # | 수정 | 난이도 | 영향도 |
|---|------|--------|--------|
| 1 | ARC_MP → VAL_PV → RFI 경로 추가 (CP-1) | 낮음 | 높음 |
| 2 | RFI → USER_APPROVE 유저 게이트 추가 (CP-3) | 낮음 | 높음 |
| 3 | ×N 실패 정책 정의: fail-fast + 유저 3-way (재시도/스킵/중단) | 중간 | 높음 |
| 4 | ISSUES 노드 주체 명확화 (architect TASK_DECOMPOSE 또는 메인 Claude) | 중간 | 중간 |
| 5 | architect TECH_EPIC @OUTPUT에서 stories_doc 제거 (설계와 이슈 생성 분리) | 중간 | 중간 |
| 6 | 첫 모듈 canary 게이트 (유저 방향 확인 후 N-1 진행) | 낮음 | 중간 |
| 7 | batch vs incremental 모드 선택 (모듈 의존성 기반) | 높음 | 중간 |

### Impl 루프

| # | 수정 | 난이도 | 영향도 |
|---|------|--------|--------|
| 1 | TE_SELF max 2회 초과 → FAIL_ROUTE 분기 추가 (CP-4) | 낮음 | 높음 |
| 2 | fast depth 다이어그램에 SRC_CHK 후 depth 분기 노드 삽입 | 낮음 | 높음 |
| 3 | depth 테이블 fast 행 정정: pr-reviewer 제거, LLM 2회 명시 | 낮음 | 중간 |
| 4 | VALIDATION_ESCALATE / REVIEW_LOOP_ESCALATE 폐기 or 명시화 (CP-5) | 중간 | 중간 |
| 5 | SPEC_GAP: attempt 리셋 폐지 → attempt 동결 + spec_gap_count 별도 관리 | 중간 | 높음 |
| 6 | vitest 실패 → fail_type=test_fail 라벨 명시 | 낮음 | 낮음 |
| 7 | fast depth 최소 게이트: vitest --related 추가 (CP-6) | 낮음 | 중간 |
| 8 | 실패 유형별 독립 카운터 (장기 — 단계적 도입) | 높음 | 높음 |

### Bugfix 루프

| # | 수정 | 난이도 | 영향도 |
|---|------|--------|--------|
| 1 | ENG_RETRY max 2회 초과 → IMPLEMENTATION_ESCALATE 연결 (CP-4) | 낮음 | 높음 |
| 2 | COMMIT → MERGE → MCE/HD 추가 (브랜치 전략 정합) | 낮음 | 높음 |
| 3 | SPEC_ISSUE VAL_PV FAIL 분기 추가 (재보강 max 1회 → 에스컬레이션) | 낮음 | 높음 |
| 4 | BUGFIX_PLAN_READY 마커 노드 다이어그램 추가 | 낮음 | 낮음 |
| 5 | engineer에 regression test 작성 의무 명시 (Google: 모든 bugfix CL에 테스트 필수) | 낮음 | 중간 |
| 6 | severity 기반 경량 분기 (LOW+1파일 → architect 스킵) | 중간 | 중간 |
| 7 | bugfix depth 체계 공식화 (fast/std/deep 매핑) | 중간 | 중간 |
| 8 | architect/bugfix-plan.md REGRESSION/INTEGRATION_ISSUE 진입조건 → qa 출력과 정합 | 낮음 | 낮음 |

---

## 4. 불필요하거나 제거 가능한 요소

| 요소 | 현재 상태 | 판단 | 근거 |
|------|-----------|------|------|
| PLAN_DONE 마커 (정책 3) | 정의만 있고 미사용 | **삭제 또는 활용** | 유지하면 혼란. 활용하면 PPR 직후 게이트로 유용 |
| VALIDATION_ESCALATE 마커 | 정의만 있고 미소비 | **삭제 권장** | attempt 카운터에 통합되어 별도 마커 불필요 |
| REVIEW_LOOP_ESCALATE 마커 | 정의만 있고 미소비 | **삭제 권장** | 위와 동일 |
| SRC_CHK 노드 (impl) | engineer가 src/ 미변경 시 발동 | **존재 사유 명시 필요** | engineer 허용 경로가 src/** 뿐이라 발동 조건 불명확 |
| impl SPEC_GAP attempt 리셋 | 리셋으로 최대 9회 반복 가능 | **리셋 폐지, 동결로 전환** | 오실레이션 방지 |
| TASK_DECOMPOSE 내부 impl 일괄 작성 | ARC_TD가 N개 impl을 한 세션에서 작성 | **분리 권장** | 컨텍스트 윈도우 한계로 마지막 impl 품질 저하 |
| plan.md E-2 (신규 기획 무조건 SYSTEM_DESIGN) | PP_NEW → ARC_SD 고정 | **현행 유지 (명시적 의도)** | 신규 프로젝트는 설계가 필수라는 전제가 합리적 |

---

## 5. 빅테크 벤치마크 요약 — 현재 시스템과의 갭

### 현재 시스템이 잘 하고 있는 것

| 항목 | 빅테크 대응 | 평가 |
|------|------------|------|
| 설계 → 검증 → 구현 파이프라인 | Google Design Doc → CL | ✅ 패턴 일치 |
| validator 자동 검증 | Google presubmit | ✅ 자동화된 품질 게이트 |
| depth 기반 리뷰 강도 조절 | Google readability/security review 선택적 | ✅ 리스크 기반 조절 |
| 에스컬레이션 → 유저 보고 | Google TL escalation | ✅ 자동 복구 방지, 인간 판단 존중 |
| 순차 실행 + 학습 효과 | Meta stacked diff (순차 land) | ✅ LLM 특성에 맞는 순차 전략 |
| 3회 attempt 제한 | (인간은 무제한, LLM은 비용/hallucination 고려) | ✅ LLM 맥락에서 합리적 |

### 개선 필요

| 항목 | 빅테크 관행 | 현재 상태 | 갭 |
|------|------------|-----------|-----|
| Lint/Format 자동 실행 | Google presubmit 필수 | engineer 완료 게이트에 tsc만 | ⚠️ ESLint/Prettier 미포함 |
| 모든 bugfix에 regression test | Google CL 필수 | bugfix에 test-engineer 없음 | ⚠️ 테스트 작성 주체 불명 |
| severity 기반 라우팅 | Google P0-P4, Meta SEV | 4-way 분류이나 severity별 경로 미분화 | ⚠️ 단순 버그에도 full pipeline |
| 경량 경로에도 최소 게이트 | Google/Meta CI 무조건 실행 | fast depth 테스트 완전 스킵 | ⚠️ 게이트 우회 |
| 롤백 전략 | Google auto-rollback, Meta revert-first | 롤백 절차 미정의 | ⚠️ merge 후 문제 시 대응 없음 |
| 근본 원인 분석 (RCA) | Google postmortem, Meta SEV review | 없음 | ⚠️ 재발 방지 메커니즘 부재 |
| 에스컬레이션 후 복귀 | Google 3-way (재시도/롤백/중단) | 에스컬레이션 = 종착점 | ⚠️ 복귀 경로 미정의 |

---

## 6. 최종 우선순위 — Top 10 Action Items

아래는 4개 리뷰 + 교차 검증을 종합한 최종 우선순위. 난이도 대비 영향도가 높은 순.

| 순위 | 항목 | 대상 | 난이도 | 영향도 | 분류 |
|------|------|------|--------|--------|------|
| **1** | TE_SELF / ENG_RETRY 한도 초과 에스컬레이션 추가 | impl, bugfix | 낮음 | **위험** | CP-4 (무한루프) |
| **2** | Plan Validation 일관 적용 (MODULE_PLAN → VAL_PV 필수) | plan, tech-epic, (design) | 낮음 | **위험** | CP-1 (게이트 우회) |
| **3** | bugfix merge 단계 추가 | bugfix | 낮음 | **위험** | 브랜치 전략 정합 |
| **4** | bugfix SPEC_ISSUE VAL_PV FAIL 분기 추가 | bugfix | 낮음 | **높음** | 데드엔드 방지 |
| **5** | tech-epic READY_FOR_IMPL 유저 게이트 추가 | tech-epic | 낮음 | **높음** | 정책 3 준수 |
| **6** | fast depth 테이블 pr-reviewer 제거 + 다이어그램 분기 노드 추가 | impl | 낮음 | **중간** | 3곳 불일치 해소 |
| **7** | VALIDATION_ESCALATE / REVIEW_LOOP_ESCALATE 폐기 | impl, rules | 중간 | **중간** | CP-5 (마커 정리) |
| **8** | tech-epic ×N 실패 정책 + canary 게이트 | tech-epic | 중간 | **높음** | 대규모 변경 안전망 |
| **9** | SPEC_GAP attempt 리셋 → 동결 + 별도 카운터 | impl | 중간 | **높음** | 오실레이션 방지 |
| **10** | bugfix regression test 의무화 + severity 기반 분기 | bugfix | 중간 | **중간** | 빅테크 프랙티스 |

---

## 7. 리뷰 간 불일치/보완 사항

교차 검증 중 발견한 리뷰 간 차이점:

| 항목 | 리뷰 A 의견 | 리뷰 B 의견 | 최종 판단 |
|------|-------------|-------------|-----------|
| KNOWN_ISSUE 임계값 (1회 vs 3회) | bugfix 리뷰: 현재 bugfix.md와 rules.md 모두 1회로 일치 (GAP_AUDIT가 이전 버전 참조?) | GAP_AUDIT: 3회 vs 1회 불일치 | **bugfix.md 현재 버전 확인 필요**. bugfix 리뷰가 최신 파일을 읽은 것이 맞다면 GAP_AUDIT A-2는 해결 완료. |
| Design Validation 재시도 (1회 vs 더 필요?) | tech-epic 리뷰: LLM-to-LLM이므로 1회 합리적 | plan 리뷰: Plan Validation은 2회로 상향 검토 | **Design Validation 1회 유지, Plan Validation은 현행(1회) 유지**. 두 검증 모두 에스컬레이션이 안전망이므로 추가 재시도 불필요. |
| fast depth 폐지 vs 유지 | impl 리뷰: vitest --related 최소 게이트 추가하여 유지 | (다른 리뷰 미언급) | **최소 게이트 추가 후 유지**. 완전 폐지는 과잉. |
| 실패 유형별 독립 카운터 | impl 리뷰: 제안하되 단계적 도입 (높은 복잡도) | bugfix 리뷰: 미언급 | **장기 과제로 분류**. 현재는 단일 카운터 + safety cap으로 충분. |

---

## 부록 A: GAP_AUDIT_REPORT 전체 항목 최종 상태

| GAP_AUDIT ID | 항목 | 처리 리뷰 | 상태 |
|---|---|---|---|
| A-1 | impl fast depth pr-reviewer 모순 | impl G-3 | ✅ 수정안 제시 |
| A-2 | bugfix KNOWN_ISSUE 임계값 | bugfix G-4 + 부록 C-5 | ✅ 해결 완료 (현재 양쪽 "1회"로 일치) |
| A-3 | bugfix BUGFIX_PLAN_READY 누락 | bugfix G-5 | ✅ 수정안 제시 |
| A-4 | VALIDATION_ESCALATE 미사용 | impl G-4 | ✅ 폐기 권장 |
| A-5 | REVIEW_LOOP_ESCALATE 미사용 | impl G-5 | ✅ 폐기 권장 |
| A-6 | PLAN_DONE 미사용 | plan G-2 | ✅ 활용 또는 삭제 |
| B-1 | design UX_REDESIGN 누락 | (design 제외) | ⏭️ 미대상 |
| B-2 | impl fast test skip 미반영 | impl G-1 | ✅ 분기 노드 추가 |
| B-3 | impl TE_SELF 종착점 없음 | impl G-2 | ✅ 분기 추가 |
| B-4 | bugfix ENG_RETRY 에스컬레이션 없음 | bugfix G-1 | ✅ 에스컬레이션 추가 |
| B-5 | bugfix SPEC_ISSUE VAL_PV FAIL 없음 | bugfix G-3 | ✅ FAIL 분기 추가 |
| B-6 | bugfix merge 누락 | bugfix G-2 | ✅ merge 단계 추가 |
| B-7 | tech-epic Plan Validation 없음 | tech-epic G-1 | ✅ VAL_PV 추가 |
| B-8 | tech-epic ×N 실패 처리 없음 | tech-epic G-2 | ✅ fail-fast + 유저 판단 |
| C-1 | Plan Validation 적용 불일치 | 전체 CP-1 | ✅ 일관 적용 |
| C-2 | 정책 8 다이어그램 미반영 | impl G-6, plan I-2 | ✅ 주석 추가 |
| C-3 | bugfix test-engineer 부재 | bugfix G-7 | ✅ engineer 위임 |
| C-4 | READY_FOR_IMPL 발행 주체 | plan I-1 | ✅ 통일안 제시 |
| D-1 | design IMPL_CHK 주체 | (design 제외) | ⏭️ 미대상 |
| D-2 | design FLAG prefix | (design 제외) | ⏭️ 미대상 |
| D-3 | impl vitest fail_type | impl G-7 | ✅ 라벨 명시 |

---

## 부록 B: 신규 발견 (GAP_AUDIT에 없었던 항목)

각 리뷰에서 GAP_AUDIT 이후 신규로 발견된 주요 항목:

| 리뷰 | ID | 항목 | 영향도 |
|------|-----|------|--------|
| plan | G-3 | SCOPE 결정 기준 부재 | 중간 |
| plan | G-5 | product-planner → architect 핸드오프 정보 손실 (NFR) | 중간 |
| plan | I-4 | ARC_MP_SKIP의 design_doc 파라미터가 존재하지 않음 | 높음 |
| plan | E-1 | PPR 직후 유저 확인 없이 architect 직행 | 중간 |
| plan | E-3 | TASK_DECOMPOSE 내부 impl 일괄 작성 → 품질 저하 | 중간 |
| tech-epic | G-3 | ISSUES 노드 주체/방법 미정의 | 중간 |
| tech-epic | G-7 | architect TECH_EPIC @OUTPUT(stories_doc)과 다이어그램 순서 모순 | 높음 |
| tech-epic | B-4 | batch vs incremental 모드 (모듈 의존성 기반) | 중간 |
| impl | I-1 | 단일 attempt 카운터가 이질적 실패유형 동일 취급 | 높음 |
| impl | I-2 | SPEC_GAP 리셋으로 최대 9회 오실레이션 | 높음 |
| impl | B-1 | Lint/Format 단계 부재 (Google presubmit 대비) | 중간 |
| bugfix | I-1 | 모든 FUNCTIONAL_BUG에 architect 경유 (단순 버그에 과잉) | 중간 |
| bugfix | BT-7 | architect/bugfix-plan.md의 REGRESSION/INTEGRATION_ISSUE 진입조건이 qa 출력에 없음 (데드코드) | 중간 |
| bugfix | BT-4 | 롤백 전략 부재 | 중간 |
| bugfix | BT-3 | 근본 원인 분석(RCA) 단계 부재 | 낮음 |

---

## 부록 C: Iteration 2 교차 검증 — 리뷰 자체의 누락 보완

4개 개별 리뷰가 **공통으로 놓친** 항목을 iteration 2에서 추가 발견.

### C-1. impl.md — SPEC_MISSING 마커 미처리

**발견**: `orchestration-rules.md` 에스컬레이션 테이블에 `SPEC_MISSING | validator Code Validation (impl 없음) | architect Module Plan 호출`이 정의되어 있고, `agents/validator/code-validation.md` line 16에도 `SPEC_MISSING` 발행 로직이 존재한다.

**문제**: impl.md 다이어그램에 이 마커를 소비하는 경로가 없다. validator가 SPEC_MISSING을 발행하면 하네스가 처리할 방법이 없다. GAP_AUDIT에서 지적했으나 impl 리뷰에서 누락.

**수정안**: impl.md 다이어그램의 VAL_CV 출력에 3-way 분기 추가:
```
VAL_RESULT -->|PASS| DEPTH_CHK
VAL_RESULT -->|FAIL| FAIL_ROUTE
VAL_RESULT -->|SPEC_MISSING| ARC_MP_RECOVER["architect MODULE_PLAN\n(impl 복구)"]
```

### C-2. impl.md — PRODUCT_PLANNER_ESCALATION_NEEDED 미처리

**발견**: `orchestration-rules.md` 에스컬레이션 테이블에 `PRODUCT_PLANNER_ESCALATION_NEEDED | architect SPEC_GAP | product-planner 에스컬레이션`이 정의되어 있고, `agents/architect/spec-gap.md` line 35에 발행 로직이 존재한다.

**문제**: impl.md의 SPEC_GAP 분기에서 `SPEC_GAP_RESOLVED`만 처리하고 `PRODUCT_PLANNER_ESCALATION_NEEDED`를 처리하지 않는다. architect가 "이건 PRD 수준의 변경이 필요하다"고 판단해도 루프에 그 경로가 없다.

**수정안**: SPEC_GAP 분기에 추가:
```
ARC_SG -->|SPEC_GAP_RESOLVED| SGR
ARC_SG -->|PRODUCT_PLANNER_ESCALATION_NEEDED| PP_ESC["product-planner\n에스컬레이션"]:::escalation
ARC_SG -->|TECH_CONSTRAINT_CONFLICT| TC_ESC["기술 제약 충돌\n에스컬레이션"]:::escalation
```

### C-2b. impl.md — TECH_CONSTRAINT_CONFLICT 미처리 (Iteration 3 추가)

**발견**: `orchestration-rules.md` line 42에 `TECH_CONSTRAINT_CONFLICT | architect SPEC_GAP (기술 제약 충돌) | 메인 Claude 보고`가 정의되어 있고, `agents/architect/spec-gap.md` line 51에 발행 로직이 존재한다.

**문제**: impl.md의 SPEC_GAP 분기에서 SPEC_GAP_RESOLVED만 처리. architect가 "기존 기술 스택 제약으로 스펙 충족 불가"라고 판단해도 다이어그램에 경로가 없다. C-2와 동일 구조.

**정리 — architect SPEC_GAP의 실제 3-way 출력 vs 다이어그램**:

| architect SPEC_GAP 출력 | 다이어그램 처리 |
|---|:---:|
| `SPEC_GAP_RESOLVED` | ✅ |
| `PRODUCT_PLANNER_ESCALATION_NEEDED` | ❌ |
| `TECH_CONSTRAINT_CONFLICT` | ❌ |

→ 3개 출력 중 1개만 다이어그램에 있음. **66% 미처리**.

### C-3. bugfix.md — DESIGN_ISSUE 라우팅 다이어그램/테이블 3-way 불일치

**발견**: bugfix.md 내부에서 DESIGN_ISSUE의 라우팅이 3곳에서 다르다:

| 위치 | DESIGN_ISSUE 라우팅 |
|------|---------------------|
| Mermaid 다이어그램 (line 59) | `QA_ROUTE -->|DESIGN_ISSUE| SE` → **SCOPE_ESCALATE** (에스컬레이션) |
| qa 분류 테이블 (line 84) | `→ 디자인 루프` (designer → design-critic → engineer) |
| 마커 테이블 (line 132) | `→ 디자인 루프 (관련 파일 ≥ 1일 때)` |

bugfix 리뷰에서 I-3으로 지적했으나 심각도를 낮게 평가. Iteration 3에서 논리적 모순을 추가 확인:

**논리적 모순**: `SCOPE_CHECK{{"관련 파일 ≥ 1?"}} -->|YES| QA_ROUTE` 후에 `QA_ROUTE -->|DESIGN_ISSUE| SE(SCOPE_ESCALATE)` 로 연결된다. 그런데 `SCOPE_ESCALATE`의 정의는 "관련 모듈/파일 = 0 → 신규 기능 판정" (qa.md line 107, rules line 37). SCOPE_CHECK가 이미 "파일 있음"을 확인했는데 "파일 없음" 전용 에스컬레이션으로 보내는 것은 **정의 자체와 모순**.

**수정안**: 다이어그램의 `QA_ROUTE -->|DESIGN_ISSUE| SE`를 `QA_ROUTE -->|DESIGN_ISSUE| DESIGN_ENTRY["→ 디자인 루프"]`로 변경. SCOPE_ESCALATE는 SCOPE_CHECK=NO 경로에서만 사용 (이미 정상).

### C-4. 하네스 전체 — `validator_b_passed` 레거시 Mode B 네이밍 잔존

**발견**: 오케스트레이션 문서는 "Code Validation" 등 서술적 이름으로 현행화되었으나, 하네스 스크립트·훅·플래그 파일에 레거시 Mode B 네이밍이 광범위하게 잔존한다.

| 파일 | 잔존 참조 |
|------|-----------|
| `hooks/post-agent-flags.py` | `touch("validator_b_passed")` |
| `hooks/harness-router.py` | `"validator_b_passed": os.path.exists(...)` |
| `hooks/agent-gate.py` | `"❌ pr-reviewer 전 validator Mode B PASS 필요"` (에러 메시지에 Mode B!) |
| `harness/bugfix.sh` | `touch "/tmp/${PREFIX}_validator_b_passed"` |
| `harness/utils.sh` | `"merge 거부: validator_b_passed 없음"` |
| `harness/impl-process.sh` | `touch "/tmp/${PREFIX}_validator_b_passed"` (2곳) |
| `docs/harness-state.md` | `validator Mode B (PASS)` |
| `orchestration/impl.md` depth 테이블 | `validator_b_passed` |
| `orchestration-rules.md` 머지 조건 | `validator_b_passed` (3곳) |

**영향**: 오케스트레이션 문서를 읽는 사람은 "Code Validation"을 알지만, 스크립트를 읽는 사람은 "Mode B"만 본다. 신규 컨트리뷰터가 둘을 연결하기 어렵다. `agent-gate.py`의 에러 메시지에 "Mode B"가 표시되어 유저에게도 혼란.

**수정안**: 플래그 이름을 `code_validation_passed`로 일괄 리네이밍. 또는 최소한 `docs/harness-state.md`와 에러 메시지에서 "Mode B" 참조를 서술적 이름으로 변경.

### C-5. GAP_AUDIT A-2 해결 확인

**현재 상태**: bugfix.md line 31: `"1회 분석 원인 불가"`, orchestration-rules.md line 36: `"1회 분석으로 원인 특정 불가"`. **양쪽 일치.**

GAP_AUDIT_REPORT의 A-2 항목("3회 vs 1회 불일치")은 이전 버전(Mermaid 변환 전) 기준이었으며, 현재는 해결 완료. 단, qa.md의 KNOWN_ISSUE 판정은 "3가지 조건 모두 충족" (3 conditions, not 3 attempts)이므로 "3회"와 혼동될 수 있다. bugfix.md의 KI 노드 텍스트에 "qa 판정 기준 3조건 충족" 등으로 명확화하면 오해 방지.

---

## 부록 D: 최종 Top 10 수정 (Iteration 3 최종)

3회 iteration을 거쳐 확정된 최종 우선순위:

| 순위 | 항목 | 대상 | 난이도 | 근거 |
|------|------|------|--------|------|
| **1** | TE_SELF / ENG_RETRY 한도 초과 에스컬레이션 추가 | impl, bugfix | 낮음 | 무한루프 위험 (CP-4) |
| **2** | Plan Validation 일관 적용 (MODULE_PLAN → VAL_PV 필수) | plan, tech-epic | 낮음 | 게이트 우회, 정책 8 미적용 (CP-1) |
| **3** | bugfix merge 단계 + VAL_PV FAIL 분기 추가 | bugfix | 낮음 | 브랜치 전략 불일치 + 데드엔드 |
| **4** | impl SPEC_GAP 3-way 출력 처리 (RESOLVED / PP_ESCALATION / TECH_CONFLICT) | impl | 낮음 | architect 출력 3개 중 2개 미처리 (66%) |
| **5** | impl SPEC_MISSING 경로 + bugfix DESIGN_ISSUE 라우팅 수정 | impl, bugfix | 낮음 | 에이전트 발행 가능 마커 미소비 + 논리적 모순 |
| **6** | tech-epic READY_FOR_IMPL 유저 게이트 + ×N 실패 정책 | tech-epic | 중간 | 정책 3 위반 + 대규모 변경 안전망 부재 |
| **7** | fast depth 테이블 정정 + 다이어그램 분기 노드 | impl | 낮음 | 3곳 불일치 (테이블/다이어그램/머지 조건) |
| **8** | VALIDATION_ESCALATE / REVIEW_LOOP_ESCALATE 폐기 | impl, rules | 중간 | 정의만 있고 소비 경로 없는 좀비 마커 |
| **9** | SPEC_GAP attempt 리셋 → 동결 전환 | impl | 중간 | 리셋으로 최대 9회 오실레이션 가능 |
| **10** | `validator_b_passed` → `code_validation_passed` 리네이밍 | 하네스 전체 | 중간 | 문서-코드 네이밍 불일치 (10+ 파일) |

### 전체 수치 요약

| 지표 | 값 |
|------|-----|
| 개별 리뷰 발견 합계 | 67건 |
| 교차 검증 공통 패턴 | 6건 (CP-1~6) |
| Iteration 2 추가 발견 | 5건 (C-1~5) |
| Iteration 3 추가 발견 | 1건 (C-2b TECH_CONSTRAINT_CONFLICT) |
| **총 고유 발견** | **72건+** |
| P0 (무한루프/데드엔드) | 10건 |
| 에이전트 발행 가능하나 다이어그램 미처리 마커 | 5개 (SPEC_MISSING, PP_ESCALATION, TECH_CONFLICT, VALIDATION_ESCALATE, REVIEW_LOOP_ESCALATE) |
| 좀비 마커 (정의 있으나 미사용) | 3개 (PLAN_DONE, VALIDATION_ESCALATE, REVIEW_LOOP_ESCALATE) |
| GAP_AUDIT 21건 중 해결/수정안 제시 | 18건 (design 3건 제외) |
