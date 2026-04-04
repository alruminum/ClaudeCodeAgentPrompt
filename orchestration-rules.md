# 오케스트레이션 룰

모든 프로젝트에서 공통으로 적용되는 에이전트 워크플로우 규칙.
프로젝트 특화 룰은 `.claude/agents/orchestrator.md`에 추가로 정의한다.

---

## 작업 시작 전 필수 확인 (절대 원칙)

모든 구현·디자인·계획 작업 시작 전 반드시 아래 순서를 따른다:

1. 프로젝트에 `.claude/agents/orchestrator.md`가 존재하면 **Read해서 프로젝트 특화 워크플로우 확인**
2. 없으면 이 파일의 기본 룰을 따른다

건너뛰기 금지 — 사전에 파악했다고 생각해도 매번 확인.
**위반 시 즉시 중단. 확인 없이 진행한 모든 구현은 무효.**

---

## 메인 Claude 직접 구현 절대 금지 (절대 원칙)

**메인 Claude는 `src/**` 파일에 Edit/Write 툴을 직접 사용할 수 없다.**

- 이유 불문. 규모 불문. 상황 불문.
- 반드시 engineer 에이전트를 통해서만 구현.
- 메인 Claude가 직접 코드를 작성하면 구현-검토 루프가 무력화된다.

---

## 구현 루프 예외 없음 (절대 원칙)

`src/**` 변경이 발생하는 모든 작업은 규모와 관계없이 구현-검토 루프를 반드시 거친다.

**루프 생략이 허용되지 않는 상황 (예시가 아닌 열거):**
- "줄 수가 적은 변경"
- "간단한 UI 수정"
- "이미 아는 내용"
- "사용자가 빨리 해달라고 함"
- "플랜 모드 거부가 반복됨"
- "이전에 비슷한 작업을 했음"

위 상황 중 어느 것도 루프 생략의 근거가 되지 않는다.

---

## 에이전트 역할 경계 (절대 원칙)

**서브에이전트는 다른 서브에이전트를 스폰할 수 없다.**
메인 Claude가 직접 서브에이전트를 순서에 맞게 호출한다.

| 에이전트 | 역할 | 절대 하지 않는 것 |
|---|---|---|
| `designer` | variant 3개 생성 (ASCII 와이어프레임 + React/HTML 구현체) | 실제 소스 파일 수정 금지 |
| `design-critic` | 4개 기준 점수화 + PICK/ITERATE/ESCALATE 판정 | 파일 수정 금지 |
| `architect` | 설계 문서·impl 파일 작성 | 소스 코드 수정 금지 |
| `engineer` | 소스 코드 구현 | 설계 문서 수정 금지 |
| `validator` | PASS/FAIL 검증 리포트 | 파일 수정 금지 |
| `product-planner` | PRD/TRD 작성 | 코드·설계 문서 수정 금지 |

---

## UX 개편 워크플로우 (화면 전체 변경 시 — 절대 원칙)

Stitch를 사용하는 화면 전체 UX 개편 시 아래 순서를 반드시 따른다.
컴포넌트 수준 변경은 아래 "디자인 이터레이션 루프"를 따른다.

```
Step 0. 유저 → 디자이너: 디자인 요청
        디자이너: PRD 대조
        ├─ 단순 UX 수정 → Step 1 진행
        └─ PRD 변경 필요 → 기획자 에스컬레이션
             → 기획자: 영향 리포트 작성 → 유저 검토 후 진행 여부 결정

Step 1. 디자이너: 5개 ASCII 와이어프레임 생성
Step 2. 디자인 검수 에이전트: 5개 중 3개 선별
             → ASCII 와이어프레임 포함 선별 리포트 → 유저 대기
             ⛔ 유저 승인 없이 Stitch 진행 절대 금지
Step 3. 유저: 3개 확인 후 승인 (전체 or 일부)
Step 4. 디자이너: 승인된 안을 Stitch 렌더링 → 유저에게 제시
Step 5. 유저: 1개 선택 → 아키텍트에게 바로 전달
             ⛔ 이 단계에서 PRD 재대조 불필요 (Step 0에서 완료)
```

> 아키텍트는 impl 계획 중 PRD 위반 발견 시 기획자 에스컬레이션 가능 (별도 경로).

---

## 디자인 이터레이션 루프

