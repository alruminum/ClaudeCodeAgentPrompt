# 하네스 플러그인 배포 계획서

> 작성일: 2026-04-09
> 최신화: **2026-04-21** — oh-my-zsh install.sh 안(`plan-packaging-final.md`) 폐기 확정, Claude Code 플러그인 마켓플레이스 경로로 단일화
> 상태: **ACTIVE (정본)**
> 목적: `~/.claude/` 전역 하네스 → Claude Code 플러그인 마켓플레이스 배포 가능 패키지로 전환

---

## 0. 결정 요약 (2026-04-21)

- **배포 채널**: Claude Code 플러그인 마켓플레이스 단일. oh-my-zsh `install.sh` 안은 `docs/archive/plan-packaging-final.md`로 비활성화
- **근거**: claude-hud (2026-04-21 설치 경험) + OMC 사례로 플러그인 API 성숙도 확인. 2026-04-09에 유일하게 막혔던 "API 미성숙" 우려 해소
- **배포 제외 항목**: `commands/hardcarry.md`, `commands/softcarry.md`, `dongchan-style/` — 유저 개인용. 배포판엔 포함하지 않음
- **다음 액션**: Pre-Plugin 완성도 P0 먼저 (§11 참조)

---

## 1. 현재 문제

| 문제 | 영향 | 상태 |
|---|---|---|
| 전역 `~/.claude/`에 하드코딩 (58곳) | 다른 머신/사용자에 설치 불가 | 미해결 |
| 훅이 `~/.claude/settings.json`에 직접 등록 | 수동 설정 + 버전 관리 불가 | 미해결 |
| 하네스 파일 업데이트 = `~/.claude/harness/*.py` 직접 수정 | 여러 프로젝트가 같은 파일 참조 → 하나 깨지면 전부 깨짐 | 미해결 |
| `harness-state/` 위치 | Phase 3 세션 격리(`2026-04-19`)로 `.sessions/`, `.issues/`, `.global.json` 재구성 완료 → 플러그인 경로 반영 필요 | 부분 해결 |
| 에이전트 공통/프로젝트 분리 | `/agent-downSync` 폐기 → `.claude/agent-config/{name}.md` 패턴 확정 | 해결 (2026-04-XX CLAUDE.md) |

---

## 2. 목표 상태

```
1. `/plugin marketplace add <owner>/<repo>` + `/plugin install` 한 번으로 설치 완료
2. 플러그인 버전 업데이트 → 모든 프로젝트에 자동 반영
3. 프로젝트별 에이전트 커스텀은 `.claude/agent-config/{name}.md`로 유지
4. 기존 워크플로우 (기획/설계/구현/디자인/버그픽스 5루프) 동작 변경 없음
```

---

## 3. Claude Code 플러그인 시스템 요약

### 3.1 플러그인 = 배포 단위

| 구성 요소 | 플러그인 내 위치 | 비고 |
|---|---|---|
| 메타데이터 | `.claude-plugin/plugin.json` | 이름, 버전, 설명 |
| 마켓플레이스 매니페스트 | `.claude-plugin/marketplace.json` | 배포용 |
| 훅 | `hooks/hooks.json` + `hooks/*.py` | 설치 시 자동 활성화 |
| 에이전트 | `agents/*.md` | 프로젝트 `.claude/agent-config/*.md`와 병합 |
| 스킬(명령) | `skills/*/SKILL.md` 또는 `commands/*.md` | `/harness-test`, `/quick` 등 |
| 하네스 코어 | `harness/*.py` | `${CLAUDE_PLUGIN_ROOT}/harness/` |
| 설정 기본값 | `settings.json` (루트) | 플러그인 기본 permissions/env |

### 3.2 핵심 환경변수

| 변수 | 의미 |
|---|---|
| `${CLAUDE_PLUGIN_ROOT}` | 플러그인 캐시 디렉토리 (읽기 전용) |
| `${CLAUDE_PLUGIN_DATA}` | 플러그인 영구 데이터 디렉토리 (버전 간 공유) |

### 3.3 배포 흐름

```
GitHub repo (marketplace)
  → 유저: /plugin marketplace add <owner>/<repo>
  → 유저: /plugin install harness-engineering
  → ~/.claude/plugins/cache/{marketplace}/{plugin}/{version}/ 에 캐시
  → hooks.json의 훅 자동 활성화
  → agents/*.md 자동 인식
```

### 3.4 업데이트 흐름

