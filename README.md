# ClaudeCodeAgentPrompt

Claude Code 기반 멀티 에이전트 오케스트레이션 시스템.
Bash 스크립트 + Python 훅으로 11개 에이전트의 워크플로우를 결정론적으로 강제한다.

## 아키텍처

```
orchestration-rules.md (단일 소스)
        │
   ┌────┴────┐
   ▼         ▼
hooks/*.py   harness-*.sh
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
bash .claude/harness-executor.sh impl --impl docs/impl/01-module.md --issue 42 --prefix proj

# 버그픽스 루프
bash .claude/harness-executor.sh bugfix --bug "설명" --issue 42 --prefix proj

# 디자인 루프
bash .claude/harness-executor.sh design --impl docs/impl/01-module.md --issue 42 --prefix proj
```

## 핵심 파일

| 파일 | 역할 |
|------|------|
| `orchestration-rules.md` | 마스터 규칙 (루프, 마커, 정책) |
| `harness-executor.sh` | 5가지 모드 라우터 |
| `harness-loop.sh` | 구현 루프 엔진 (fast/std/deep) |
| `hooks/harness_common.py` | 훅 공유 유틸 (get_prefix, deny) |
| `hooks/*.py` | PreToolUse/PostToolUse 게이트 (11개) |
| `agents/*.md` | 에이전트 정의 파일 |
| `docs/harness-state.md` | 현행 상태 문서 |
| `docs/harness-backlog.md` | 개선 로드맵 |

## 문서

- [orchestration-rules.md](orchestration-rules.md) — 전체 워크플로우 규칙
- [docs/harness-state.md](docs/harness-state.md) — 시스템 현행 상태
- [docs/harness-backlog.md](docs/harness-backlog.md) — 백로그 및 로드맵
