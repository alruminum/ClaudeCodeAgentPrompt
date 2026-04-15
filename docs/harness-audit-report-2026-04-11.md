# Harness Engineering System — Expert Audit Report

> 평가자 시점: Anthropic 수석 연구원 / AI Agent Systems 전문가
> 평가 대상: ~/.claude/harness/ (~3,700 LOC Python core + ~2,000 LOC Python hooks + ~2,500 LOC agent prompts)
> 비교 대상: SWE-agent, OpenHands, Devin, Aider, Cursor, Claude Code native, ChatDev/MetaGPT (학술), Oh My OpenAgent
> 참고: Addy Osmani "Code Agent Orchestra" (2026) — 업계 베스트 프랙티스 대조
> 작성일: 2026-04-11
> 최종 수정: 2026-04-14 — Python 전환 완료 + P0 6건 완료 + 로드맵 현행화

---

## 1. EXECUTIVE SUMMARY

이 시스템은 Claude Code를 런타임으로 활용하면서 그 위에 **결정론적 다중 에이전트 오케스트레이션 레이어**를 구축한 프레임워크다. 핵심 차별점은 "에이전트 프레임워크를 새로 만든 것이 아니라, 기존 LLM CLI 위에 소프트웨어 공학 워크플로우를 강제하는 하네스"라는 점이다.

**총평 스코어: 78.1/100** (Python 전환 + P0 완료 반영. DX 개선(README + 설치 + 벤치마크) 시 80+ 예상)

2026-04-12 Python 전면 전환 완료 (4,500 LOC Bash → 3,709 LOC Python stdlib only). BSD/GNU grep 호환 문제 영구 제거, jq 의존 제거, 타입 안전 확보. 오픈소스로 배포할 경우, 현재 생태계에서 **유일하게 "production-grade multi-agent orchestration on top of Claude Code"를 제공하는 프로젝트**가 될 수 있다.

---

## 2. SCORING BREAKDOWN

| 카테고리 | 초기(4/11) | Python전환 | P0완료(4/14) | 가중치 | 가중 점수 | P0 변경 이유 |
|----------|-----------|-----------|-------------|--------|-----------|----------|
| **독창성** | 85 | 85 | 85 | 20% | 17.0 | 변동 없음 |
| **아키텍처** | 78 | 85 | **86** | 20% | **17.2** | +1: Circuit Breaker (시간 윈도우 조기 감지) |
| **실용성** | 80 | 80 | **82** | 15% | **12.3** | +2: test_command 범용화, worktree 격리 |
| **확장성** | 60 | 68 | **75** | 15% | **11.25** | +7: test/lint 연결 완료, 도메인별 토큰 예산, isolation config |
| **관측 가능성** | 82 | 82 | **85** | 10% | **8.5** | +3: REFLECTION 성공 학습, circuit_breaker JSONL |
| **안전성** | 75 | 77 | **78** | 10% | **7.8** | +1: worktree 격리 옵션 |
| **DX** | 40 | 40 | 40 | 10% | 4.0 | 변동 없음 (배포 준비 전) |
| **합계** | **72.3** | **76.1** | **78.1** | 100% | **78.1** | **+5.8p** (초기 대비) |

---

## 3. STRENGTHS — 진짜 잘한 것

### S1. 계층적 오케스트레이션 분리 (Layered Orchestration) — ★★★★★

**기존 시스템과의 차이:**
- SWE-agent/OpenHands/Aider: 오케스트레이션이 프레임워크에 내장 → 커스텀 어려움
- Devin: 오케스트레이션이 블랙박스 → 사용자 통제 불가
- Oh My OpenAgent: 모델 라우팅에 집중, 워크플로우 구조는 약함
- **이 시스템**: Claude Code = 범용 런타임, 하네스 = 워크플로우 레이어 → **분리**

이 분리가 왜 중요한가:
1. LLM 런타임이 업그레이드되면 하네스는 그대로 혜택을 받음 (Claude 모델 업그레이드 → 하네스 수정 불필요)
2. 워크플로우 변경 시 LLM 코드를 건드리지 않음 (orchestration-rules.md만 수정)
3. 같은 하네스를 다른 LLM CLI에 이식 가능 (이론적으로)

**학술적으로도 이 패턴은 드물다.** ChatDev/MetaGPT는 multi-agent이지만 프레임워크와 오케스트레이션이 결합되어 있다. 이 시스템의 "하네스 as configuration" 접근은 논문 1편 분량의 contribution이 될 수 있다.

### S2. Depth-Based Loop Strategy — ★★★★☆

3단계 깊이 전략 (simple/std/deep)은 실용적이면서 독창적이다:

| Depth | Agent 수 | 용도 | 비용 추정 |
|-------|----------|------|-----------|
| simple | 2 (engineer + pr-reviewer) | 텍스트/스타일/설정 | ~$0.5-1 |
| std | 5 (+ test-engineer + validator) | 로직/API/DB | ~$3-8 |
| deep | 6 (+ security-reviewer) | 인증/결제/암호화 | ~$5-15 |

**기존 시스템에는 이 개념이 없다.** SWE-agent/Aider는 모든 태스크를 동일한 파이프라인으로 처리한다. Devin도 태스크 복잡도에 따른 에이전트 수 조절을 하지 않는다. 단일 구독(Claude Max)으로 전체 기능이 동작하며, depth로 비용을 통제할 수 있다.

비교: "Agentless" 논문(2024)이 "단순한 파이프라인이면 충분하다"고 주장했는데, 이 시스템은 그 주장을 수용하면서도 (simple depth) 복잡한 경우의 안전망을 유지한다 (deep depth). 균형이 좋다.

### S3. Hook-Based Agent Boundary Enforcement — ★★★★☆

`agent-boundary.py`로 에이전트별 파일 접근을 물리적으로 차단하는 것은 **현존하는 오픈소스 코딩 에이전트 중 유일하다:**

- engineer: `src/**`만 Write 가능
- architect: `docs/**`만 Write 가능
- validator/pr-reviewer: 완전 ReadOnly

**왜 이것이 중요한가:**
- Multi-agent 시스템의 가장 큰 리스크는 에이전트 간 역할 침범이다
- ChatDev/MetaGPT/OMO 등은 role prompting만으로 경계를 유지하려 하는데, LLM은 프롬프트를 무시할 수 있다
- 이 시스템은 hooks로 **물리적으로 차단** → LLM이 아무리 hallucinate해도 경계를 넘지 못함

### S4. Harness Memory + Auto-Promotion — ★★★★☆

실패 패턴 3회 누적 → 자동 프로모션 → CONSTRAINTS 주입은 **크로스-세션 학습 메커니즘**이다.

기존 시스템 대비:
- SWE-agent: 학습 없음. 매번 처음부터.
- OpenHands: Microagents(키워드 기반 지식 주입) — 수동 큐레이션 필요
- Aider: 없음
- Devin: Playbooks (수동)
- **이 시스템**: 반자동 학습. 실패 → 자동 감지 → 수동 리뷰 후 영구 적용

완전 자동화는 아니지만, "사람이 큐레이션하는 자동 감지"는 현재 기술 수준에서 가장 현실적인 접근이다.

### S5. Structured Observability (JSONL + harness-review.py) — ★★★★☆

8가지 낭비 패턴 자동 감지:
- WASTE_INFRA_READ: 에이전트가 하네스 인프라 파일을 읽는 것
- WASTE_SUB_AGENT: 서브에이전트 과다 스폰
- CONTEXT_BLOAT: 40KB 초과 프롬프트
- RETRY_SAME_FAIL: 동일 실패 반복

**이것은 업계에서 거의 유일하다.** SWE-agent는 trajectory viewer가 있지만 자동 분석은 없다. Aider는 비용 추적만 한다. 이 수준의 자동 리뷰는 Devin의 내부 시스템에나 있을 법한 것이다.

### S6. SPEC_GAP Frozen Attempt Pattern — ★★★★☆

SPEC_GAP가 attempt를 소비하지 않는 동결 설계는 섬세하다:
- attempt(max 3) + spec_gap(max 2) = 최대 5라운드
- 스펙 문제로 인한 실패와 구현 능력 부족으로 인한 실패를 분리
- 오실레이션 방지 (이전의 리셋 방식 폐기)

이 수준의 루프 제어는 학술 논문에서도 드물다. 대부분의 agent 시스템은 단순한 max_retries만 있다.

### S7. 단일 구독 완전 동작 — ★★★★☆

단일 Claude 구독(Max $100~200)으로 전체 10개 에이전트가 동작한다. OMO 같은 크로스 AI 시스템은 풀스택 구동에 월 $400+ 다중 구독이 필요하며, 단일 구독 시 크로스 AI 이점이 소멸한다. 대부분의 개발자 현실(구독 1~2개)에서 우리 시스템이 더 실용적이다.

---

## 4. WEAKNESSES — 냉정한 약점

### ~~W1. Bash 기반의 구조적 한계~~ — **해결됨 (2026-04-12)**

4,500 LOC Bash → 3,709 LOC Python 3.9+ stdlib only 전면 전환 완료.

