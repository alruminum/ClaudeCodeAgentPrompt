# 구현 루프 (Impl)

진입 조건: READY_FOR_IMPL 또는 plan_validation_passed

---

## depth (루프 깊이)

| depth | 실행 단계 | 사용 조건 | 머지 조건 |
|---|---|---|---|
| `fast` | engineer → validator → commit → merge (LLM 2회, 테스트·보안·리뷰 스킵) | impl에 `(MANUAL)` 태그만 있을 때 / 변수명·설정값 등 단순 변경 | 없음 |
| `std` | engineer → test-engineer → vitest → validator → commit → merge (LLM 3회) | 일반 구현 (기본값) | validator_b_passed |
| `deep` | engineer → test-engineer → vitest → validator → pr-reviewer → security-reviewer → commit → merge (LLM 5회) | impl에 `(BROWSER:DOM)` 태그 있을 때, 또는 보안·품질 게이트 필요 시 | pr_reviewer_lgtm + security_review_passed |

자동 선택 규칙 (`--depth` 미지정 시):
- impl 파일에 `(MANUAL)` 태그만 있고 `(TEST)` `(BROWSER:DOM)` 없음 → `fast` 자동
- impl 파일에 `(BROWSER:DOM)` 태그 있음 → `deep` 자동
- 그 외 → `std`

---

## 재진입 상태 감지

구현 루프 재진입 시 이전 실행의 완료 단계를 감지해 스킵한다.

```mermaid
flowchart TD
    RE_ENTRY{{"진입 시 체크"}}
    RE_PV{{"plan_validation_passed 플래그?"}}
    RE_IMPL{{"impl 파일 존재?"}}

    RE_ENTRY --> RE_PV
    RE_PV -->|YES| ENG_DIRECT["engineer 루프 직접 진입\n(architect + validator 스킵)"]
    RE_PV -->|NO| RE_IMPL
    RE_IMPL -->|YES| VAL_PV["validator Plan Validation\n(architect 스킵)"]
    RE_IMPL -->|NO| ARC_START["architect부터 (기본)"]
```

## 흐름

```mermaid
flowchart TD
    RFI{"READY_FOR_IMPL\n(impl 파일 경로 확정)"}

    subgraph ATTEMPT_LOOP["attempt loop (MAX 3회)"]
        ENG["engineer\n@MODE:ENGINEER:IMPL"]
        SPEC_CHK{{"SPEC_GAP_FOUND?"}}

        ARC_SG["architect\n@MODE:ARCHITECT:SPEC_GAP"]
        IMPL_ESC_SG["IMPLEMENTATION_ESCALATE"]:::escalation

        SRC_CHK{{"src/** 변경 있음?"}}

        TE["test-engineer\n@MODE:TEST_ENGINEER:TEST"]
        TF_CHK{{"TESTS_FAIL 분류"}}
        TE_SELF["test-engineer 자체 수정\n(max 2회, attempt 불변)"]

        VITEST["harness/impl-process.sh\n→ vitest run\n(ground truth)"]

        VAL_CV["validator\n@MODE:VALIDATOR:CODE_VALIDATION"]
    end

    subgraph DEEP_ONLY["deep only"]
        PR_REV["pr-reviewer\n@MODE:PR_REVIEWER:REVIEW"]
        SEC_REV["security-reviewer\n@MODE:SECURITY_REVIEWER:AUDIT"]
    end

    COMMIT["git commit\n(feature branch)"]
    MERGE["merge_to_main\n(--no-ff)"]
    MCE["MERGE_CONFLICT_ESCALATE"]:::escalation
    HD{"HARNESS_DONE"}
    STORIES["메인 Claude:\nstories.md 체크 +\nGitHub Issue 업데이트"]
    USER_REPORT{{"유저 보고 후 대기"}}
    PUSH["유저 승인 → git push"]
    IMPL_ESC["IMPLEMENTATION_ESCALATE\n(3회 실패)"]:::escalation

    %% 노트: fail_type?, fail_context? 는 재시도 시 선택 파라미터
    RFI --> ENG
    ENG -->|"impl_path, fail_type?, fail_context?"| SPEC_CHK
    SPEC_CHK -->|YES| ARC_SG
    ARC_SG --> SG_RESULT{{"architect 결과?"}}
    SG_RESULT -->|SPEC_GAP_RESOLVED| SGR
    SG_RESULT -->|PP_ESCALATION| PP_ESC["product-planner\n에스컬레이션"]:::escalation
    SG_RESULT -->|TECH_CONSTRAINT| TC_ESC["기술 제약 충돌\n에스컬레이션"]:::escalation
    SGR --> SG_LIMIT{{"spec_gap_count > 2?"}}
    SG_LIMIT -->|YES| IMPL_ESC_SG
    SG_LIMIT -->|NO| ENG

    SPEC_CHK -->|NO| SRC_CHK
    SRC_CHK -->|YES| DEPTH_TE{{"depth = fast?"}}
        DEPTH_TE -->|YES| VAL_CV
        DEPTH_TE -->|NO| TE
    TE -->|"impl_path, src_files"| TF_CHK
    TF_CHK -->|IMPLEMENTATION_BUG| FAIL_ROUTE
    TF_CHK -->|"TEST_CODE_BUG\nFLAKY"| TE_SELF
    TE_SELF --> TE_LIMIT{{"TE_SELF > 2?"}}
        TE_LIMIT -->|NO| TE
        TE_LIMIT -->|"YES (FLAKY)"| RECLASS["재분류: IMPLEMENTATION_BUG"]
        TE_LIMIT -->|"YES (TEST_CODE_BUG)"| FAIL_ROUTE
        RECLASS --> FAIL_ROUTE

    TF_CHK -->|TESTS_PASS| VITEST
    VITEST -->|"실패 (fail_type=test_fail)"| FAIL_ROUTE
    VITEST -->|통과| VAL_CV

    SRC_CHK -->|NO| VAL_CV
    VAL_CV -->|"impl_path, src_files"| VAL_RESULT

    VAL_RESULT{{"PASS / FAIL / SPEC_MISSING"}}
    VAL_RESULT -->|FAIL| FAIL_ROUTE
    VAL_RESULT -->|SPEC_MISSING| SM_RECOVER["architect MODULE_PLAN\n(impl 복구)"]:::escalation
    VAL_RESULT -->|PASS| DEPTH_CHK

    DEPTH_CHK{{"depth?"}}
    DEPTH_CHK -->|deep| PR_REV
    DEPTH_CHK -->|"std/fast"| COMMIT

    PR_REV -->|"impl_path, src_files"| PR_RESULT
    PR_RESULT{{"LGTM / CHANGES_REQUESTED"}}
    PR_RESULT -->|CHANGES_REQUESTED| FAIL_ROUTE
    PR_RESULT -->|LGTM| SEC_REV

    SEC_REV -->|"src_files"| SEC_RESULT
    SEC_RESULT{{"SECURE / VULNERABILITIES_FOUND"}}
    SEC_RESULT -->|"VULNERABILITIES_FOUND\n(HIGH/MEDIUM)"| FAIL_ROUTE
    SEC_RESULT -->|SECURE| COMMIT

    FAIL_ROUTE["FAIL → attempt++"]
    FAIL_ROUTE -->|"attempt < 3"| ENG
    FAIL_ROUTE -->|"attempt >= 3"| IMPL_ESC

    COMMIT --> MERGE
    MERGE -->|충돌| MCE
    MERGE -->|성공| HD
    HD --> STORIES
    STORIES --> USER_REPORT
    USER_REPORT --> PUSH

    classDef escalation stroke:#f00,stroke-width:2px
```