```
개발자: plugin.json version 범프 + git push
  → 유저: /plugin update (또는 자동 업데이트 설정)
  → 새 버전 캐시 다운로드
  → 구 버전 7일간 보존 (Grace period)
  → 훅/에이전트/하네스 즉시 새 버전 사용
```

---

## 4. 대상 플러그인 구조 (2026-04-21 갱신)

```
harness-engineering/
├── .claude-plugin/
│   ├── plugin.json                    # 메타데이터 + 버전
│   └── marketplace.json               # 마켓플레이스 매니페스트
│
├── hooks/
│   ├── hooks.json                     # 훅 등록 (settings.json 대체)
│   ├── harness_common.py              # 공유 유틸
│   ├── session_state.py               # Phase 3 세션 격리 상태 API (2026-04-19)
│   │
│   ├── harness-router.py              # UserPromptSubmit
│   ├── harness-session-start.py       # SessionStart
│   ├── harness-review-inject.py       # UserPromptSubmit
│   ├── harness-review-stop.py         # Stop
│   ├── harness-review-trigger.py      # PostToolUse(Bash)
│   ├── harness-drift-check.py         # PreToolUse(Bash)
│   ├── harness-settings-watcher.py    # PostToolUse(Edit)
│   │
│   ├── agent-boundary.py              # PreToolUse(Edit/Write/Read)
│   ├── agent-gate.py                  # PreToolUse(Agent)
│   ├── post-agent-flags.py            # PostToolUse(Agent)
│   ├── session-agent-cleanup.py       # UserPromptSubmit
│   │
│   ├── orch-rules-first.py            # PreToolUse(Edit/Write) — 경고형 (2026-04-19)
│   ├── plugin-write-guard.py          # PreToolUse(Edit/Write)
│   ├── commit-gate.py                 # PreToolUse(Bash)
│   ├── post-commit-cleanup.py         # PostToolUse(Bash)
│   ├── issue-gate.py                  # PreToolUse(mcp__github__create_issue/update_issue)
│   │
│   ├── skill-gate.py                  # PreToolUse(Skill) — Phase 4
│   ├── skill-stop-protect.py          # Stop — Phase 4
│   ├── skill_protection.py            # 공유 유틸 — Phase 4
│   ├── post-skill-flags.py            # PostToolUse(Skill) — Phase 4
│   └── ralph-session-stop.py          # Stop — ralph-loop 가드
│
├── agents/                            # 공통 지침 (프로젝트 .claude/agent-config/로 머지)
│   ├── architect.md
│   ├── architect/                     # 하위 모드: light-plan, module-plan, spec-gap, system-design, task-decompose, tech-epic
│   │   ├── light-plan.md
│   │   ├── module-plan.md
│   │   ├── spec-gap.md
│   │   ├── system-design.md
│   │   ├── task-decompose.md
│   │   └── tech-epic.md
│   ├── engineer.md
│   ├── test-engineer.md
│   ├── validator.md
│   ├── validator/plan-validation.md
│   ├── pr-reviewer.md
│   ├── security-reviewer.md
│   ├── qa.md
│   ├── designer.md
│   ├── design-critic.md
│   ├── ux-architect.md                # 2026-04-17 신설 (UX_FLOW/UX_SYNC/UX_REFINE)
│   ├── product-planner.md
│   ├── preamble.md
│   └── README.md
│
├── harness/                           # Python 코어 (2026-04-12 migration)
│   ├── __init__.py
│   ├── config.py                      # harness.config.json 로더
│   ├── core.py                        # 공통 로직 (HUD, Marker, handoff, ...)
│   ├── executor.py                    # 메인 엔트리포인트 + heartbeat
│   ├── helpers.py                     # automated_checks, git 유틸
│   ├── impl_loop.py                   # 구현 루프 (simple/std/deep)
│   ├── impl_router.py                 # depth 자동 분류
│   ├── plan_loop.py                   # 기획-UX-설계 루프
│   ├── providers.py                   # Second Reviewer v3 (Gemini 등)
│   └── review_agent.py                # harness-review JSONL 파서
│
├── commands/                          # Claude Code 스킬 (자연어 진입로)
│   ├── init-project.md                # /init-project — 프로젝트 초기화
│   ├── quick.md                       # /quick — 한 줄 버그픽스 체인
│   ├── qa.md                          # /qa — 버그 트리아지
│   ├── ux.md                          # /ux — 디자인 요청 → designer
│   ├── ux-sync.md                     # /ux-sync — ux-flow.md INCREMENTAL 패치
│   ├── product-plan.md                # /product-plan — 기획-UX 루프
│   ├── ralph.md                       # /ralph — ralph-loop 래퍼
│   ├── deliver.md                     # /deliver — B2B 납품 체크
│   ├── doc-garden.md                  # /doc-garden — 문서-코드 드리프트
│   ├── harness-test.md                # /harness-test — dry-run
│   ├── harness-review.md              # /harness-review — JSONL 분석
│   ├── harness-status.md              # /harness-status — 플래그/훅 상태
│   ├── harness-monitor.md             # /harness-monitor — 실시간 스트리밍
│   └── harness-kill.md                # /harness-kill — 루프 중단
│   # 제외: hardcarry.md, softcarry.md (개인용 — 배포 제외)
│
├── orchestration/                     # 규칙 문서 (카탈로그 + 상세)
│   ├── policies.md                    # 마스터 규칙 (2026-04-19 정제: 418 → 229줄)
│   ├── agent-boundaries.md
│   ├── branch-strategy.md
│   ├── changelog.md
│   ├── issue-convention.md
│   ├── design.md
│   ├── impl.md
│   ├── impl_simple.md
│   ├── impl_std.md
│   ├── impl_deep.md
│   ├── plan.md
│   ├── system-design.md
│   └── tech-epic.md
│
├── templates/
│   └── CLAUDE-base.md                 # 프로젝트 CLAUDE.md 템플릿
│
├── scripts/
│   └── setup-project.sh               # 프로젝트 초기화 (harness.config.json + agent-config 템플릿)
│
├── tests/
│   ├── pytest/                        # Python 코어 + 훅 단위 테스트
│   │   ├── test_session_state.py      # 150+ tests (Phase 3)
│   │   ├── test_ralph_isolation.py
│   │   ├── test_session_start_ux_drift.py
│   │   ├── test_parity.py             # BATS↔pytest 동등성
│   │   └── test_*.py
│   └── bats/                          # 레거시 BATS (migration 중)
│       ├── utils.bats, flow.bats, impl.bats, executor.bats
│       ├── gates.bats, edge.bats, hooks.bats
│       ├── commit-strategy.bats, rule-audit.bats, dryrun.bats
│
├── settings.json                      # 플러그인 기본 permissions/env
├── README.md                          # 설치/사용법 (영문 + 한글)
├── CHANGELOG.md                       # semver
└── LICENSE                            # MIT (예정)
```

