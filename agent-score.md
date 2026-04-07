# 에이전트 완성도 평가 — 100점 만점

> 마지막 평가일: 2026-04-02
> 시스템 전체 평균: **89.8점** _(2차 개선: design-critic 85→89, validator 86→90, qa 87→91 반영)_

---

## 채점 기준 (5개 카테고리)

| 카테고리 | 배점 | 설명 |
|---|---|---|
| 역할 명확성 | 20점 | 역할·범위·에이전트 간 경계가 명확한가 |
| 워크플로우 완성도 | 25점 | 정상 케이스 처리 완전. 단계·출력 마커 명확 |
| 엣지케이스 & 충돌 처리 | 20점 | 예외 상황·에이전트 충돌·루프 보호 |
| 출력 일관성 | 20점 | 마커·출력 형식·후속 에이전트를 위한 정보 |
| 제약 & 가드레일 | 15점 | 잘못된 사용 방지·범위 이탈·재시도 한도 |

---

## 순위 요약

| 순위 | 에이전트 | 점수 | 핵심 미비 |
|---|---|---|---|
| 1 | pr-reviewer | 92 | ✅ 개선됨 (78→92). 잔여: NICE TO HAVE 후속 흐름 코멘트 수준, REVIEW_LOOP_ESCALATE 이후 메인 Claude 처리 미정 |
| 2 | architect | 92 | 재시도 한도 없음, Mode A 없이 Mode B 호출 방지 없음 |
| 3 | product-planner | 90 | 이해관계자 충돌 처리 없음, PRODUCT_PLAN_READY 선언 시점 기준 모호 |
| 4 | designer | 91 | ✅ 개선됨 (82→91). 잔여: UX 개편 진입 조건 모호, Mode A/B 출력 형식 분리 미완 |
| 5 | qa | 87 | KNOWN_ISSUE 결정 주체 불명확, 재검증 루프 주체가 메인 Claude 의존 |
| 6 | engineer | 87 | CHANGES_REQUESTED 피드백 처리 별도 없음, Figma Mode B 불완전 _(루프 한도 추가로 +1)_ |
| 7 | test-engineer | 87 | 기존 테스트 파일 처리 없음 _(자체 수정 한도 추가로 +1)_ |
| 8 | design-critic | 89 | ✅ 개선됨 (85→89). 잔여: ITERATE 피드백 구체성 기준 없음 |
| 9 | validator | 90 | ✅ 개선됨 (86→90). 잔여: Mode A 저장 실제 보장은 메인 Claude 의존 |
| 10 | qa | 91 | ✅ 개선됨 (87→91). 잔여: 재검증 루프 호출 주체 명시 보완 여지 |

---

## 공통 미비 패턴

- **루프 재시도 한도** — 대부분 에이전트에 최대 재시도 횟수 없음
- **MCP 실패 fallback** — designer, design-critic: Stitch/Figma 실패 시 복구 절차 없음
- **이전 루프 참조 강제** — pr-reviewer, validator: 재검토 시 이전 MUST FIX/FAIL 목록 참조 의무 없음

---

## 상세 평가

---

### architect — 92점

| 카테고리 | 점수 | 세부 내용 |
|---|---|---|
| 역할 명확성 | 19/20 | Mode A~E 5개 모드 + 각 호출 시점 + PRD 위반 에스컬레이션 + Schema-first. **감점**: Mode D/E 경계가 README와 완전 일치하는지 미확인 |
| 워크플로우 완성도 | 24/25 | Mode A NFR 포함, Mode B DB 영향도+8항목 게이트+핵심로직 체크, Mode C TECH_CONSTRAINT_CONFLICT, TRD 현행화 8섹션. **감점**: step 4-a 번호 체계 깨짐 |
| 엣지케이스 & 충돌 처리 | 17/20 | TECH_CONSTRAINT_CONFLICT 3옵션+권고, ADR Superseded 처리, Breaking Change 검토. **감점**: READY_FOR_IMPL 재시도 횟수 한도 없음, SYSTEM_DESIGN_READY 없이 Mode B 호출 방지 없음 |
| 출력 일관성 | 18/20 | SYSTEM_DESIGN_READY/READY_FOR_IMPL/TECH_CONSTRAINT_CONFLICT 마커 완전. **감점**: 핵심 로직 체크 항목이 출력 형식에서 분리됨 |
| 제약 & 가드레일 | 14/15 | 추측 금지, 결정 근거 필수, PRD 직접 수정 금지, Code-first 예외 명시. **감점**: 게이트 미통과 최대 재시도 횟수 없음 |

