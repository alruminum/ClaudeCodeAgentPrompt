# 설계 루프 (System Design)

진입 조건: 유저 승인 ① 완료 (기획-UX 루프에서 전달)
종료 게이트: **디자인 승인** (architecture.md + design-handoff.md 확정)

> 이전: [기획-UX 루프](plan.md)
> 다음: [구현 루프](impl.md)

**오케스트레이션 주체**: 메인 Claude (하네스 자동이 아닌 메인 Claude가 직접 병렬 호출)

---

```mermaid
flowchart TD
    APPROVE_1{{"유저 승인 ① 완료\n(PRD + UX Flow)"}}

    PARALLEL{{"병렬 실행"}}

    ARC_SD["architect\n@MODE:ARCHITECT:SYSTEM_DESIGN\n(ux-flow.md 참조)"]
    DES["designer ONE_WAY 순차\n(UX Flow 디자인 테이블 기반)\nskip_issue_creation: true\nsave_handoff_to: docs/design-handoff.md"]

    SDR{"SYSTEM_DESIGN_READY"}
    SGE["SPEC_GAP_ESCALATE"]:::escalation
    DHO{"DESIGN_HANDOFF\n→ docs/design-handoff.md"}

    VAL_DV["validator\n@MODE:VALIDATOR:DESIGN_VALIDATION"]

    DRF{"DESIGN_REVIEW_FAIL"}
    DRP{"DESIGN_REVIEW_PASS"}
    ARC_REDO["architect 재설계\n(max 1회)"]
    DRE["DESIGN_REVIEW_ESCALATE"]:::escalation

    USER_DESIGN{{"디자인 승인\n(architecture.md + Pencil 확인)"}}
    NEXT["→ 구현 루프\n(impl.md)"]

    APPROVE_1 --> PARALLEL
    PARALLEL --> ARC_SD
    PARALLEL --> DES

    ARC_SD -->|"SYSTEM_DESIGN_READY"| SDR
    ARC_SD -->|"마커 없음"| SGE

    DES -->|"DESIGN_HANDOFF"| DHO

    SDR --> VAL_DV
    VAL_DV --> DRF
    VAL_DV --> DRP

    DRF --> ARC_REDO
    ARC_REDO -->|재FAIL| DRE
    ARC_REDO -->|PASS| DRP

    DRP --> USER_DESIGN
    USER_DESIGN --> NEXT

    classDef escalation stroke:#f00,stroke-width:2px
```

---

## ���렬 실행 상세

### architect(SD) — 하네스 경유

`executor.py` 경유 (기존 패턴). ux-flow.md를 참조해서 화면 구조 기반 시스템 설계.

```
@MODE:ARCHITECT:SYSTEM_DESIGN
@PARAMS: { "plan_doc": "prd.md", "ux_flow_doc": "docs/ux-flow.md" }
```

### designer — Agent 도구 직접 호출 (하네스 밖)

UX Flow Doc의 **디자인 테이블**에서 대상 화면을 추출 → 화면별 ONE_WAY 순차 호출.
상세 designer 동작은 [디자인 루프](design.md) 참조.

추가 파라미터:
- `skip_issue_creation: true` — Phase 0-0 (GitHub 이슈 생성) 스킵
- `save_handoff_to: docs/design-handoff.md` — DESIGN_HANDOFF를 파일로 저장

```
@MODE:DESIGNER:SCREEN_ONE_WAY
@PARAMS: {
  "target": "[디자인 테이블 화면명]",
  "ux_goal": "[UX Flow Doc 인터랙션/와이어프레임 기반]",
  "skip_issue_creation": true,
  "save_handoff_to": "docs/design-handoff.md"
}
```

### 한쪽 실패 시

- architect 실패 + designer 성공 → architect만 재시도, design-handoff.md 보존
- architect 성공 + designer 실패 → designer만 재시도, architecture.md 보존
- 양쪽 실패 → 메인 Claude 보고

---

## UI 없는 기능 (ux-architect 스킵)

기획-UX 루프에서 ux-architect를 스킵한 경우:
- designer 호출 없음 (디자인 테이블이 비어있으므로)
- architect(SD)만 실행 → validator(DV) → 디자인 승인 (Pencil 확인 없이 architecture.md만 검토)

---

## 체크포인트

| 산출물 | 존재 시 스킵 |
|--------|-------------|
| `docs/architecture.md` | architect(SD) 스킵 |
| `docs/design-handoff.md` | designer 스킵 |

---

## 마커 레퍼런스

### 인풋 마커

| @MODE | 대상 에이전트 | 호출 시점 |
|---|---|---|
| `@MODE:ARCHITECT:SYSTEM_DESIGN` | architect | 유저 승인 ① 후 시스템 설계 (ux-flow.md 참조) |
| `@MODE:DESIGNER:SCREEN_ONE_WAY` | designer | 디자인 테이블 기반 화면별 순차 호출 |
| `@MODE:VALIDATOR:DESIGN_VALIDATION` | validator | SYSTEM_DESIGN_READY 후 설계 검증 |

### 아웃풋 마커

| 마커 | 발행 주체 | 다음 행동 |
|------|-----------|-----------|
| `SYSTEM_DESIGN_READY` | architect | validator Design Validation |
| `SPEC_GAP_ESCALATE` | plan_loop (architect 마커 누락 시 자동) | 메인 Claude 보고 후 대기 |
| `DESIGN_HANDOFF` | designer | docs/design-handoff.md에 저장 |
| `DESIGN_REVIEW_PASS` | validator | 디자인 승인 게이트 |
| `DESIGN_REVIEW_FAIL` | validator | architect 재설계 (max 1회) |
| `DESIGN_REVIEW_ESCALATE` | validator | 메인 Claude 보고 후 대기 |
