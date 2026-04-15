# oh-my-claudecode (OMC) vs 우리 시스템 — 상세 비교 분석

> 분석일: 2026-04-15
> 대상: https://github.com/Yeachan-Heo/oh-my-claudecode (28.8K stars, 2.7K forks, 2,685 commits)
> 결론: **가장 직접적인 경쟁자. 같은 Claude Code 위에서 같은 문제를 다른 철학으로 해결.**

---

## 1. 한눈에 비교

| | 우리 시스템 | oh-my-claudecode (OMC) |
|---|-----------|----------------------|
| Stars | 0 (미배포) | **28,800** |
| 에이전트 수 | 11 (역할 특화) | **19** (범용 분류) |
| 스킬 수 | 12 | **37** |
| 실행 모드 | depth 기반 (simple/std/deep) | **5가지** (team/autopilot/ralph/ultrawork/pipeline) |
| 팀 모드 | 보류 (순차 파이프라인 유지) | **네이티브 팀 구현** (5단계 파이프라인) |
| 모델 라우팅 | Claude only | **Haiku/Sonnet/Opus 자동 배정** |
| 외부 AI | 없음 | **CCG: Codex + Gemini 합성** |
| 배포 방식 | 글로벌 설치 (~/.claude/) | **npm 패키지** (`npm i -g oh-my-claude-sisyphus`) |
| 언어 | Python 3.9+ stdlib | TypeScript/Node.js |
| 라이선스 | 미정 | MIT |
| 물리적 경계 강제 | **hooks로 차단** | 프롬프트 기반 (disallowedTools) |
| 결정론성 | **완전 결정론적** (while 루프) | 비결정적 (팀 자체 조율) |
| 학습 메커니즘 | **harness-memory + auto-promotion** | skill learning (수동) |
| 낭비 감지 | **harness-review 8패턴** | session analytics (수동) |
| 디자인 도구 | **Pencil MCP + design-critic** | 텍스트 기반 designer |

---

## 2. OMC가 확실히 앞서는 것

### 2.1 커뮤니티 & DX — 압도적 격차

28.8K stars vs 0. npm 한 줄 설치 vs 수동 setup. `/setup` 한 번이면 끝 vs README 없음.
이건 시스템 품질이 아니라 **포장과 유통**의 차이이지만, 오픈소스에서는 이게 전부일 수 있음.

### 2.2 에이전트 팀 네이티브 구현 — 실전 검증

OMC는 Claude Code 에이전트 팀을 **이미 프로덕션에서 사용 중**:

```
/team 3:executor "task"
→ team-plan → team-prd → team-exec → team-verify → team-fix
```

5단계 파이프라인:
1. **team-plan**: explore + planner로 태스크 분해
2. **team-prd**: analyst로 요구사항 명확화
3. **team-exec**: N명 worker 병렬 실행
4. **team-verify**: verifier + security-reviewer 게이팅
5. **team-fix**: 실패 항목 반복 수정 → team-exec로 루프

handoff 문서(`.omc/handoffs/`)로 단계 간 컨텍스트 전달. 우리가 "보류"한 것을 이미 구현하고 28.8K 유저가 사용 중.

### 2.3 실행 모드 다양성 — 5가지 vs 1가지

| 모드 | 설명 | 우리 대응 |
|------|------|----------|
| team | 팀 파이프라인 | 없음 (보류) |
| autopilot | 완전 자율 실행 | 없음 |
| ralph | 검증 루프 반복 | ralph-loop 플러그인 (유사) |
| ultrawork | 최대 병렬 | 없음 |
| pipeline | 순차 처리 | depth 기반 순차 (유사) |

우리는 사실상 pipeline 모드 하나만 있음. OMC는 태스크 성격에 따라 모드를 선택할 수 있음.

### 2.4 스마트 모델 라우팅 — 토큰 비용 최적화

```
단순 작업 (린트, 포맷) → Haiku (저비용)
표준 작업 (구현, 테스트) → Sonnet (중비용)
복잡 작업 (아키텍처, 디버깅) → Opus (고비용)
```