**개선 우선순위**
1. Mode B READY_FOR_IMPL 재시도 최대 3회 → 초과 시 메인 Claude 에스컬레이션
2. Mode B 시작 전 SYSTEM_DESIGN_READY 존재 여부 확인 게이트 추가
3. 출력 형식 체크리스트 항목 순서 정리

---

### product-planner — 90점

| 카테고리 | 점수 | 세부 내용 |
|---|---|---|
| 역할 명확성 | 19/20 | Mode A/B 트리거 명확, BM+스펙 레벨 의무. **감점**: 기존 PRD 있는 상태에서 invoked 시 Mode A/B 선택 기준 불명확 |
| 워크플로우 완성도 | 23/25 | 6개 수집항목+NFR, MoSCoW+UX흐름, 스코프 4옵션, Mode B 영향분석 4항목. **감점**: 유저가 계속 수정 요청할 때 PRODUCT_PLAN_READY 선언 시점 기준 없음 |
| 엣지케이스 & 충돌 처리 | 16/20 | Phase 3 명시적 선택 강제, NFR 미정 "없음" 명시. **감점**: 이해관계자 충돌 프레임워크 없음, Mode B에서 기술 제약 충돌 시 처리 없음 |
| 출력 일관성 | 19/20 | PRODUCT_PLAN_READY 7섹션, PRODUCT_PLAN_UPDATED. **감점**: Mode B "재검토 필요 Phase" 지시가 추상적 |
| 제약 & 가드레일 | 13/15 | 추측 금지, 유저 확인 필수, BM 필수. **감점**: Phase 3 이전 PRODUCT_PLAN_READY 강제 메커니즘 없음, 루프 종료 기준 없음 |

**개선 우선순위**
1. Phase 1~2 완료 후 PRODUCT_PLAN_READY 선언 가능 조건(최대 대화 수 또는 "충분함" 판단 기준) 추가
2. 기존 PRD 있는 경우 Mode A/B 자동 판별 규칙 추가
3. Mode B 출력의 "재검토 필요 Phase" 구체화 (Phase 번호 명시)

---

### qa — 87점

| 카테고리 | 점수 | 세부 내용 |
|---|---|---|
| 역할 명확성 | 19/20 | 2축 분류, 경량 RCA, 라우팅 역할, 코드 수정 금지. **감점**: 재검증 루프에서 QA가 직접 재호출 못하고 메인 Claude에 의존 |
| 워크플로우 완성도 | 22/25 | Step 1~5, 회귀 감지, KNOWN_ISSUE 루프, 라우팅 매트릭스. **감점**: 재검증 루프 주체 모호, CRITICAL 중단 후 다른 이슈 처리 없음 |
| 엣지케이스 & 충돌 처리 | 16/20 | CRITICAL 즉시 중단, KNOWN_ISSUE 3회, 높은 확신 기준. **감점**: KNOWN_ISSUE 후 결정 주체 불명확, 여러 CRITICAL 동시 우선순위 없음 |
| 출력 일관성 | 17/20 | BLOCKED/FAIL/PASS 판정 선두, 심각도별 그룹, KNOWN_ISSUE 마커. **감점**: DB 관련 이슈 증거 첨부 방법 구체성 부족 |
| 제약 & 가드레일 | 13/15 | false positive 원칙, 읽기 전용, 메인 Claude만 호출. **감점**: 재검증 루프 호출 횟수 한도 없음 |

**개선 우선순위**
1. 재검증 루프 주체 명확화: "메인 Claude가 qa를 재호출" 절차 명시
2. CRITICAL 이슈 중단 후 나머지 이슈 처리 여부 규칙 추가
3. 재검증 루프 최대 3회 → KNOWN_ISSUE 에스컬레이션 명시

---

### engineer — 86점

| 카테고리 | 점수 | 세부 내용 |
|---|---|---|
| 역할 명확성 | 18/20 | Phase 1~3, SPEC_GAP_FOUND, DESIGN_HANDOFF 통합. **감점**: pr-reviewer CHANGES_REQUESTED 수신 처리 별도 없음 |
| 워크플로우 완성도 | 22/25 | SPEC_GAP 9항목, 자가 검증 6항목, DESIGN_HANDOFF 토큰 변환+충돌+영향도, 커밋 규칙. **감점**: DESIGN_HANDOFF Mode B(Figma) frame→React 변환 절차 없음 |
| 엣지케이스 & 충돌 처리 | 16/20 | SPEC_GAP 에스컬레이션, 병렬 impl 충돌 처리. **감점**: CHANGES_REQUESTED와 FAIL 동시 수신 우선순위 없음 |
| 출력 일관성 | 17/20 | 완료 보고 형식, SPEC_GAP_FOUND 형식. **감점**: DESIGN_HANDOFF 완료 보고에 영향받은 파일 섹션 없음 |
| 제약 & 가드레일 | 13/15 | 계획 외 기능 금지, 래퍼 함수만, as any 금지, git add . 금지. **감점**: tsc 통과 강제 없음(권고만), 최대 재시도 횟수 없음 |