```
[최대 3회]

1. designer: 3가지 미적 방향의 variant 생성
2. design-critic: 4개 기준 점수화 후 판정
   - PICK     → 유저에게 PICK variant + 리포트 전문 출력 후 대기
               ⛔ 자동 impl 절대 금지 — 유저 명시적 승인 필요
   - ITERATE  → 피드백 포함해 designer 재실행 (최대 3회)
   - ESCALATE → 유저에게 3개 variant 전체 보고, 유저가 직접 선택
3회 후 PICK 없음 → ESCALATE

3. 유저 명시적 승인 → engineer가 실제 파일에 PICK variant 적용
```

> design-critic 리포트는 요약 없이 전문(점수표 + 판정 근거) 그대로 출력.

---

## 작업 유형 분류 (architect 호출 전 필수)

메인 Claude는 architect Mode B를 호출하기 전에 작업 유형을 판단한다.

| 작업 유형 | 판단 기준 | architect 호출 시 필수 명시 |
|---|---|---|
| 버그픽스 | 이슈 레이블에 `bug` 포함 | 프롬프트 첫 줄에 `버그픽스 —` 명시 |
| 신규 기능 | 이슈 레이블에 `feat` 또는 신규 Epic | 일반 Mode B 호출 |
| 리팩토링/기술 에픽 | 기능 변경 없이 코드 구조 변경 | Mode E 호출 |

**버그픽스 호출 예시:**
```
Mode B — 버그픽스: [이슈 제목]
이슈: #NNN (bug 레이블)
...
```

버그픽스 시 구현 중 추가 수정이 발생하면:
- 별개 이슈 등록 금지
- 원래 이슈 체크리스트에 항목 추가
- 커밋 메시지는 원래 이슈 번호 참조

---

## 구현-검토 루프

```
[Phase 1 — 설계]
  architect: impl/NN-*.md 작성

[Phase 2 — 설계 검증] ⛔ 건너뛰기 절대 금지
  validator: impl 파일 검토 → PASS / FAIL
  → PASS: 유저에게 결과 보고 + 승인 대기
          ⛔ 승인 없이 Phase 3 진입 절대 금지
  → FAIL: 피드백 → architect 재보강 → validator 재검증 (최대 1회)
          → 재검증 결과도 유저 보고 후 대기

[Phase 3 — 구현-검토 (최대 3회)]
  engineer: impl 파일 기반 구현
  test-engineer: 테스트 코드 작성 + 실행 → TESTS_PASS / TESTS_FAIL
    → TESTS_FAIL: 리포트 출력 → engineer 재구현 (loop+1)
    ⛔ TESTS_PASS 없이 validator 호출 금지 (훅 강제)
  validator: 스펙 vs 구현 비교 → PASS / FAIL
  → FAIL: 리포트 전문 출력 → engineer 재구현 (loop+1)
  → PASS:
    pr-reviewer: 코드 품질 리뷰 → LGTM / CHANGES_REQUESTED
    → CHANGES_REQUESTED(MUST FIX): 리포트 출력 → engineer 재구현 (loop+1)
    → LGTM:
      해당 태스크 체크
      → validator + pr-reviewer 리포트 전문 출력
      → git commit ⛔ pr-reviewer LGTM 없이 커밋 금지 (훅 강제)
      → 커밋 해시 출력 후 대기 ⛔ 자동 다음 모듈 진입 금지
  3회 후 FAIL/CHANGES_REQUESTED: 유저 에스컬레이션
```

> 모든 리포트는 요약 없이 전문 그대로 출력.
> LGTM의 NICE TO HAVE 항목은 커밋 메시지 또는 백로그에 기록.
> LGTM 후에도 항상 유저 보고 후 대기.

---

## 하네스 에이전트 동기화 규칙

이 파일의 워크플로우가 변경되면 아래 파일도 반드시 함께 업데이트한다.
별도 지시 없이도 적용 — 룰 변경과 에이전트 업데이트는 세트.

| 변경 내용 | 업데이트 대상 파일 | 업데이트 위치 |
|---|---|---|
| 구현-검토 루프 순서/조건 | `.claude/agents/harness-executor.md` | Phase 1 실행 루프 |
| 디자인 이터레이션 루프 | `.claude/agents/harness-executor.md` | Phase 0.5 디자인 루프 분기 |
| 에이전트 역할 경계 | `.claude/agents/harness-executor.md` | 역할 경계 섹션 |
| architect Mode 추가/변경 | `CLAUDE.md` (프로젝트) | 에이전트 호출 규칙 > architect Mode 상세 표 |