30-50% 토큰 절약을 주장. 우리는 모든 에이전트에 동일 모델(sonnet 기본, 일부 opus) 사용. 에이전트별 모델 지정은 agents/*.md의 `model:` 필드로 가능하지만, 태스크 복잡도에 따른 **동적 라우팅**은 없음.

### 2.5 Deep Interview — 수학적 모호성 점수

Socratic 질문으로 요구사항 수집. 모호성 점수를 3차원(Goal 40%, Constraints 30%, Success Criteria 30%)으로 계산. 20% 미만으로 내려가야 실행 허가.

우리의 product-planner도 역질문을 하지만, **수학적 모호성 측정**은 없음.

### 2.6 CCG — 크로스 모델 합성

Codex(아키텍처) + Gemini(UX) → Claude가 합성. 우리는 단일 모델 전용.
다만 OMO 분석에서 확인한 것처럼, 이건 다중 구독($400+/월)이 필요한 기능.

### 2.7 AI Slop Cleaner — 후처리

AI 생성 코드의 "슬롭"(불필요한 주석, 과도한 추상화, 의미 없는 변수명) 자동 제거.
우리에는 없는 기능. pr-reviewer가 일부 역할을 하지만 자동 수정까지는 안 함.

### 2.8 알림 시스템

Telegram/Discord/Slack 콜백 지원. 장시간 작업 완료 시 알림. 우리는 없음.

---

## 3. 우리가 확실히 앞서는 것

### 3.1 물리적 에이전트 경계 강제 — OMC에 없음

우리:
```python
# agent-boundary.py (PreToolUse hook)
engineer → src/** 만 Write 가능, docs/** 차단
architect → docs/** 만 Write 가능, src/** 차단
validator/pr-reviewer → 완전 ReadOnly (모든 Write 차단)
```

OMC:
```yaml
# agents/architect.md
disallowedTools: Write, Edit  # 프롬프트 수준 제한
```

OMC는 `disallowedTools`를 에이전트 정의에 명시하지만, 이건 **프롬프트 수준**이라 LLM이 무시할 수 있음. 우리는 **hooks가 도구 호출 자체를 차단** → 무시 불가.

이것이 우리 시스템의 가장 독보적인 차별점. OMC의 19개 에이전트 중 누군가가 경계를 넘어도 막을 물리적 장치가 없음.

### 3.2 결정론적 파이프라인 — 재현 가능성

우리: Python while 루프가 정확히 어떤 에이전트를 어떤 순서로 호출. JSONL로 선형 타임라인 기록. 같은 입력 → 같은 실행 경로.

OMC: 팀원이 task를 "자체 선택". 비결정적 실행. 같은 입력에 다른 경로 가능. 디버깅 시 인과 관계 추적 어려움.

### 3.3 Depth 기반 비용 최적화 — OMC에 없는 개념

```
simple: 2 에이전트 (텍스트/스타일) → ~$0.5
std:    5 에이전트 (로직/API)    → ~$3-8
deep:   6 에이전트 (보안)        → ~$5-15
```

OMC는 모델 라우팅으로 비용을 줄이지만, **에이전트 수 자체를 태스크에 맞게 조절**하는 개념은 없음. 단순 텍스트 수정에도 전체 파이프라인(plan→prd→exec→verify→fix)이 돌아감.

### 3.4 SPEC_GAP 동결 패턴 — OMC에 없음

스펙 문제(architect 책임)와 구현 문제(engineer 책임)를 분리:
- attempt(max 3) + spec_gap(max 2) = 최대 5라운드
- SPEC_GAP는 attempt를 소비하지 않음

OMC의 team-fix는 단순 재시도. 실패 원인이 스펙인지 구현인지 구분하지 않음.

### 3.5 Harness Memory + Auto-Promotion — 반자동 학습

동일 패턴 3회 실패 → 자동 감지 → CONSTRAINTS 주입 → 영구 적용.
OMC의 `skillify`/`learner`는 수동 패턴 추출. 실패 기반 자동 학습은 없음.

### 3.6 Harness Review — 자동 낭비 감지 8패턴

WASTE_INFRA_READ, WASTE_SUB_AGENT, CONTEXT_BLOAT, RETRY_SAME_FAIL 등 8가지 패턴을 JSONL에서 자동 감지.
OMC는 session analytics가 있지만 **자동화된 낭비 패턴 감지**는 없음.

### 3.7 디자인 워크플로우 — Pencil MCP 통합

designer 에이전트 + design-critic + 2x2 매트릭스(SCREEN/COMPONENT x ONE_WAY/THREE_WAY).
OMC의 designer는 텍스트 기반 코드 생성. 시각적 디자인 도구 통합 없음.

### 3.8 QA 트리아지 — 5가지 분류 자동 라우팅

```
FUNCTIONAL_BUG → executor.sh impl --issue
CLEANUP → depth=simple 강제
DESIGN_ISSUE → ux 스킬 → designer
KNOWN_ISSUE → 유저 보고
SCOPE_ESCALATE → product-planner
```

OMC는 범용 debugger/tracer 에이전트가 있지만, **분류 → 자동 라우팅** 체계는 없음.

### 3.9 Circuit Breaker + REFLECTION + 도메인별 토큰 예산

최근 추가된 P0 기능들. OMC에는 모두 없음:
- 시간 윈도우 기반 반복 실패 조기 감지
- 성공 패턴 자동 추출 + 학습
- 도메인별(frontend/backend) 차등 토큰 예산

---

## 4. 아키텍처 철학 비교

| | 우리 | OMC |
|---|-----|-----|
| **오케스트레이션** | 하네스가 통제 (Python 루프) | Claude Code 팀이 자율 조율 |
| **에이전트 관계** | 순차 파이프라인 (hub-and-spoke) | 팀 협업 (peer-to-peer) |
| **품질 보증** | 물리적 경계 + 결정론적 게이팅 | 프롬프트 규칙 + 검증 에이전트 |
| **비용 전략** | depth로 에이전트 수 통제 | 모델 라우팅으로 단가 통제 |
| **학습** | 자동 (실패 3회 → promotion) | 수동 (skillify로 패턴 저장) |
| **확장** | Python 코드 수정 | 스킬 .md 파일 추가 |

**핵심 차이: "통제 vs 자율"**

우리: "AI를 엄격하게 통제하되, 각 단계를 정확히 실행"
OMC: "AI에게 자율성을 주되, 다양한 도구를 제공"

---

## 5. OMC의 팀 모드 상세 분석

### 5단계 파이프라인

```
team-plan (explore + planner)
    ↓ handoff 문서
team-prd (analyst — 필요시만)
    ↓ handoff 문서
team-exec (N명 worker 병렬)
    ↓ 결과
team-verify (verifier + security-reviewer)
    ↓ PASS/FAIL
team-fix (executor/debugger) ←→ team-exec (루프)
```

### 우리 depth=std와 비교

```
우리: engineer → test-engineer → validator → pr-reviewer → merge
OMC: plan → prd → exec(N) → verify → fix(루프)
```

**OMC 장점**: 기획(plan+prd)이 실행(exec) 전에 별도 단계. 우리는 architect가 impl 파일을 미리 작성하는 방식이라 "기획 → 실행" 분리가 덜 명확.

**우리 장점**: depth=simple이면 기획 단계 자체를 스킵. OMC는 모든 팀 실행이 5단계를 거침 → 단순 작업에 오버헤드.

### handoff 문서 패턴

OMC는 `.omc/handoffs/`에 단계 간 인수인계 문서를 작성. 각 문서에 "결정 사항 + 컨텍스트 + 다음 단계 지시"가 포함.

우리의 `explore_instruction()` + `build_smart_context()`가 유사하지만, **파일로 명시적 저장하는 패턴**은 없음. 이것은 도입 가치가 있음 — 특히 SPEC_GAP 발생 시 architect↔engineer 간 컨텍스트 전달에.

### worker 사전 배정

OMC: "Pre-assign task owners before spawning agents to prevent claiming races"
리더가 task를 생성할 때 owner를 미리 지정 → 팀원 간 경쟁 방지.

우리는 순차 호출이라 이 문제 자체가 없음. 하지만 팀 전환 시에는 이 패턴이 필요.

---

## 6. OMC 에이전트 19개 vs 우리 11개

| OMC 에이전트 | 우리 대응 | 차이 |
|-------------|---------|------|
| architect | architect | OMC는 ReadOnly. 우리도 docs/**만 Write. 유사 |
| executor | engineer | 거의 동일. OMC는 "3회 실패 → architect 에스컬레이션" |
| verifier | validator | 유사. 둘 다 PASS/FAIL 판정 |
| planner | architect (MODULE_PLAN) | OMC는 별도 에이전트. 우리는 architect의 모드 |
| analyst | product-planner | 유사. 요구사항 수집 |
| test-engineer | test-engineer | 동일 |
| code-reviewer | pr-reviewer | 동일 |
| security-reviewer | security-reviewer | 동일 |
| designer | designer | OMC는 텍스트. 우리는 Pencil MCP |
| debugger | qa | OMC는 디버깅 특화. 우리 qa는 분류+라우팅 |
| critic | design-critic | OMC는 범용. 우리는 디자인 심사 특화 |
| explore | (Explore 서브에이전트) | OMC는 독립 에이전트. 우리는 내장 에이전트 타입 |
| writer | — | **우리에 없음**. 문서 작성 전문 |
| scientist | — | **우리에 없음**. 데이터 분석/실험 |
| tracer | — | **우리에 없음**. 런타임 추적 |
| git-master | — | **우리에 없음**. Git 전문 (rebase, cherry-pick 등) |
| code-simplifier | — | **우리에 없음**. 코드 간소화 전문 |
| document-specialist | — | **우리에 없음**. 문서화 전문 |
| — | socrates | OMC에 없음. 의도 분류 |

OMC가 8개 더 많지만, 우리에 없는 6개(writer, scientist, tracer, git-master, code-simplifier, document-specialist) 중 실제로 필요한 것:
- **code-simplifier**: pr-reviewer의 CHANGES_REQUESTED로 일부 커버되지만 전문 에이전트 가치 있음
- **git-master**: 복잡한 git 작업(rebase, conflict resolution) 시 유용
- 나머지(writer, scientist, tracer, document-specialist): 우리 도메인에서 필요성 낮음

---

## 7. OMC 스킬 37개 vs 우리 12개

OMC 스킬 중 우리에 없는 주목할 만한 것:

| OMC 스킬 | 기능 | 도입 가치 |
|---------|------|----------|
| **deep-interview** | 수학적 모호성 점수로 요구사항 수집 | **높음** — product-planner 강화 가능 |
| **ccg** | Codex+Gemini 합성 | 낮음 — 다중 구독 필요 |
| **ai-slop-cleaner** | AI 생성 코드 후처리 | **중간** — pr-reviewer에 통합 가능 |
| **skillify** | 작업 패턴을 스킬로 추출 | 중간 — harness-memory와 유사하지만 다른 접근 |
| **self-improve** | 자기 개선 루프 | 낮음 — 실효성 불명확 |
| **visual-verdict** | 시각적 검증 | 낮음 — Pencil MCP로 커버 |
| **wiki** | 프로젝트 위키 생성 | 낮음 |
| **remember** | 영구 메모리 | 우리 harness-memory와 유사 |
| **hud** | 실시간 상태 표시 | **중간** — 가시성 개선 |
| **omc-doctor** | 환경 진단 | 중간 — harness-test와 유사 |
| **configure-notifications** | 알림 설정 | 중간 — 장시간 작업 시 유용 |

---

## 8. 채택 가치가 있는 OMC 아이디어

### 높음

**1. Deep Interview 방식의 모호성 정량화**
현재 product-planner의 역질문이 정성적. 모호성 점수(Goal/Constraints/Success Criteria)를 도입하면 "언제 기획을 끝내고 구현을 시작할지"의 판단이 명확해짐.

**2. Handoff 문서 패턴**
파이프라인 단계 간 `.claude/handoffs/`에 인수인계 문서 저장. 현재 explore_instruction()이 파일 경로만 전달하는데, 명시적 handoff 문서는 SPEC_GAP 컨텍스트 전달에 효과적.

### 중간

**3. AI Slop Cleaner**
HARNESS_DONE 후 자동으로 AI 생성 패턴(과도한 주석, 불필요한 추상화) 제거. pr-reviewer의 역할과 겹치지만, 자동 수정까지 해주는 점이 다름.

**4. HUD Statusline**
하네스 실행 중 실시간 상태 표시. 현재는 `[HARNESS] engineer (attempt 2/3)` 수준. 토큰 사용량, 경과 시간, 진행률 등 추가 가능.

**5. 모델 라우팅 (depth 내부)**
depth=std 내에서도 validator는 Haiku면 충분, engineer는 Sonnet 필요 같은 분화. 현재 agents/*.md의 `model:` 필드로 가능하지만 활용 안 됨.

### 낮음 (채택 불필요)

- CCG 크로스 모델 합성 — 다중 구독 비용
- 5가지 실행 모드 — depth 전략이 더 단순하고 효과적
- 팀 모드 전면 도입 — 이미 보류 판정

---

## 9. 최종 판정

### OMC가 이기는 영역
- **DX & 채택**: 압도적 (28.8K stars, npm 설치, /setup)
- **실행 모드 다양성**: 5가지 vs 1가지
- **팀 모드 실전 경험**: 프로덕션 검증됨
- **스킬 생태계**: 37개 vs 12개
- **모델 라우팅**: 비용 30-50% 절약 주장

### 우리가 이기는 영역
- **물리적 경계 강제**: hooks vs 프롬프트 (우리가 유일)
- **결정론적 파이프라인**: 재현 가능, 디버깅 용이
- **depth 기반 비용 최적화**: 에이전트 수 자체를 조절
- **SPEC_GAP 동결**: 실패 원인 분리
- **자동 학습**: 실패 3회 → auto-promotion (수동 skillify 대비)
- **자동 낭비 감지**: harness-review 8패턴
- **디자인 도구**: Pencil MCP 통합
- **QA 트리아지**: 5가지 분류 자동 라우팅

### 포지셔닝

```
OMC: "다양한 도구와 자율성으로 AI가 알아서 하게"
우리: "엄격한 통제와 결정론으로 AI를 정확하게 쓰게"
```

OMC는 **"범용 도구상자"**, 우리는 **"정밀 공정 라인"**.

OMC가 더 넓은 시장(바이브 코딩 입문~중급)을 커버하지만,
우리가 더 깊은 시장(프로덕션 품질 요구, 팀 규율, 감사 추적)을 커버.

**28.8K stars를 따라가려 하지 말고, "왜 OMC로는 부족한가"를 설명할 수 있는 포지셔닝이 핵심.**
→ "AI가 자율적으로 잘해요" 대신 "AI가 정확히 내 규칙대로 해요"

---

## 10. 팀 전환 보류 판정 재확인

OMC가 팀 모드를 성공적으로 구현한 것을 보면 "기술적으로 불가능"은 아님.
하지만 OMC의 팀 모드는 **비결정적 실행을 수용하는 철학** 위에 구축됨.

우리 시스템의 핵심 가치가 **결정론적 통제**인 이상, 팀 전환은 정체성 변경에 해당.
"OMC가 했으니까 우리도" 가 아니라 "우리 강점을 유지하면서 이점만 선택적 도입"이 맞음.

보류 판정 유지. 단, OMC에서 배울 아이디어(handoff 문서, 모호성 점수, slop cleaner)는 순차 파이프라인 위에서 도입 가능.
