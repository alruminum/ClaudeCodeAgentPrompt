# 디자인 루프 (Design) — v3 Pencil MCP 기반

진입 조건: impl 파일에 UI 키워드 감지 + design_critic_passed 없음

---

## 모드 선택

| 모드 | 진입 플래그 | 시안 수 | 크리틱 |
|---|---|---|---|
| **DEFAULT** | (미지정, 기본값) | 1 variant | 없음 — 유저 직접 확인 |
| **CHOICE** | `--choice` | 3 variants | PASS/REJECT per variant → 유저 PICK |
| **UX_REDESIGN** | `--ux-redesign` | 5→3 → variant A/B/C | UX_SHORTLIST 경유 |

---

## DEFAULT 모드 흐름 (1 variant, 크리틱 없음)

```mermaid
flowchart TD
    DES_D["designer
@MODE:DESIGNER:DEFAULT"]
    P0_D["Phase 0: 컨텍스트 수집
+ Pencil 캔버스 준비"]
    P1_D["Phase 1: variant-A 1개 생성
(Pencil batch_design)
+ 애니메이션 스펙
+ get_screenshot"]
    DRR_D{"DESIGN_READY_FOR_REVIEW"}

    USER_CHK{{"유저 직접 확인
Pencil 캔버스에서 확인 후
APPROVE / REJECT 입력"}}

    DES_RETRY_D["designer 재시도
(max 3회)"]
    DLE_D["DESIGN_LOOP_ESCALATE"]:::escalation

    HANDOFF_D{"DESIGN_HANDOFF"}
    P4_D["Phase 4: 코드 생성
(design-variants/)"]
    IMPL_CHK_D{{"impl 파일 영향 있음?"}}
    ARC_MP_D["architect
@MODE:ARCHITECT:MODULE_PLAN"]
    RFI_D{"READY_FOR_IMPL"}
    KEEP_D["기존 impl 파일 유지"]
    FLAG_D["/tmp/{prefix}_design_critic_passed
플래그 생성"]
    USER_APPROVE_D{{"유저 승인 대기"}}
    IMPL_ENTRY_D["→ 구현 루프 진입"]

    DES_D --> P0_D
    P0_D --> P1_D
    P1_D --> DRR_D
    DRR_D --> USER_CHK
    USER_CHK -->|"APPROVE"| HANDOFF_D
    USER_CHK -->|"REJECT"| DES_RETRY_D
    DES_RETRY_D -->|"3회 초과"| DLE_D
    DES_RETRY_D -->|"3회 이내"| P1_D

    HANDOFF_D --> P4_D
    P4_D --> IMPL_CHK_D
    IMPL_CHK_D -->|YES| ARC_MP_D
    ARC_MP_D -->|"design_doc, module"| RFI_D
    IMPL_CHK_D -->|NO| KEEP_D
    RFI_D --> FLAG_D
    KEEP_D --> FLAG_D
    FLAG_D --> USER_APPROVE_D
    USER_APPROVE_D --> IMPL_ENTRY_D

    classDef escalation stroke:#f00,stroke-width:2px
```

---

## CHOICE 모드 흐름 (3 variants, 크리틱 PASS/REJECT)