### 4.1 2026-04-10 이후 추가된 주요 구성 요소

| 요소 | 도입일 | 플러그인 반영 포인트 |
|---|---|---|
| ux-architect 에이전트 (UX_FLOW/UX_SYNC/UX_REFINE) | 04-17 ~ 04-18 | `agents/ux-architect.md` |
| HUD Statusline (`hud.json` + `/harness-monitor`) | 04-15 | `harness/core.py` HUD 클래스, `commands/harness-monitor.md` |
| Handoff 문서 패턴 | 04-15 | `harness/core.py` generate_handoff/write_handoff |
| POLISH 모드 (ai-slop-cleaner) | 04-15 | `harness/impl_loop.py` |
| Circuit Breaker (120s 윈도우) | 04-15 | `harness/core.py` |
| Second Reviewer v3 (providers.py) | 04-15 | `harness/providers.py` |
| CLARITY_INSUFFICIENT (5차원 모호성 점수) | 04-15 | `commands/product-plan.md` + `agents/product-planner.md` |
| harness-router 7→3카테고리 간소화 | 04-15 | `hooks/harness-router.py` |
| TDD 게이트 (std/deep attempt 0 test-engineer) | 04-17 | `harness/impl_loop.py` |
| 디자인 게이트 3루프 분리 | 04-17 | `orchestration/{plan,system-design,impl,design}.md` |
| Phase 3 세션 격리 (`.sessions/`, `.issues/`, `.global.json`) | 04-19 | `hooks/session_state.py` + `${CLAUDE_PLUGIN_DATA}` 매핑 |
| Phase 4 스킬 컨텍스트 보호 | 04-19 | `hooks/skill-gate.py`, `skill-stop-protect.py`, `skill_protection.py`, `post-skill-flags.py` |
| orch-rules-first 경고형 전환 | 04-19 | `hooks/orch-rules-first.py` |
| ux-flow 드리프트 자동 감지 + INCREMENTAL | 04-20 ~ 04-21 | `hooks/harness-session-start.py` + `commands/ux-sync.md` |
| architect Mode 강제 완화 + `/quick` | 04-20 | `commands/quick.md`, `harness/impl_router.py` |
| PR 워크플로우 (push + PR 자동 생성 + squash) | 04-16 | `harness/impl_loop.py` |
| build_command 게이트 | 04-16 | `harness/{config,helpers,impl_loop}.py` |
| simple depth 회귀 차단 (DOM/텍스트 std 승격) | 04-19 | `harness/helpers.py`, `impl_router.py`, `agents/architect.md` |

