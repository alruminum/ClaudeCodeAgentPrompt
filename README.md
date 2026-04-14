# ClaudeCodeAgentPrompt

Claude Code 기반 멀티 에이전트 오케스트레이션 시스템.
Python 코어 + Bash 래퍼 + Python 훅으로 11개 에이전트의 워크플로우를 결정론적으로 강제한다.

## 아키텍처

```
orchestration-rules.md (단일 소스)
        │
   ┌────┴────┐
   ▼         ▼
hooks/*.py   harness/*.py (코어) + *.sh (래퍼)
(게이트)      (루프 엔진)
   │              │
   ▼              ▼
settings.json  에이전트 11개
```

- **5개 루프**: A(기획), B(디자인), C(구현), D(버그픽스), E(기술 에픽)
- **11개 에이전트**: architect, engineer, validator, qa, designer, design-critic, test-engineer, pr-reviewer, security-reviewer, product-planner, socrates
- **플래그 상태머신**: `/tmp/{prefix}_*` 파일로 에이전트 간 순서 강제

## 설치

```bash
# 프로젝트 루트에서 실행
bash ~/.claude/setup-harness.sh
bash ~/.claude/setup-agents.sh --repo owner/repo
```

## 사용

```bash
# 구현 루프
bash .claude/harness/executor.sh impl --impl docs/impl/01-module.md --issue 42 --prefix proj

# 플랜 루프
bash .claude/harness/executor.sh plan --prefix proj

# 디자인 루프 — ux 스킬이 designer를 직접 호출 (harness 경유 없음)
# /ux 스킬 실행 → TYPE(SCREEN/COMPONENT) + variant 수 선택 → designer Agent 직접 호출
```

## 핵심 파일

### Python 코어 (harness/*.py)

| 파일 | 역할 |
|------|------|
| `executor.py` | 메인 엔트리포인트 — 모드 라우팅, lock, heartbeat, depth 감지 |
| `core.py` | `_agent_call()`, `kill_check()`, `parse_marker()` 등 코어 유틸 |
| `config.py` | 프로젝트 설정 로드 (prefix, 경로) |
| `helpers.py` | impl 루프 공유 헬퍼 (constraints, budget_check, hlog) |
| `impl_loop.py` | impl depth별 루프 엔진 (simple/std/deep) |
| `impl_router.py` | impl 모드 진입 — 재진입 감지, architect, plan validation |
| `plan_loop.py` | plan 모드 전체 흐름 |
| `review_agent.py` | 하네스 완료 후 Haiku 로그 분석 |

### Bash 래퍼 (harness/*.sh)

| 파일 | 역할 |
|------|------|
| `executor.sh` | Python executor.py 래퍼 (Bash 도구 호출 호환) |
| `impl.sh` / `impl_simple.sh` / `impl_std.sh` / `impl_deep.sh` | depth별 Python 래퍼 |
| `utils.sh` | Python core.py 래퍼 |
| `flags.sh` / `markers.sh` | 플래그 상수 + 마커 파싱 유틸 |

### 기타

| 파일 | 역할 |
|------|------|
| `orchestration-rules.md` | 마스터 규칙 (루프, 마커, 정책) |
| `agents/preamble.md` | Universal Preamble — 전 에이전트 공통 지침 |
| `hooks/*.py` | PreToolUse/PostToolUse 게이트 (16개) |
| `agents/*.md` | 에이전트 정의 파일 (11개) |
| `docs/harness-state.md` | 현행 상태 문서 |
| `docs/harness-backlog.md` | 개선 로드맵 |

## 문서

- [orchestration-rules.md](orchestration-rules.md) — 전체 워크플로우 규칙
- [docs/harness-state.md](docs/harness-state.md) — 시스템 현행 상태
- [docs/harness-backlog.md](docs/harness-backlog.md) — 백로그 및 로드맵