```mermaid
flowchart TD
    DES["designer
@MODE:DESIGNER:CHOICE"]
    P0["Phase 0: 컨텍스트 수집
+ Pencil 캔버스 준비"]
    P1["Phase 1: variant A/B/C 3개 생성
(Pencil batch_design)
+ 애니메이션 스펙
+ get_screenshot × 3"]
    DRR{"DESIGN_READY_FOR_REVIEW
+ 스크린샷 3개"}

    CRITIC["design-critic
@MODE:CRITIC:REVIEW
(variant별 PASS/REJECT)"]

    APPROVED{"VARIANTS_APPROVED
(1개 이상 PASS)"}
    ALL_REJ{"VARIANTS_ALL_REJECTED"}
    DES_RETRY["designer 재시도
(max 3회, 피드백 누적)"]
    DLE["DESIGN_LOOP_ESCALATE"]:::escalation

    PHASE3{{"Phase 3: 유저 PICK
Pencil에서 PASS된 variant 확인 후
A/B/C 입력"}}
    HANDOFF{"DESIGN_HANDOFF"}

    P4["Phase 4: 코드 생성
(batch_get 확정 프레임 읽기
→ 디자인 토큰 + 컴포넌트 구조
+ 애니메이션 스펙 → 코드)
출력: design-variants/"]

    IMPL_CHK{{"impl 파일 영향 있음?"}}
    ARC_MP["architect
@MODE:ARCHITECT:MODULE_PLAN"]
    RFI{"READY_FOR_IMPL"}
    KEEP["기존 impl 파일 유지"]

    FLAG["/tmp/{prefix}_design_critic_passed
플래그 생성"]
    USER_APPROVE{{"유저 승인 대기"}}
    IMPL_ENTRY["→ 구현 루프 진입"]

    DES --> P0
    P0 --> P1
    P1 --> DRR
    DRR --> CRITIC
    CRITIC -->|"variant별 채점"| APPROVED
    CRITIC -->|"전체 기준 미달"| ALL_REJ

    APPROVED --> PHASE3
    ALL_REJ -->|feedback| DES_RETRY
    DES_RETRY -->|"3회 초과"| DLE
    DES_RETRY -->|"3회 이내"| P1

    PHASE3 --> HANDOFF
    HANDOFF --> P4
    P4 --> IMPL_CHK
    IMPL_CHK -->|YES| ARC_MP
    ARC_MP -->|"design_doc, module"| RFI
    IMPL_CHK -->|NO| KEEP
    RFI --> FLAG
    KEEP --> FLAG
    FLAG --> USER_APPROVE
    USER_APPROVE --> IMPL_ENTRY

    classDef escalation stroke:#f00,stroke-width:2px
```

---

## 마커 레퍼런스

### 인풋 마커 (이 루프에서 호출하는 @MODE)

| @MODE | 대상 에이전트 | 호출 시점 |
|---|---|---|
| `@MODE:DESIGNER:DEFAULT` | designer | Pencil MCP 기반 1 variant 생성 (기본값) |
| `@MODE:DESIGNER:CHOICE` | designer | --choice 플래그 시 3 variant 생성 |
| `@MODE:DESIGNER:UX_REDESIGN` | designer | UX 전면 개편 요청 시 |
| `@MODE:CRITIC:REVIEW` | design-critic | CHOICE 모드 — 3 variant PASS/REJECT 심사 |
| `@MODE:CRITIC:UX_SHORTLIST` | design-critic | UX 개편 5→3 선별 |
| `@MODE:ARCHITECT:MODULE_PLAN` | architect | DESIGN_HANDOFF 후 impl 영향 있을 때 |

### 아웃풋 마커 (이 루프에서 발생하는 시그널)

| 마커 | 발행 주체 | 다음 행동 |
|------|-----------|-----------|
| `DESIGN_READY_FOR_REVIEW` | designer | DEFAULT: 유저 직접 확인 / CHOICE: design-critic 호출 |
| `VARIANTS_APPROVED` | design-critic (CHOICE) | 1개 이상 PASS — Phase 3 유저 PICK 안내 |
| `VARIANTS_ALL_REJECTED` | design-critic (CHOICE) | 전체 REJECT — designer 재시도 (max 3회, 피드백 누적) |
| `UX_REDESIGN_SHORTLIST` | design-critic | 3개 선별 → Phase 1 variant 생성 |
| `DESIGN_LOOP_ESCALATE` | designer (3회 초과) | 유저 직접 선택 |
| `DESIGN_HANDOFF` | designer Phase 4 (유저 선택 후) | architect Module Plan (영향 시) → 구현 루프 |

---

## 의존성

- **Pencil.dev** 설치 필요 (VS Code 확장 또는 데스크톱 앱)
- **Pencil MCP 서버** 활성화 필요
- 사용 MCP 도구: `batch_design`, `batch_get`, `get_screenshot`, `get_editor_state`
- 추가 비용: $0 (Pencil.dev 얼리 액세스 무료)