**개선 우선순위**
1. pr-reviewer CHANGES_REQUESTED 수신 시 처리 절차 별도 섹션 추가
2. validator FAIL + pr-reviewer CHANGES_REQUESTED 동시 처리 우선순위 규칙
3. 최대 재시도 횟수(3회) → 초과 시 메인 Claude 에스컬레이션

---

### test-engineer — 86점

| 카테고리 | 점수 | 세부 내용 |
|---|---|---|
| 역할 명확성 | 18/20 | Phase 1~3, 코드 수정 금지, TESTS_PASS/FAIL 마커. **감점**: 기존 테스트 파일 있는 경우 처리 없음 |
| 워크플로우 완성도 | 22/25 | 3유형 케이스 도출, 프레임워크 감지 4단계, FLAKY/TEST_CODE_BUG/IMPLEMENTATION_BUG 분류. **감점**: 테스트 설정 파일 생성 여부 기준 없음, 통합 vs 단위 구분 없음 |
| 엣지케이스 & 충돌 처리 | 15/20 | FLAKY/TEST_CODE_BUG 자체 수정. **감점**: 자체 수정 시도 횟수 한도 없음, 테스트 실행 환경 오류 시 처리 없음, 루프 한도 없음 |
| 출력 일관성 | 18/20 | TESTS_PASS/FAIL 마커, 케이스 테이블, 실패 유형 분류, 처리 방향. **감점**: FLAKY 자체 수정 후 재실행 결과 보고 형식 없음 |
| 제약 & 가드레일 | 13/15 | 구현 파일 수정 금지, 테스트 약화 금지, impl 범위 외 금지. **감점**: 자체 수정 최대 횟수 없음, 테스트 환경 설정 생성 허용 여부 불명확 |

**개선 우선순위**
1. 자체 수정(FLAKY, TEST_CODE_BUG) 최대 2회 → 초과 시 SPEC_GAP_FOUND 에스컬레이션
2. 기존 테스트 파일 있는 경우 "덮어쓰기 vs 보강" 판단 규칙 추가
3. FLAKY 자체 수정 후 재실행 결과 보고 형식 추가

---

### design-critic — 85점

| 카테고리 | 점수 | 세부 내용 |
|---|---|---|
| 역할 명확성 | 19/20 | 3 variant vs 5→3 모드 분리, 4개 마커, 읽기 전용. **감점**: Playwright 스크린샷 사용 시점이 base에 없음 |
| 워크플로우 완성도 | 22/25 | View 위반 선행 체크, 4축 40점, 판정 기준 명확, UX 개편 4가중치. **감점**: 5→3 선별 후 유저 미승인 시 처리 없음, ESCALATE 반복 발생 처리 없음 |
| 엣지케이스 & 충돌 처리 | 13/20 | View 전용 위반 ITERATE 감점 명시. **감점**: 동점 타이브레이킹 없음, 3개 모두 30점 이상 시 처리 불명확, Stitch MCP 실패 fallback 없음 |
| 출력 일관성 | 18/20 | 점수표, PICK 근거, Variant 단점, ITERATE 피드백, UX_REDESIGN_SHORTLIST 형식 완전. **감점**: ITERATE 피드백 구체성 수준 기준 없음 |
| 제약 & 가드레일 | 14/15 | 읽기 전용, 새 variant 생성 범위 밖, 증거 기반, 유저 승인 없이 진행 절대 금지. **감점**: 반복 ITERATE 루프 한도가 base에 없음 |

**개선 우선순위**
1. 동점 타이브레이킹 규칙: "구현 실현성" 우선 → 여전히 동점 → ESCALATE
2. 3개 모두 PICK 조건 충족 시 최고점 variant 자동 PICK 명시
3. Stitch MCP 실패 시 "ASCII 와이어프레임으로 유저 직접 선택" fallback 추가

---

### validator — 85점