> 상세 내역: `orchestration/changelog.md` (2026-04-15 ~ 2026-04-21 40+ 엔트리)

---

## 5. 핵심 마이그레이션 포인트

### 5.1 경로 참조: `~/.claude/` → `${CLAUDE_PLUGIN_ROOT}/`

**변경 대상: 하네스 Python 코어 + 모든 훅**

| Before (현재) | After (플러그인) |
|---|---|
| `os.path.expanduser("~/.claude/harness/executor.py")` | `os.path.join(os.environ['CLAUDE_PLUGIN_ROOT'], 'harness/executor.py')` |
| `Path.home() / ".claude" / "orchestration"` | `Path(os.environ['CLAUDE_PLUGIN_ROOT']) / "orchestration"` |
| `~/.claude/hooks/harness-router.py` (settings.json) | `${CLAUDE_PLUGIN_ROOT}/hooks/harness-router.py` (hooks.json) |

**폴백 전략**: `CLAUDE_PLUGIN_ROOT` 미설정 시 (개발 환경 / 비-플러그인 설치) `${HOME}/.claude/`로 폴백.

```python
# harness/core.py 등 상단
import os
from pathlib import Path

HARNESS_ROOT = Path(os.environ.get('CLAUDE_PLUGIN_ROOT', Path.home() / '.claude'))
```

```bash
# scripts/setup-project.sh 상단
HARNESS_ROOT="${CLAUDE_PLUGIN_ROOT:-${HOME}/.claude}"
```

### 5.2 hooks.json: settings.json 훅 대체

현재 `~/.claude/settings.json`의 23개 훅 엔트리를 `hooks/hooks.json`으로 이전:

```json
{
  "description": "Harness Engineering — 결정론적 에이전트 오케스트레이션",
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/session-agent-cleanup.py\" 2>/dev/null || true",
            "timeout": 5
          }
        ]
      },
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/harness-router.py\" auto 2>>/tmp/harness-hook-stderr.log; exit 0",
            "timeout": 30
          }
        ]
      },
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/harness-review-inject.py\" 2>/dev/null || true",
            "timeout": 10
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/harness-session-start.py\" auto 2>/dev/null || true",
          "timeout": 5
        }]
      }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/skill-stop-protect.py\" 2>/dev/null || true", "timeout": 5 }] },
      { "hooks": [{ "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/ralph-session-stop.py\" 2>/dev/null || true", "timeout": 5 }] },
      { "hooks": [{ "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/harness-review-stop.py\" 2>/dev/null || true", "timeout": 5 }] }
    ],
    "PreToolUse": [
      { "matcher": "Edit",  "hooks": [
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/plugin-write-guard.py\"", "timeout": 5 },
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/orch-rules-first.py\" 2>/dev/null || true", "timeout": 5 },
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/agent-boundary.py\" 2>/dev/null || true", "timeout": 5 }
      ]},
      { "matcher": "Write", "hooks": [/* 동일 3개 */] },
      { "matcher": "Read",  "hooks": [{ "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/agent-boundary.py\" 2>/dev/null || true", "timeout": 5 }] },
      { "matcher": "Bash",  "hooks": [
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/harness-drift-check.py\" 2>/dev/null || true", "timeout": 5 },
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/commit-gate.py\" 2>/dev/null || true", "timeout": 5 }
      ]},
      { "matcher": "Agent", "hooks": [{ "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/agent-gate.py\" 2>/dev/null || true", "timeout": 5 }] },
      { "matcher": "Skill", "hooks": [{ "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/skill-gate.py\" 2>/dev/null || true", "timeout": 5 }] },
      { "matcher": "mcp__github__create_issue", "hooks": [{ "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/issue-gate.py\" 2>/dev/null || true", "timeout": 5 }] },
      { "matcher": "mcp__github__update_issue", "hooks": [{ "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/issue-gate.py\" 2>/dev/null || true", "timeout": 5 }] }
    ],
    "PostToolUse": [
      { "matcher": "Edit",  "hooks": [{ "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/harness-settings-watcher.py\" 2>/dev/null || true", "timeout": 5 }] },
      { "matcher": "Agent", "hooks": [{ "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/post-agent-flags.py\" 2>/dev/null || true", "timeout": 5 }] },
      { "matcher": "Skill", "hooks": [{ "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/post-skill-flags.py\" 2>/dev/null || true", "timeout": 5 }] },
      { "matcher": "Bash",  "hooks": [
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/post-commit-cleanup.py\" 2>/dev/null || true", "timeout": 5 },
          { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/harness-review-trigger.py\" 2>/dev/null || true", "timeout": 5 }
      ]}
    ]
  }
}
```