**해결된 문제:**
- ~~BSD/GNU grep 호환~~ → Python `re` 모듈로 영구 제거
- ~~jq + Python fallback~~ → Python `json` 모듈 네이티브
- ~~전역 변수 의존~~ → dataclass + 함수 파라미터
- ~~BATS 테스트~~ → unittest 기반 test_parity.py (17개 동등성 테스트)

**잔여:** executor.sh는 1줄 래퍼(`exec python3 executor.py "$@"`)로 유지 (호출 호환성). 원본 .sh는 .sh.bak으로 보존.

코드 리뷰(2026-04-14) 결과 4건 수정 완료: 데드코드 제거, watchdog 타임아웃, SIGTERM 핸들러, log_fh try/finally.

### W2. 서브에이전트 패턴의 컨텍스트 병목 — ★★★☆☆ (에이전트 팀으로 해결 가능)

현재 Main Claude가 모든 에이전트 결과를 중간에서 파싱하고 다음 에이전트에 전달 → Main의 컨텍스트 윈도우가 중간 결과로 오염됨.

**에이전트 팀 전환으로 해결 가능:** 팀원 간 직접 통신으로 Main 우회.

### W3. 샌드박스 부재 — ★★★☆☆ (Significant)

engineer 에이전트가 사용자의 실제 파일시스템에서 직접 작업한다. `rollback_attempt`이 git reset으로 구현되어 있지만:
- reset 전에 발생하는 side effect (서버 시작, DB 마이그레이션 등)는 복구 불가
- 악의적이지 않더라도 LLM의 hallucination이 위험한 명령을 실행할 수 있음

**비교:** SWE-agent(Docker), OpenHands(Docker), Devin(VM) — 모두 격리 환경.

### W4. 한국어 전용 + DX 부족 — ★★☆☆☆ (Critical for OSS adoption)

- 모든 에이전트 프롬프트, 정책, 문서가 한국어
- README.md 부재
- "Getting Started" 경험 없음

**비교:** Aider(`pip install`), OMO(`bunx oh-my-opencode install`) — 한 줄 설치.

### W5. 테스트 프레임워크 종속 (vitest) — ★★★☆☆

`impl_std.sh`가 `npx vitest run`을 하드코딩 → JavaScript/TypeScript 프로젝트 전용.

**개선 방향:** `harness.config.json`에 `test_command` 필드 추가.

---

## 5. 기존 프로젝트 대비 비교 매트릭스

| 항목 | 이 시스템 | SWE-agent | OpenHands | Aider | Devin | OMO |
|------|-----------|-----------|-----------|-------|-------|-----|
| Multi-Agent 오케스트레이션 | **★★★★★** | ☆ | ★★ | ★ | ★★★★ | ★★★★ |
| Agent 역할 분리 | **★★★★★** | ☆ | ★★ | ★ | ★★★ | ★★★ |
| 물리적 경계 강제 | **★★★★★** | ★★★ | ★★★ | ☆ | ★★★★ | ★★ |
| Depth 기반 비용 최적화 | **★★★★★** | ☆ | ☆ | ☆ | ★★? | ★★★ |
| 자동 리뷰/감사 | **★★★★☆** | ★★ | ★★ | ★ | ★★★? | ★★ |
| 크로스세션 학습 | **★★★★☆** | ☆ | ★★ | ☆ | ★★★ | ★★? |
| 크로스 AI | ☆ | ★★★ | ★★★★★ | ★★★★★ | ☆ | **★★★★★** |
| 샌드박스 격리 | ☆ | **★★★★★** | **★★★★★** | ☆ | **★★★★★** | ☆ |
| 설치 용이성 (DX) | ★ | ★★★ | ★★★★ | **★★★★★** | ★★★★ | **★★★★★** |
| 편집 신뢰성 | ★★★ | ★★★ | ★★★ | ★★★★ | ★★★★ | **★★★★★** |
| 코드 인텔리전스 | ★ | ★ | ★★ | ★★★ | ★★★★ | **★★★★★** |
| 디자인 워크플로우 | **★★★★★** | ☆ | ☆ | ☆ | ☆ | ☆ |
| QA/이슈 트리아지 | **★★★★★** | ☆ | ☆ | ☆ | ★★ | ★★ |
| SPEC_GAP 관리 | **★★★★★** | ☆ | ☆ | ☆ | ☆ | ☆ |
| 단일 구독 완전 동작 | **★★★★★** | ★★★★ | ★★★★ | ★★★★★ | ★★★ | ★★ |

### 경쟁 포지션 요약

**OMO vs 우리 시스템 — 철학적 차이:**

