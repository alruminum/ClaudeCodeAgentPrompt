# Phase 4: 스킬 컨텍스트 보호 (Skill Context Protection)

> **선행**: Phase 3 (세션 격리) 머지 필수.

---

## 배경

`/ux`, `/qa`, `/product-plan` 같은 스킬 실행 중에 훅이 "스킬 맥락"을 인지하지 못해 **정당한 Bash/Edit 호출을 차단한 사고**가 있었음. 훅 입장에서는 "지금 어떤 스킬이 돌고 있는지" 알 방법이 없어 일반 메인 Claude 규칙을 적용하게 됨.

또한 스킬이 여러 에이전트를 호출하는 중간에 Stop 훅이 조기 종료하거나, 스킬 결과를 기다리는 동안 훅이 오인으로 작업을 막는 케이스도 잠재.

---

## 목표

**현재 어떤 스킬이 활성인지**를 훅이 일관되게 인지하고, 스킬 성격에 따라 적절한 보호(조기 종료 방지, 오인 차단 방지)를 적용한다.

---

## 커버리지

### 해결한다
- 스킬 실행 중 훅이 스킬 맥락을 읽어 판정에 반영
- 스킬이 오래 도는 경우 Stop 훅의 조기 종료 방지
- 스킬 종료 시 상태가 확실히 청소됨 (OMC cancel-skill-active-state 결함 회피)
- 스킬별 보호 강도 차등 (짧은 스킬 vs 긴 스킬)

### 해결하지 않는다
- 스킬 내부 에이전트 호출 순서 강제 (이건 스킬 md 역할)
- 스킬 실패 복구/재시작

---

## 참고 패턴 (OMC)

OMC `skill-active-state.json` 모델:

- Skill 툴 PreToolUse에서 활성 상태 기록 (skill 이름, 시작시각, 세션 ID)
- 보호 레벨 3단: **light / medium / heavy** (최대 강화 횟수, stale TTL 차등)
- Skill 툴 PostToolUse에서 해제
- Stop 훅이 활성 상태 보이면 재강화 메시지 주입 (조기 종료 방지)
- `/cancel` 계열 명령이 해당 상태 파일 명시적 삭제

OMC 결함(`docs/cancel-skill-active-state-gap.md`)에서 배운 것:
- 상태 청소 책임자가 여러 곳이면 한 곳 누락 시 상태가 TTL까지 잔존 → 재강화 루프에 빠짐
- 청소 책임자를 단일 지점으로 일원화 (쓰는 자가 지운다 원칙)

---

## 스킬 보호 분류 (초안)

스킬 성격별 보호 강도. 최종 분류는 구현 시 조정.

| 레벨 | 특징 | 대상 (초안) |
|---|---|---|
| **none** | 즉시 종료 / 읽기 전용 | `harness-status`, `harness-monitor`, `harness-kill`, `harness-test`, `deliver`, `doc-garden` |
| **light** | 짧은 상호작용 | `fewer-permission-prompts`, `update-config`, `keybindings-help` |
| **medium** | 다중 에이전트 호출 | `product-plan`, `ux`, `qa`, `init-project` |
| **heavy** | 장시간 루프 | `ralph`, `loop`, `schedule` |

TTL · 재강화 횟수는 OMC 값 참고 (light: 5분/3회, medium: 15분/5회, heavy: 30분/10회).

---

## 성공 기준

- 스킬 실행 중 훅이 `live.json.skill`을 읽어 스킬 맥락에서 판정
- `/ux` 실행 중 Bash·Edit 정당 호출이 오인 차단되지 않음 (실측 사고 재현 불가)
- 스킬 종료 직후 `skill-active-state.json` 삭제됨 (TTL 대기 불필요)
- 장시간 스킬이 Stop 훅에 의해 조기 종료되지 않음
- 스킬 크래시/사용자 강제 종료 시 다음 세션 시작에서 stale 청소됨

---

## 위험과 결정 지점

### D1. 스킬 보호 대상과 레벨 분류 확정
각 스킬이 어느 레벨에 속하는지 결정 필요. 과보호하면 정상 종료가 차단됨. 초안을 바탕으로 관측 후 조정.

### D2. 중첩 스킬 처리
스킬 안에서 다른 스킬이 호출되는 경우 `live.json.skill` 덮어쓰기. 일단 **last-write-wins** (가장 최근 활성 스킬만 추적). 필요 시 스택 구조로 확장.

### D3. Stop 훅 재강화 메시지의 침해성
재강화가 잦으면 모델 컨텍스트 낭비. 횟수 한도(max_reinforcements) 필요.

---

## 구현 단계

### Phase 4.A — Skill 상태 기록/해제
**목표**: Skill 툴 이벤트에서 상태 파일 쓰기/지우기.
- PreToolUse(Skill)에서 `skill-active-state.json` + `live.json.skill` 기록
- PostToolUse(Skill)에서 둘 다 소거
- 기존 훅들이 `live.json.skill`을 읽어 판정 로직에 반영

**검증 가능 기준**: 스킬 호출 시 파일 생성·소거 사이클 확인, `/ux` 맥락에서 훅 오인 차단 재현 불가.

### Phase 4.B — Stop 훅 보호
**목표**: 활성 스킬이 있으면 조기 종료 방지 + TTL/횟수 기반 자동 해제.
- Stop 훅에서 skill-active-state 확인 → 재강화 메시지 주입
- max_reinforcements / stale_ttl_ms 도달 시 강제 해제
- `/harness-kill` 등 취소 경로에서 명시적 해제

**검증 가능 기준**: 장시간 스킬이 Stop에 잘리지 않음, TTL 지나면 자동 해제됨, 취소 시 즉시 해제됨.

---

## 비스코프

| 항목 | 이유 |
|---|---|
| 스킬 스택 구조 (중첩 추적) | 필요 시 추가 — 현재 middle-case 적음 |
| 스킬별 권한 매트릭스 | 현재 훅은 에이전트 기준. 스킬 기준 별도 매트릭스는 과함 |
| 스킬 실행 로그 집계 | harness-review 범위 |