> **주의**: `Stop` 훅의 첫 엔트리 `afplay Glass.aiff`는 macOS 전용 개인 설정이라 플러그인에서 제외. 유저가 원하면 자기 `settings.json`에 수동 추가.

### 5.3 에이전트 2-섹션 구조 (이미 확정된 패턴)

2026-04-XX CLAUDE.md에서 결정된 대로:
- **플러그인**: `agents/*.md` — 공통 지침 (모든 프로젝트 공유)
- **프로젝트**: `.claude/agent-config/{name}.md` — 프로젝트 특화 지침

각 에이전트는 시작 시 `.claude/agent-config/{name}.md`가 있으면 읽고, 없으면 기본 동작.
`/agent-downSync`, `/agent-upSync`는 이미 폐기 상태.

### 5.4 하네스 경로 추상화 구체안

```python
# harness/core.py 최상단
import os
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get('CLAUDE_PLUGIN_ROOT', Path.home() / '.claude'))
PLUGIN_DATA = Path(os.environ.get('CLAUDE_PLUGIN_DATA', Path.home() / '.claude' / 'plugin-data'))

# 참조 경로
ORCHESTRATION_DIR = PLUGIN_ROOT / 'orchestration'
AGENTS_DIR = PLUGIN_ROOT / 'agents'
```

```python
# hooks/harness-router.py
plugin_root = Path(os.environ.get('CLAUDE_PLUGIN_ROOT', Path.home() / '.claude'))
executor_py = plugin_root / 'harness' / 'executor.py'
```

### 5.5 상태 저장소: `harness-state/` → 프로젝트 `.claude/` (변경 없음)

**중요 판단 (2026-04-21 추가)**: Phase 3 세션 격리로 이미 세션/이슈별 상태는 **프로젝트 `.claude/harness-state/`** 에 쓴다. 이건 유지:

```
프로젝트/.claude/harness-state/
  ├── .sessions/{session_id}/live.json   # 현재 활성 에이전트
  ├── .issues/{prefix}_{issue}/lock       # 이슈 lock (세션 간 공유)
  ├── .global.json                        # 프로젝트 전역 상태
  └── .session-id                          # 현재 세션 포인터
```

`${CLAUDE_PLUGIN_DATA}`는 **크로스 프로젝트 공유 상태**에만 사용:
- 글로벌 harness-memory (실패 패턴 자동 프로모션 결과)
- 유저별 하네스 설정 오버라이드

### 5.6 배포 제외 경로

**배포판에 포함하지 않음** (개인용):
- `commands/hardcarry.md`
- `commands/softcarry.md`
- `dongchan-style/**`
- `hooks/agent-boundary.py.bak-hardcarry`, `hooks/agent-gate.py.bak-hardcarry`
- 모든 `.bak`, `.bak-*` 파일

---

## 6. 프로젝트에서의 사용 흐름

### 6.1 최초 설치 (1회)

```bash
# 1. 마켓플레이스 추가
/plugin marketplace add <owner>/harness-engineering

# 2. 플러그인 설치
/plugin install harness-engineering

# 3. Claude Code 재시작 (hooks.json 로드)

# 4. 프로젝트 초기화
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup-project.sh"
#   → .claude/harness.config.json 생성
#   → .claude/settings.json (env + allowedTools만)
#   → .claude/agent-config/ 빈 템플릿 생성
#   → .gitignore에 harness-state/ 추가
```

### 6.2 일상 사용 (변경 없음)

```
유저 프롬프트 → harness-router.py → 분류 (BUG/UI/IMPL)
  → python3 ${CLAUDE_PLUGIN_ROOT}/harness/executor.py impl --issue N --prefix proj
```

### 6.3 업데이트

```bash
/plugin update harness-engineering   # 수동
# 또는 자동 업데이트 설정
```

### 6.4 프로젝트별 커스텀

`.claude/agent-config/{name}.md` 는 플러그인과 **독립** — 업데이트 영향 없음.

---

## 7. 마이그레이션 에픽 (2026-04-21 갱신)

### Epic 0: Pre-Plugin 완성도 (P0 — §11 참조)

플러그인 구조 변환 **전에** 완료해야 하는 항목. 자세한 건 §11.