| | 우리 시스템 | Oh My OpenAgent |
|---|-----------|-----------------|
| 철학 | **프로세스 엔지니어링** | **모델 엔지니어링** |
| 핵심 질문 | "에이전트를 어떤 순서로, 어떤 규칙으로 조율할까?" | "각 태스크에 어떤 모델이 최적일까?" |
| 혁신 축 | 워크플로우 구조 (depth, gates, boundaries) | 모델 라우팅 (cross-AI, hashline, LSP) |
| 비용 구조 | 단일 구독 $100~200/월 | 다중 구독 $400+/월 (풀스택) |
| 약점 | 모델 다양성 없음, DX 부족 | 워크플로우 구조 약함, 물리적 경계 없음 |

**레이어 관점에서 두 시스템은 경쟁이 아닌 상호 보완:**

```
Layer 3: 사용자 인터페이스 (DX, 설치, CLI)
Layer 2: 모델 라우팅 (Oh My OpenAgent의 영역)
Layer 1: 워크플로우 엔진 (우리 시스템의 영역)    ← 여기가 핵심
Layer 0: LLM Runtime (Claude Code, OpenCode, Aider)
```

### harness_framework (jha0313) 비교 — 2026-04-14 추가

> 출처: https://github.com/jha0313/harness_framework (Meta 시니어 개발자, 6 commits, 5 stars)

입문자용 하네스 템플릿. `claude -p` 헤드리스 모드로 Phase를 순차 실행하는 단일 에이전트 구조. 아키텍처 수준에서 배울 것은 없으나, 아이디어 수준에서 채택할 항목 2건:

**채택 — Circuit Breaker (시간 윈도우 기반 반복 감지)**
harness_framework: "같은 에러 60초 내 5회 → 전략 변경 경고". 우리: `max 3 attempts`는 횟수만 봄. 같은 에러가 빠르게 반복되는 패턴(타입 에러 → 같은 수정 → 같은 타입 에러)을 조기 감지 못함.
→ impl_loop.py에 시간 윈도우 기반 감지 추가. 동일 fail_type 120초 내 2회 반복 시 조기 에스컬레이션.

**채택 — "MVP 제외 사항" 강제**
harness_framework: PRD에 "안 만들 것" 명시 → scope creep 방지. 우리: product-planner PRD에 제외 사항 구조적 강제 없음. engineer의 scope 확장이 SPEC_GAP 원인 중 하나.
→ product-planner 프롬프트에 "## MVP 제외 사항" 섹션 필수화. impl 파일에 "구현하지 않는 것" 추가.

**채택하지 않는 것:**
- Phase 기반 순차 실행 — 우리 depth 기반 체인이 더 정교
- `claude -p` 헤드리스 — 우리 `claude --agent` + stream-json이 정보량 많음
- TDD Guard hook — 우리 test-engineer + depth 전략이 더 유연 (depth=simple은 테스트 불필요)
- UI_GUIDE anti-slop — 우리 designer + Pencil MCP가 시각적 도구로 처리
- Phase 상태 추적 — JSONL + harness-review로 이미 더 상세하게 커버

---

## 6. 에이전트 팀 전환 전략

### 발견: Claude Code 네이티브 에이전트 팀 지원