## 실패 유형별 수정 전략

FAIL 시 모든 유형을 동일하게 처리하지 않는다. `fail_type`에 따라 engineer에게 다른 컨텍스트와 지시를 전달한다.

| fail_type | 컨텍스트 (engineer에게 전달) | 지시 |
|---|---|---|
| `test_fail` | vitest 출력 전체 + 실패 테스트 파일 소스 | "테스트 실패. 구현 코드를 수정. 테스트 자체 수정 금지." |
| `validator_fail` | validator 리포트 + impl 파일 | "스펙 불일치. impl의 해당 항목 재확인 후 누락 구현." |
| `pr_fail` | MUST FIX 항목 목록 | "코드 품질 이슈. MUST FIX 항목만 수정. 기능 변경 금지." |
| `security_fail` | 취약점 리포트 (HIGH/MEDIUM 행) | "보안 취약점. 수정 방안 컬럼대로 적용." |

---

## 마커 레퍼런스

### 인풋 마커 (이 루프에서 호출하는 @MODE)

| @MODE | 대상 에이전트 | 호출 시점 |
|---|---|---|
| `@MODE:ENGINEER:IMPL` | engineer | 코드 구현 (초회 + 재시도) |
| `@MODE:TEST_ENGINEER:TEST` | test-engineer | src/** 변경 후 테스트 작성 |
| `@MODE:VALIDATOR:CODE_VALIDATION` | validator | 테스트 통과 후 코드 검증 |
| `@MODE:PR_REVIEWER:REVIEW` | pr-reviewer | [deep only] 코드 품질 리뷰 |
| `@MODE:SECURITY_REVIEWER:AUDIT` | security-reviewer | [deep only] 보안 감사 |
| `@MODE:ARCHITECT:SPEC_GAP` | architect | SPEC_GAP_FOUND 수신 시 |

### 아웃풋 마커 (이 루프에서 발생하는 시그널)

| 마커 | 발행 주체 | 다음 행동 |
|------|-----------|-----------|
| `SPEC_GAP_FOUND` | engineer | architect SPEC_GAP → attempt 동결 (spec_gap_count 별도) |
| `SPEC_GAP_RESOLVED` | architect | engineer 재시도 |
| `PRODUCT_PLANNER_ESCALATION_NEEDED` | architect | product-planner 에스컬레이션 |
| `TECH_CONSTRAINT_CONFLICT` | architect | 메인 Claude 보고 — 기술 제약 충돌 |
| `TESTS_PASS` | test-engineer | vitest run (ground truth) |
| `TESTS_FAIL` | test-engineer | 분류별 처리 (IMPLEMENTATION_BUG/TEST_CODE_BUG/FLAKY) |
| `PASS` | validator | pr-reviewer (deep) 또는 commit (std) |
| `FAIL` | validator | engineer 재시도 |
| `SPEC_MISSING` | validator | architect MODULE_PLAN (impl 복구) |
| `LGTM` | pr-reviewer | security-reviewer |
| `CHANGES_REQUESTED` | pr-reviewer | engineer 재시도 |
| `SECURE` | security-reviewer | commit |
| `VULNERABILITIES_FOUND` | security-reviewer | engineer 재시도 (HIGH/MEDIUM) |
| `IMPLEMENTATION_ESCALATE` | harness (3회 실패) | 메인 Claude 보고 |
| `MERGE_CONFLICT_ESCALATE` | harness (merge 충돌) | 메인 Claude 보고 |
| `HARNESS_DONE` | harness (commit 성공) | stories.md 체크 → 유저 보고 |