### Epic 1: 레포 + 메타데이터

| # | 태스크 | 산출물 |
|---|---|---|
| 1.1 | GitHub repo 생성 (`harness-engineering`) + MIT LICENSE | repo |
| 1.2 | `.claude-plugin/plugin.json` (버전, 설명, 의존성) | plugin.json |
| 1.3 | `.claude-plugin/marketplace.json` | marketplace.json |
| 1.4 | 디렉토리 구조 생성 | hooks/, agents/, harness/, commands/, orchestration/, tests/, scripts/, templates/ |

### Epic 2: 경로 추상화 레이어

| # | 태스크 | 산출물 |
|---|---|---|
| 2.1 | `harness/core.py` `PLUGIN_ROOT`/`PLUGIN_DATA` 상수 추가 | core.py |
| 2.2 | 현역 `harness/*.py` 11개 파일의 `~/.claude/` 참조 치환 (현재 ~58곳 중 `.bak` 제외하면 ~15곳) | harness/ |
| 2.3 | `hooks/*.py` 23개의 경로 참조 검사 + 치환 | hooks/ |
| 2.4 | `hooks/harness_common.py` PLUGIN_ROOT 기반으로 재작성 | harness_common.py |
| 2.5 | `scripts/setup-project.sh` PLUGIN_ROOT 기반 | setup-project.sh |

### Epic 3: hooks.json 전환

| # | 태스크 | 산출물 |
|---|---|---|
| 3.1 | `hooks/hooks.json` 작성 (settings.json hooks 23 엔트리 이전) | hooks.json |
| 3.2 | `~/.claude/settings.json`에서 hooks 섹션 제거 (개발 환경은 플러그인 inactive 상태로 복귀) | settings.json |
| 3.3 | `harness-settings-watcher.py` 플러그인 환경 감지 로직 | watcher |
| 3.4 | macOS 전용 `afplay` Stop 훅은 README에 옵션으로 안내 | README |

### Epic 4: 에이전트 공통/프로젝트 분리 검증

| # | 태스크 | 산출물 |
|---|---|---|
| 4.1 | 현재 `~/.claude/agents/*.md` 13개의 공통/특화 섹션 검토 | 감사 리포트 |
| 4.2 | `scripts/setup-project.sh` — `.claude/agent-config/` 템플릿 생성 | 셋업 스크립트 |
| 4.3 | `hardcarry`, `softcarry`, `dongchan-style` 배포 제외 확인 | 체크리스트 |

### Epic 5: 스킬/명령 이전