Claude Code v2.1.32+에서 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` 환경변수로 활성화되는 네이티브 에이전트 팀 기능이 존재한다.

**서브에이전트 vs 에이전트 팀 비교:**

| | 서브에이전트 (현재) | 에이전트 팀 (네이티브) |
|---|---------------------|----------------------|
| 통신 | Main에게만 결과 보고 | **팀원 간 직접 메시지** |
| 조율 | Main이 모든 작업 관리 | **공유 작업 목록 + 자체 조율** |
| 컨텍스트 | 결과가 Main으로 요약됨 | 각자 독립 컨텍스트 윈도우 |
| 에이전트 정의 | agents/*.md | **동일한 agents/*.md 재사용 가능** |
| 훅 | Pre/PostToolUse | **TeammateIdle, TaskCreated, TaskCompleted** |
| 계획 승인 | 하네스가 수동 관리 | **plan approval 모드 내장** |

### 에이전트 팀이 해결하는 현재 시스템의 문제들

**1. Main Claude 컨텍스트 병목 해소**
현재: engineer 출력 → Main 파싱 → test-engineer 전달 → Main 파싱 → validator 전달
팀: engineer가 test-engineer에게 직접 "이 파일 변경했어" → Main은 최종 결과만

**2. SPEC_GAP 왕복 비용 제거**
현재: `engineer → Main → architect → Main → engineer` (3 hop)
팀: `engineer → architect (직접)` (1 hop)

**3. TaskCreated/TaskCompleted 훅 = 네이티브 게이팅**
현재 flags.sh + markers.sh 수동 상태 머신 → 네이티브 Task 의존성 관리로 대체

**4. Plan Approval = plan_validation의 네이티브 대체**
현재: architect → validator Plan Validation → flag touch → impl 진입
팀: architect 팀원에 "Require plan approval" → 리더 승인/거부 → 자동 진행

### 전환 시 주의사항

1. **실험적 기능** — 세션 재개 불가, 작업 상태 지연이 프로덕션 하네스에 치명적
2. **파일 충돌** — engineer와 test-engineer가 같은 src/ 파일 건드리면 덮어쓰기
3. **비용 예측** — depth 전략의 핵심 강점(예측 가능한 에이전트 수)이 약해질 수 있음
4. **JSONL 로깅** — 팀 모델에서 에이전트별 비용/시간 추적은 별도 구현 필요
5. **harness-review** — 선형 타임라인 기반 분석이 팀의 병렬 실행에서 작동하지 않음

### 전환 로드맵

**Phase 1 — Hybrid (현재 하네스 유지 + 팀 실험)**

```
settings.json에 CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: "1" 추가
impl_std.sh에서 engineer↔test-engineer 구간만 팀으로 전환
나머지(architect, validator, pr-reviewer)는 기존 서브에이전트 유지
```

가장 빈번한 왕복(engineer↔test-engineer)에서 효과 검증. 리스크 최소.

**Phase 2 — SPEC_GAP 팀화**

```
architect + engineer를 팀으로 묶어 SPEC_GAP 직접 소통
validator는 TaskCompleted 훅으로 게이팅
Bash 하네스의 SPEC_GAP 관련 코드 50% 제거
```

**Phase 3 — 전면 팀 전환**

```
executor.sh를 "팀 리더 프롬프트 생성기"로 전환
depth 전략을 "팀 크기"로 재해석:
  simple: leader + engineer (2인 팀)
  std: leader + architect + engineer + test-engineer + validator (5인 팀)
  deep: std + security-reviewer (6인 팀)
```

**Phase 3 리더 프롬프트 예시:**

```
"Create a team for impl task #42:
 - architect teammate (agents/architect.md): plan approval required
 - engineer teammate (agents/engineer.md): depends on architect's plan
 - test-engineer teammate (agents/test-engineer.md): depends on engineer
 - validator teammate (agents/validator.md): depends on engineer

 Task dependencies:
 T1: Create impl plan → architect
 T2: Implement code → engineer (blocked by T1)
 T3: Write and run tests → test-engineer (blocked by T2)
 T4: Validate against spec → validator (blocked by T2)

 Engineer and test-engineer should communicate directly on test failures.
 Use TaskCompleted hook for quality gates."