| 카테고리 | 점수 | 세부 내용 |
|---|---|---|
| 역할 명확성 | 19/20 | Mode A/B 분리, 읽기 전용, 단일 책임(판정만), 증거 기반. **감점**: Mode A 호출 Phase 번호가 README 흐름과 불일치 가능성 |
| 워크플로우 완성도 | 22/25 | Mode A 3섹션 11항목, Mode B 3계층(A:7/B:5+DB3/C:12), DB 추가 체크, Mode A 결과 보존 요청. **감점**: Mode A 결과 저장이 메인 Claude에게 "요청"이라 실제 보장 불가, design-review.md 없을 때 Mode B 처리 없음 |
| 엣지케이스 & 충돌 처리 | 15/20 | FAIL 원인 요약, PASS도 권고사항, DB 변경 분기. **감점**: Mode A FAIL 후 재검증 절차 없음, Mode B 계획 파일 없는 경우 처리 없음, 재시도 횟수 한도 없음 |
| 출력 일관성 | 17/20 | DESIGN_REVIEW_PASS/FAIL, PASS/FAIL 마커, 테이블 형식. **감점**: Mode B 출력 형식에 DB 추가 체크 결과 섹션 없음 |
| 제약 & 가드레일 | 12/15 | 파일 수정 금지, 수정 제안 금지, 모드 미지정 판단 규칙. **감점**: PARTIAL verdict 금지 없음, 재시도 한도 없음 |

**개선 우선순위**
1. Mode A 결과 저장을 Write 도구 없이 강제하는 방법 재설계 (메인 Claude에게 저장 의무 명시 강화)
2. Mode B 출력 형식에 DB 추가 체크 결과 섹션 추가
3. PARTIAL verdict 금지 + 최대 재시도 3회 규칙 추가

---

### designer — 91점 _(이전: 82점, +9)_

| 카테고리 | 점수 | 세부 내용 |
|---|---|---|
| 역할 명확성 | 18/20 | Mode A/B/UX개편 3가지, View-layer only, 차별화 의무. **감점**: UX 개편 모드 진입 조건이 주관적 (컴포넌트 vs 화면 전체 경계 수치 없음) |
| 워크플로우 완성도 | 23/25 | Phase 0~2, UX 개편 5→critic→Stitch→유저, Stitch 실패 4단계 fallback, ITERATE 처리 절차. **감점**: Phase 0 skip 기준 없음 |
| 엣지케이스 & 충돌 처리 | 18/20 | Variant 차별화 자가 검증 게이트, MCP 실패 fallback, ITERATE 3라운드 한도, DESIGN_LOOP_ESCALATE. **감점**: 3라운드 후 유저도 모든 variant 거부 시 처리 없음 |
| 출력 일관성 | 18/20 | DESIGN_READY_FOR_REVIEW, DESIGN_HANDOFF, DESIGN_LOOP_ESCALATE 마커, 피드백 누적 추적. **감점**: UX 개편 5개 와이어프레임 출력 형식 없음, Mode A/B 출력 형식 분리 불명확 |
| 제약 & 가드레일 | 14/15 | View-layer only, 금지 목록, 더미 데이터, variant 자가 체크 게이트, ITERATE 한도. **감점**: 200줄 자가 검증 게이트 없음(원칙만 존재) |

**잔여 개선 포인트**
1. UX 개편 vs 컴포넌트 수준 판단 기준 구체화 (예: "2개 이상 화면 영역 구조 변경 → UX 개편")
2. Mode A/B 출력 형식 섹션 분리

---

### pr-reviewer — 92점 _(이전: 78점, +14)_

| 카테고리 | 점수 | 세부 내용 |
|---|---|---|
| 역할 명확성 | 19/20 | validator 역할 분리 표, 읽기 전용, LGTM/CHANGES_REQUESTED, MUST FIX/NICE TO HAVE, 재검토 루프 경계 명시. **감점**: REVIEW_LOOP_ESCALATE 이후 메인 Claude 흐름 묵시적 |
| 워크플로우 완성도 | 23/25 | 3단계 작업 순서, A~G 7카테고리, 레거시 처리, 테스트 파일 기준. **감점**: LGTM + NICE TO HAVE 후속 처리 절차 코멘트 수준 |
| 엣지케이스 & 충돌 처리 | 17/20 | CHANGES_REQUESTED 재검토 절차(수정 파일만, 이전 목록 추적), 루프 3라운드 한도, 레거시 처리. **감점**: REVIEW_LOOP_ESCALATE 이후 메인 Claude 처리 흐름 미정 |
| 출력 일관성 | 18/20 | LGTM/CHANGES_REQUESTED 마커, REVIEW_LOOP_ESCALATE 마커, 수정 파일 범위 명시. **감점**: 테스트 파일(G) 리뷰 결과 출력 형식 미정 |
| 제약 & 가드레일 | 15/15 | 파일 수정 금지, validator 중복 금지, 개인 취향 금지, 루프 한도 이중 명시 완전 |

**잔여 개선 포인트**
1. REVIEW_LOOP_ESCALATE 수신 후 메인 Claude 처리 흐름 명시
2. NICE TO HAVE 항목의 tech-debt 에픽 등록 자동화 절차