| # | 태스크 | 산출물 |
|---|---|---|
| 5.1 | `commands/*.md` 14개를 플러그인 형식으로 변환 (`hardcarry`/`softcarry` 제외) | commands/ |
| 5.2 | 각 command 내부 경로 참조 `${CLAUDE_PLUGIN_ROOT}` 치환 | commands/*.md |
| 5.3 | `init-project.md` — 새 프로젝트 셋업 안내 | init-project.md |

### Epic 6: 테스트 + 검증

| # | 태스크 | 산출물 |
|---|---|---|
| 6.1 | pytest 전체 (`test_session_state.py` 150+ 테스트 등)가 `PLUGIN_ROOT` 폴백 하에 통과 확인 | 테스트 결과 |
| 6.2 | BATS 테스트 (현재 12개 파일) `HARNESS_ROOT` 폴백 검증 후 pytest로 완전 migration | tests/ |
| 6.3 | 별도 머신/컨테이너에서 clean install → smoke test (`/harness-test`) | 검증 결과 |
| 6.4 | 샘플 프로젝트에서 기획/설계/구현/버그픽스/디자인 5 루프 E2E | 검증 결과 |

### Epic 7: 문서 + 배포

| # | 태스크 | 산출물 |
|---|---|---|
| 7.1 | `README.md` 전면 재작성 (설치/사용/업데이트/차별점 — 영문 + 한글) | README |
| 7.2 | `CHANGELOG.md` semver 초기화 (v1.0.0 이전 히스토리는 한 줄 요약) | CHANGELOG |
| 7.3 | 데모 영상/GIF 3분 | 영상 |
| 7.4 | v1.0.0 태그 + GitHub Release | 릴리스 |
| 7.5 | 마켓플레이스 공개 PR | PR |

---

## 8. 리스크 + 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| `CLAUDE_PLUGIN_ROOT` 미설정 환경 | 경로 깨짐 | 폴백 로직 (`${HOME}/.claude/`) 전 모듈 필수 |
| 플러그인 훅 + 전역 훅 충돌 | 중복 실행 | 플러그인 설치 시 `~/.claude/settings.json` hooks 섹션 제거 안내. setup-project.sh가 체크 |
| 에이전트 머지 순서 불확실 | 프로젝트 지침이 덮어씌워질 수 있음 | `.claude/agent-config/` 패턴 이미 확정. 플러그인 agents/는 "## 공통 지침" 섹션만 포함 |
| 플러그인 캐시 읽기 전용 | 런타임에 orchestration-rules 수정 불가 | `orch-rules-first.py` 대상을 프로젝트 경로로 한정. 플러그인 내 rules는 참조 전용 |
| 하네스 세션 상태 경로 | 플러그인 캐시에 쓸 수 없음 | Phase 3 이미 프로젝트 `.claude/harness-state/`로 재구성 — 영향 없음 |
| 플러그인 API 하위호환성 | Claude Code 버전 업데이트로 hooks.json 스키마 변경 가능 | `plugin.json` `claudeCodeVersion` 필드로 최소 버전 pin + CI 매트릭스 |
| macOS 전용 훅 (`afplay`) | 다른 OS 실패 | 제외하고 README에 옵션 스니펫 제공 |
| `.bak-hardcarry` 같은 개인 env 토글 | 배포판에 포함되면 안 됨 | 빌드 스크립트에서 `.bak*` 제외, `grep hardcarry` CI |

---

## 9. 호환성 전략

### 9.1 단계적 전환 (병행 운영)

```
Phase 1: 플러그인 레포 생성 + 경로 추상화 (HARNESS_ROOT 폴백)
  → 기존 ~/.claude/ 사용자: 변경 없이 동작
  → 플러그인 사용자: CLAUDE_PLUGIN_ROOT로 동작

Phase 2: 플러그인 v1.0.0 배포 → 새 프로젝트는 플러그인 경로
  → 기존 프로젝트는 settings.json hooks 제거 후 전환

Phase 3: ~/.claude/ 직접 설치 방식 deprecate
```

### 9.2 역방향 호환 (개발 시나리오)

로컬 개발 중엔 플러그인 설치 없이도 테스트 가능해야 함:

```python
# harness/core.py
PLUGIN_ROOT = Path(os.environ.get('CLAUDE_PLUGIN_ROOT', Path.home() / '.claude'))
```

```bash
# scripts/*.sh
HARNESS_ROOT="${CLAUDE_PLUGIN_ROOT:-${HOME}/.claude}"
```

---

## 10. 예상 결과

| 항목 | Before | After |
|---|---|---|
| 설치 | `git clone` + 수동 복사 + settings.json 편집 | `/plugin install` 1회 + 재시작 |
| 업데이트 | 수동 파일 교체 | `/plugin update` 또는 자동 |
| 에이전트 동기화 | `.claude/agent-config/` 수동 편집 (유지) | 동일 |
| 프로젝트 초기화 | `bash ~/.claude/setup-harness.sh` | `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup-project.sh"` 또는 `/init-project` |
| 훅 관리 | settings.json 직접 편집 | hooks.json 내장 (건드릴 필요 없음) |
| 버전 관리 | 없음 (always latest) | semver + CHANGELOG |
| 롤백 | 불가 | 이전 버전 캐시 7일 보존, `enabledPlugins` 에 버전 핀 가능 |
| 발견 가능성 | 없음 | 마켓플레이스 리스팅 |

---

## 11. Pre-Plugin 완성도 체크리스트 (2026-04-21 신규)

플러그인 구조 변환 **전에** 완료해야 (`Explore` 에이전트 종합 + OMC 비교 + 감사 리포트):

### P0 — 배포 전 반드시

| # | 항목 | 공수 | 비고 |
|---|---|---|---|
| P0-1 | `.bak` 파일 일괄 삭제 (`harness/*.sh.bak` 11개, `hooks/*.bak-hardcarry` 2개) | S | 경로 감사 정확도 상승 |
| P0-2 | LICENSE 추가 (MIT 권장) | S | 배포 전제 |
| P0-3 | `README.md` 전면 재작성 (영문 + 한글, 현재 드리프트 심함) | L | agent 수 불일치(11→12), 폐기된 socrates 언급 등 |
| P0-4 | 버전 체계 + `CHANGELOG.md` v1.0.0 초기화 | S | semver |
| P0-5 | 세 plan 문서 정리 완료 (본 문서만 정본) | S | ✅ 완료 (2026-04-21) |
| P0-6 | `setup-agents.sh` 완전 제거 (이미 DEPRECATED 상태) | S | cleanup |

### P1 — 배포 후 빠르게

| # | 항목 | 공수 | 상태 | 출처 |
|---|---|---|---|---|
| P1-1 | 데모 영상 3분 (issue → 루프 → merge) | M | ⬜ | audit-report P1-10 |
| P1-2 | SWE-bench lite 벤치마크 | L | ⬜ | audit-report P1-11 |
| P1-3 | BATS → pytest 잔여 migration 완료 | S | ⬜ | audit-report P1-7 (현재 parity 34/34) |
| P1-4 | 에이전트 프롬프트 영문화 | L | ⬜ | audit W4 |
| P1-5 | 토큰/비용 가시성 (HUD + JSONL `cost_usd`) | M | ✅ 완료 (이미 구현됨을 2026-04-21 재확인: HUD `total_cost/budget` 표시, JSONL `cost_usd` 필드, `harness-review` per-agent breakdown) | OMC 비교 재평가 2026-04-20 |
| P1-6 | 외부 알림 (file/osascript/webhook) | S | ✅ 완료 (2026-04-21 — `harness/notify.py` + `write_run_end` 통합. `HARNESS_NOTIFY` env var opt-in. 트리거는 `HARNESS_DONE` + `*_ESCALATE/CRASH/CONFLICT`만) | OMC 비교 재평가 2026-04-20 |
| P1-7 | 성공 attempt → skill 초안 자동 추출 | M | 🟡 부분 (REFLECTION 추출/기록은 `helpers.py` 구현됨 — `harness-memory.md` Success Patterns 섹션에 자동 기록. skill 초안 생성 파이프라인은 미구현) | OMC `/learner` 비대칭 해소 |
| P1-8 | 재시도 generic 분기 이전 실패 로그 인라인 (`_extract_generic_fail_hint`) | S | ✅ 완료 (2026-04-21 — `impl_loop.py` simple·std/deep else 분기에 prev attempt 최신 `.log` 마지막 2KB 자동 주입. pr_fail 패턴과 동일) | harness-backlog S11 · audit W2 |
| P1-8b | Smart Context hot-file 휴리스틱 (`build_smart_context` git diff HEAD~3 보강) | S | ⬜ 보류 (체감 후 재검토 — P1-8 완료로 재시도 맥락은 해결, hot-file은 별개 이슈) | harness-backlog S11 |
| P1-9 | Impl 파일 충돌 감지 (S9) | S | ⏸ 보류 (worktree 격리로 silent overwrite 위험은 이미 차단. 에픽 3개+ 프로젝트 체감 시 재검토) | harness-backlog S9 |

### P2 — 선택

| # | 항목 | 공수 |
|---|---|---|
| P2-1 | Docker/VM 샌드박스 격리 | L |
| P2-2 | cross-run 트렌드 대시보드 (`harness-trend` 스킬) | M |
| P2-3 | 이름 결정 (`harness-engineering`? `claude-harness`? 등) | S |

---

## 12. 다음 액션

1. **P0-1 ~ P0-6 먼저 완료** (총 ~1일)
2. Epic 1 착수 (repo 생성, plugin.json, marketplace.json)
3. Epic 2 경로 추상화 (architect 에이전트에게 위임 권장 — 58곳 변경)
4. Epic 3 hooks.json 전환
5. Epic 4~7 테스트·배포

> 상세 진행은 별도 backlog 항목으로 분리 후 하네스 루프로 진행. 이 문서는 **설계 정본**이며, 실제 실행은 architect/engineer 에이전트에게 위임.

---

## 부록 A — 폐기된 대안

| 대안 | 왜 폐기됐나 |
|---|---|
| oh-my-zsh 패턴 (`bash <(curl ...) install.sh`) | 유저의 `~/.claude/settings.json` 직접 편집 필요 → 충돌 위험 상시. claude-hud가 플러그인 마켓 경로의 DX 우위 입증 (2026-04-21). `docs/archive/plan-packaging-final.md` |
| 다중 배포 채널 (npm + install.sh + 플러그인) | 1인 유지보수 과부하 | `docs/archive/distribution-plan.md` |

## 부록 B — 참고 자료

- `docs/comparison-omc-2026-04-15.md` — OMC 비교분석
- `docs/harness-audit-report-2026-04-11.md` — 코어 감사 보고서
- `docs/harness-backlog.md` — 기술부채 백로그
- `harness-improvement-plan.md` — Phase A~D 개선 계획
- `orchestration/changelog.md` — 2026-04-10 이후 40+ 엔트리
- `CLAUDE.md` — 유저 글로벌 규칙