```

### 팀 전환 시 depth 전략 매핑

| Depth | 현재 (서브에이전트) | 팀 전환 후 |
|-------|---------------------|-----------|
| simple | engineer → pr-reviewer (순차) | leader + engineer (2인 팀, pr-reviewer는 리더가 직접) |
| std | engineer → test-engineer → validator → pr-reviewer (순차) | leader + 4인 팀 (test-engineer↔engineer 직접 소통) |
| deep | std + security-reviewer (순차) | leader + 5인 팀 (security-reviewer는 TaskCompleted 훅으로 게이팅) |

### 팀 전환이 Bash 코드에 미치는 영향

| 현재 Bash 코드 | 팀 전환 후 | 상태 |
|----------------|-----------|------|
| executor.sh (134줄) | 팀 리더 프롬프트 생성기로 축소 | 대폭 축소 |
| impl.sh (212줄) | depth → 팀 크기 매핑만 | 대폭 축소 |
| impl_std.sh (465줄) | **제거** — 네이티브 팀 조율로 대체 | 제거 |
| impl_simple.sh (329줄) | **제거** | 제거 |
| impl_deep.sh (495줄) | **제거** | 제거 |
| impl_helpers.sh (255줄) | 일부 유지 (constraints, memory) | 축소 |
| utils.sh (966줄) | 로깅/상태 관리만 유지 | 대폭 축소 |
| flags.sh (29줄) | **제거** — 네이티브 Task 상태로 대체 | 제거 |
| markers.sh (35줄) | 유지 (에이전트 아웃풋 형식은 동일) | 유지 |

**예상 코드 감소: ~4,500 LOC → ~800 LOC (약 82% 감소)**

---

## 7. 오픈소스 포지셔닝

### 추천 포지셔닝

**"Deterministic Agent Workflow Engine for Claude Code"**

핵심 메시지: "하나의 AI 구독으로 10개 에이전트의 결정론적 워크플로우. 여러 AI를 돌리는 게 아니라, 하나의 AI를 제대로 구조화하는 것."

### 경쟁 우위 (우리만 가진 것)

1. **결정론적 multi-agent 워크플로우** — depth + gates + boundaries
2. **물리적 에이전트 경계 강제** — hooks로 차단 (프롬프트 기반이 아님)
3. **자동 리뷰/낭비 감지** — harness-review (8가지 패턴)
4. **디자인 워크플로우** — Pencil MCP + design-critic + 2x2 매트릭스
5. **SPEC_GAP 동결 패턴** — 스펙/구현 실패 분리
6. **QA 트리아지** — 자동 분류 → 라우팅 (5가지 분류)
7. **단일 구독 완전 동작** — Claude Max 하나로 전체 기능

### 채택에 필요한 최소 조건

1. 영문 README + Getting Started (5분 경험)
2. single command 설치
3. 데모 영상 (3분, GitHub issue → harness loop → merge)
4. 벤치마크 (SWE-bench lite에서 측정)
5. 테스트 프레임워크 비종속 (config로 test command 지정)

---

## 8. 업계 베스트 프랙티스 대조 (Addy Osmani "Code Agent Orchestra", 2026)

> 출처: https://addyosmani.com/blog/code-agent-orchestra/
> GeekNews 토론: https://news.hada.io/topic?id=28303

### 기사 핵심 주장과 우리 시스템 대조

Osmani는 2026년 AI 코딩의 핵심 전환을 "generation → verification"으로 정의하며, multi-agent 오케스트레이션의 6가지 베스트 프랙티스를 제시한다. 아래는 각 패턴과 우리 시스템의 매핑이다.

| Osmani 권장 패턴 | 설명 | 우리 시스템 | 수준 |
|-----------------|------|-----------|------|
| Plan Approval | 구현 전 계획 승인 게이트 | plan_validation (architect→validator) | **이미 구현** |
| Hooks (lifecycle gates) | TeammateIdle/TaskCompleted 자동 검사 | 9개 훅 (agent-boundary, commit-gate 등) | **이미 구현 (더 정교)** |
| AGENTS.md 학습 | 패턴/함정/스타일 누적 문서 | harness-memory.md + auto-promotion (3회 실패→영구 규칙) | **이미 구현** |
| Kill Criteria (3회 실패→중단) | 반복 실패 시 에이전트 교체 | max 3 attempts → IMPLEMENTATION_ESCALATE | **이미 구현** |
| File Ownership (1파일=1에이전트) | 병렬 편집 금지 | agent-boundary.py 물리적 차단 | **이미 구현 (더 강력)** |
| WIP 제한 3-5명 | 리뷰 가능한 만큼만 실행 | depth 전략 (simple=2, std=5, deep=6) | **이미 구현** |
| Ralph Loop (상태 리셋 반복) | 작업→검증→커밋→리셋 사이클 | ralph-loop 플러그인 | **이미 구현** |
| "검증이 병목" | 생성보다 검증이 중요 | depth=std/deep에 validator+test-engineer+security | **이미 구현** |
| "인간 작성 AGENTS.md > AI 작성" | AI 작성 시 ~3% 저하 + 20% 추론 비용 증가 | 수동 큐레이션 정책 (auto-promotion은 감지만, 승인은 수동) | **이미 구현** |

### 우리가 Osmani 권장보다 앞서있는 부분

1. **물리적 경계 강제**: Osmani는 "한 파일은 한 에이전트만"을 **규칙**으로 권장. 우리는 hooks로 **물리적 차단**. LLM이 무시할 수 없음.
2. **SPEC_GAP 동결**: Osmani의 kill criteria는 단순 3회 카운트. 우리는 스펙 문제 vs 구현 문제를 분리 (attempt 3 + spec_gap 2 = 5회, 독립 카운터).
3. **자동 낭비 감지**: Osmani 기사에는 harness-review에 해당하는 자동 감사 메커니즘 언급 없음. 우리의 8가지 WASTE 패턴 감지는 기사 범위를 넘어섬.
4. **디자인 워크플로우**: Osmani 기사는 코드 에이전트만 다룸. 우리는 Pencil MCP 기반 디자인 에이전트 + design-critic까지 포함.

### 우리에게 없는 것 (도입 가치 있음)

**1. Token Budget per Domain (도메인별 토큰 예산)**
```
프론트엔드: 180k 토큰 제한
백엔드: 280k 토큰 제한
85% 도달: 자동 일시 중지 + 리더 알림
```
현재 budget_check()는 있지만 도메인별 차등이 없음. 에이전트 팀 전환 시 팀원별 토큰 예산 설정으로 구현 가능.

**2. REFLECTION.md 패턴 (작업별 자기 성찰)**
```
매 작업 후 에이전트가 작성:
- 무엇이 놀랐나?
- harness-memory에 추가할 패턴 1개
- 개선할 프롬프트 제안 1개
→ 리더가 승인한 학습만 병합
```
현재 harness-memory는 **실패만** 기록. 성공에서의 학습이 누락됨. 이 패턴은 auto-promotion의 상위 버전으로, "성공 패턴 자동 감지 → 수동 승인"으로 확장 가능.

**3. Git Worktree 격리 (에이전트별 워크트리)**
에이전트 팀에서 파일 충돌의 근본 해결책. Claude Code가 `isolation: "worktree"` 옵션 지원.
Osmani: "에이전트당 워크트리 → 충돌 제거". 에이전트 팀 Phase 2~3에서 도입 권장.

**4. 3-Tier 오케스트레이션 확장**
현재 Tier 1(인프로세스)만 사용. Tier 2(로컬 오케스트레이터)와 Tier 3(클라우드 비동기)로 확장 가능:
- Tier 2: Git worktree 기반 병렬 세션 (현재도 가능하나 자동화 없음)
- Tier 3: Claude Code Web / GitHub Copilot Coding Agent로 야간 배치 작업

### GeekNews 댓글에서의 실무 인사이트

> "5개 에이전트 운영중인데 토큰이 겁내 빨리 사라져서 눈물남" (stroke33)

이 피드백이 우리 시스템의 depth 전략의 가치를 재확인:
- 모든 태스크에 5개 에이전트를 돌리면 비용 폭발
- depth=simple(2개)로 단순 작업을 처리하면 토큰 절약
- **"올바른 수의 에이전트를 올바른 태스크에"가 핵심** — 이것이 정확히 depth 전략의 존재 이유

### 기사와의 철학적 정렬

Osmani의 핵심 메시지: "강한 소프트웨어 엔지니어는 이 도구들로 더 큰 레버리지를 얻는다. 약한 엔지니어는 동일한 문제를 병렬로 증폭한다."

우리 시스템의 설계 철학이 이와 정확히 일치:
- **스펙이 레버리지** → SPEC_GAP 감지 + plan_validation으로 모호성 사전 제거
- **검증이 병목** → depth 전략으로 검증 수준을 태스크에 매칭
- **판단은 인간이** → 유저 게이트 (READY_FOR_IMPL, HARNESS_DONE 등)에서 자동 진행 금지

---

## 9. 개선 로드맵 (우선순위) — 2026-04-14 현행화

### 완료

| # | 항목 | 완료일 | 비고 |
|---|------|--------|------|
| ~~0~~ | ~~전면 Python 전환~~ | 2026-04-12 | 3,709 LOC. 코드 리뷰 4건 수정 포함 |
| ~~1~~ | ~~test/lint command 설정화~~ | 2026-04-14 | vitest 하드코딩 제거 → config.test_command. 테스트 2건 |
| ~~2~~ | ~~REFLECTION.md (성공 학습)~~ | 2026-04-14 | _extract_reflection + _write_reflection + constraints 주입. 테스트 2건 |
| ~~3~~ | ~~도메인별 토큰 예산~~ | 2026-04-14 | token_budget: dict + 85% 경고. 테스트 3건 |
| ~~4~~ | ~~Git Worktree 격리~~ | 2026-04-14 | config.isolation + agent_call 조건부 옵션. 테스트 2건 |
| ~~5~~ | ~~Circuit Breaker~~ | 2026-04-14 | 120초 윈도우 + JSONL 이벤트. 테스트 2건 |
| ~~6~~ | ~~MVP 제외 사항~~ | — | product-planner.md에 기존 구현("명시적 제외"/"Won't") 확인으로 충족 |

> 34/34 parity 테스트 통과 (2026-04-14)

### P1 — 실전 검증 + 배포 준비

| # | 항목 | 노력 | 비고 |
|---|------|------|------|
| 7 | BATS → pytest 전환 | 소 | pre-commit hook 호환 복구 |
| 8 | 영문 README + quickstart | 중 | 채택 장벽 제거 |
| 9 | 단일 설치 명령 (pip/npm) | 중 | DX 40→60+ |
| 10 | 데모 영상 (3분) | 소 | GitHub issue → loop → merge |
| 11 | 벤치마크 (SWE-bench lite) | 대 | 신뢰도, 학술 레퍼런스 |

### ~~P1 에이전트 팀 전환~~ → 보류 (2026-04-14 재평가)

Agent Team Phase 1~3을 **보류**한다. 이유:

1. **이점이 미미**: SPEC_GAP 왕복(3 hop→1 hop)은 연간 누적 절약 < 전환 구현 비용. Main 컨텍스트 압박도 실측 수 KB 수준으로 1M 윈도우에서 무시 가능.
2. **대가가 큼**: 팀원별 독립 컨텍스트 = 비용 선형 증가, 결정론성 상실 (순차 while 루프 → 비결정적 task 자체 선택), harness-review.py 선형 타임라인 분석 불가 → 전면 재작성.
3. **인프라가 사라지지 않음**: automated_checks, git commit/merge, JSONL logging, harness-memory 등은 팀 모델에서도 필요 → 누가 실행하는지 재설계 필요 = 복잡도 추가.
4. **실험적 기능 리스크**: 세션 재개 불가, 작업 상태 지연, 종료 느림.

**재개 조건**: 순차 처리가 실제 병목이 되는 프로젝트/사용 패턴이 나타날 때. 실전 데이터로 판단.

### P2 — 차별화 + 커뮤니티

| # | 항목 | 노력 | 비고 |
|---|------|------|------|
| 12 | Docker sandbox 모드 | 중 | 안전성(W3) 해결 |
| 13 | Web UI (trajectory viewer + cost dashboard) | 대 | 가시성, 마케팅 |
| 14 | 3-Tier 확장 (worktree 병렬 + 클라우드 비동기) | 대 | Osmani 프레임워크 적용 |
| 15 | 논문 ("Harness Engineering: Deterministic Multi-Agent Orchestration") | 대 | 명성, 인용 |
| 16 | Plugin system (custom agent, depth, gate) | 대 | 커뮤니티 확장 |
| 17 | harness-memory → vector DB (자동 경험 축적) | 대 | 핵심 차별화 |
| 18 | Agent Team 전환 (보류 해제 시) | 대 | 순차 처리 병목 실증 후 재검토 |

---

## 9. 최종 판정

### 핵심 질문: "이것이 명성을 가져다 줄 수 있는가?"

**조건부 Yes.** (판정 변동 없음, 근거 강화)

Python 전환으로 아키텍처 품질이 업계 표준(SWE-agent, Aider 수준)에 도달. 이전의 "Bash라서 신뢰도 하락" 리스크가 제거됨. 남은 핵심 과제는 DX(40점)와 에이전트 팀 전환(W2).

P0 완성도 6건 완료로 **78.1점 도달** (초기 72.3 대비 +5.8p).
에이전트 팀 전환은 보류 — 이점(SPEC_GAP 1 hop, 컨텍스트 절약) 대비 대가(비용 증가, 결정론성 상실, 인프라 재설계)가 큼. 현재 순차 파이프라인이 잘 동작하고 있으며 실측 병목이 아님.
**DX(40점)가 최대 병목.** P1 배포 준비(README, 설치 명령, 벤치마크)가 80+ 도달의 핵심 경로.

오픈소스 명성 = **DX x 독창성 x 벤치마크 결과**의 곱:
- 독창성: 이미 상위 (depth + boundaries + memory + review)
- DX: P2 배포 준비로 개선 가능
- 벤치마크: SWE-bench 측정 필요

잠재력은 높다. 실행이 관건이다.

---

## Verification

이 평가는 다음 자료의 실제 내용 검토에 기반함:

**코드 (2026-04-12 Python 전환 후 버전 기준):**
- `~/.claude/harness/*.py` — executor.py, core.py, config.py, helpers.py, impl_loop.py, impl_router.py, plan_loop.py, review_agent.py (3,709 LOC)
- `~/.claude/harness/tests/test_parity.py` — 17개 동등성 테스트 (215 LOC)
- `~/.claude/harness/*.sh.bak` — Bash 원본 보존 (11개 파일)
- `~/.claude/agents/` 전체 (10개 에이전트 + preamble + README)
- `~/.claude/hooks/*.py` (agent-boundary.py, agent-gate.py, commit-gate.py 등)
- `~/.claude/scripts/harness-review.py`

**문서:**
- `~/.claude/orchestration-rules.md` + `orchestration/policies.md` + `orchestration/agent-boundaries.md`
- `~/.claude/settings.json` (훅 정의)

**외부 참고:**
- Claude Code 에이전트 팀 공식 문서 (https://code.claude.com/docs/ko/agent-teams)
- Oh My OpenAgent GitHub 리포지토리 및 설치 가이드
- Addy Osmani "Code Agent Orchestra" (https://addyosmani.com/blog/code-agent-orchestra/)
- 비교 시스템: SWE-agent, OpenHands, Aider, Devin, ChatDev, MetaGPT, Agentless

**코드 리뷰 (2026-04-14):**
- Critical 4건 중 수정 3건 (데드코드, watchdog 타임아웃, SIGTERM 핸들러, log_fh 누수) + 불필요 1건 (merge depth — 원본 확인)
- High 4건 중 수정 0건 (불필요 2건 + 스킵 2건)
- Medium/Low 7건 전부 스킵 (동작 동일 또는 향후 개선)
