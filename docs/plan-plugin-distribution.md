# 하네스 플러그인 배포 계획서

> 작성일: 2026-04-09
> 목적: `~/.claude/` 전역 하네스 → GitHub 배포 가능 플러그인으로 전환

---

## 1. 현재 문제

| 문제 | 영향 |
|---|---|
| 전역 `~/.claude/`에 하드코딩 | 다른 머신/사용자에 설치 불가 |
| 에이전트 공통/프로젝트 분리가 수동 sync (`/agent-downSync`) | 상위↔하위 동기화 어려움, 실수로 공통 지침이 덮어씌워짐 |
| 훅이 `settings.json`에 직접 등록 | 프로젝트마다 수동 설정 필요, 버전 관리 불가 |
| 하네스 스크립트 업데이트 = `~/.claude/harness/*.sh` 직접 수정 | 여러 프로젝트가 같은 파일 참조 → 하나 깨지면 전부 깨짐 |

---

## 2. 목표 상태

```
1. `git clone` + `/plugin install` 한 번으로 설치 완료
2. 플러그인 버전 업데이트 → 모든 프로젝트에 자동 반영
3. 프로젝트별 에이전트 커스텀은 그대로 유지 (2-섹션 구조 보존)
4. 기존 워크플로우 (impl/design/bugfix/plan 루프) 동작 변경 없음
```

---

## 3. Claude Code 플러그인 시스템 요약

### 3.1 플러그인 = 배포 단위

| 구성 요소 | 플러그인 내 위치 | 비고 |
|---|---|---|
| 메타데이터 | `.claude-plugin/plugin.json` | 이름, 버전, 설명 |
| 훅 | `hooks/hooks.json` + `hooks/*.py` | 설치 시 자동 활성화 |
| 에이전트 | `agents/*.md` | 프로젝트 에이전트와 병합 |
| 스킬(명령) | `skills/*/SKILL.md` 또는 `commands/*.md` | `/harness-test`, `/harness-review` 등 |
| 스크립트 | `scripts/*.sh` | `${CLAUDE_PLUGIN_ROOT}/scripts/` 로 참조 |
| 설정 기본값 | `settings.json` (루트) | 플러그인 기본 설정 |

### 3.2 핵심 환경변수

| 변수 | 의미 |
|---|---|
| `${CLAUDE_PLUGIN_ROOT}` | 플러그인 캐시 디렉토리 (읽기 전용) |
| `${CLAUDE_PLUGIN_DATA}` | 플러그인 영구 데이터 디렉토리 (버전 간 공유) |

### 3.3 배포 흐름

```
GitHub repo (marketplace)
  → 유저: /plugin marketplace add owner/repo
  → 유저: /plugin install harness-engineering@owner-repo
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
  → 훅/에이전트/스크립트 즉시 새 버전 사용
```

---

## 4. 대상 플러그인 구조

```
harness-engineering/
├── .claude-plugin/
│   ├── plugin.json                    # 메타데이터 + 버전
│   └── marketplace.json               # 마켓플레이스 매니페스트 (배포용)
│
├── hooks/
│   ├── hooks.json                     # 훅 등록 (settings.json 대체)
│   ├── harness_common.py              # 공유 유틸
│   ├── harness-router.py              # UserPromptSubmit
│   ├── harness-session-start.py       # SessionStart
│   ├── agent-boundary.py              # PreToolUse(Edit/Write/Read)
│   ├── orch-rules-first.py            # PreToolUse(Edit/Write)
│   ├── agent-gate.py                  # PreToolUse(Agent)
│   ├── commit-gate.py                 # PreToolUse(Bash)
│   ├── harness-drift-check.py         # PreToolUse(Bash)
│   ├── post-agent-flags.py            # PostToolUse(Agent)
│   ├── post-commit-cleanup.py         # PostToolUse(Bash)
│   └── harness-settings-watcher.py    # PostToolUse(Edit)
│
├── agents/                            # 공통 지침 (에이전트 공통 섹션)
│   ├── architect.md
│   ├── engineer.md
│   ├── validator.md
│   ├── designer.md
│   ├── design-critic.md
│   ├── test-engineer.md
│   ├── pr-reviewer.md
│   ├── security-reviewer.md
│   ├── qa.md
│   └── product-planner.md
│
├── scripts/
│   ├── harness/
│   │   ├── executor.sh                # 메인 라우터
│   │   ├── impl.sh                    # impl 모드
│   │   ├── impl-process.sh            # engineer 루프
│   │   ├── design.sh                  # design 모드
│   │   ├── bugfix.sh                  # bugfix 모드
│   │   ├── plan.sh                    # plan 모드
│   │   └── utils.sh                   # 공용 유틸
│   ├── setup-project.sh               # 프로젝트 초기화 (harness.config.json 생성)
│   └── harness-review.py              # JSONL 로그 파서
│
├── skills/
│   ├── harness-test/
│   │   └── SKILL.md                   # /harness-test
│   ├── harness-review/
│   │   └── SKILL.md                   # /harness-review
│   ├── harness-status/
│   │   └── SKILL.md                   # /harness-status
│   ├── harness-kill/
│   │   └── SKILL.md                   # /harness-kill
│   └── harness-monitor/
│       └── SKILL.md                   # /harness-monitor
│
├── orchestration/
│   ├── orchestration-rules.md         # 마스터 규칙 (단일 소스)
│   ├── impl.md
│   ├── bugfix.md
│   ├── design.md
│   ├── plan.md
│   └── tech-epic.md
│
├── templates/
│   └── CLAUDE-base.md                 # 프로젝트 CLAUDE.md 템플릿
│
├── tests/
│   ├── test_helper.bash
│   ├── utils.bats
│   ├── flow.bats
│   ├── impl.bats
│   ├── executor.bats
│   ├── gates.bats
│   ├── edge.bats
│   └── hooks.bats
│
├── settings.json                      # 플러그인 기본 설정 (env, permissions)
├── README.md
├── CHANGELOG.md
└── LICENSE
```

---

## 5. 핵심 마이그레이션 포인트

### 5.1 경로 참조: `~/.claude/` → `${CLAUDE_PLUGIN_ROOT}/`

**변경 대상: 모든 하네스 스크립트 + 훅**

| Before (현재) | After (플러그인) |
|---|---|
| `source "${HOME}/.claude/harness/utils.sh"` | `source "${CLAUDE_PLUGIN_ROOT}/scripts/harness/utils.sh"` |
| `python3 ~/.claude/hooks/harness-router.py` | `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/harness-router.py"` |
| `"${HOME}/.claude/harness/impl-process.sh"` | `"${CLAUDE_PLUGIN_ROOT}/scripts/harness/impl-process.sh"` |
| `~/.claude/orchestration-rules.md` | `"${CLAUDE_PLUGIN_ROOT}/orchestration/orchestration-rules.md"` |

**폴백 전략**: `CLAUDE_PLUGIN_ROOT` 미설정 시 (비-플러그인 설치) `${HOME}/.claude/`로 폴백.

```bash
# scripts/harness/utils.sh 상단
HARNESS_ROOT="${CLAUDE_PLUGIN_ROOT:-${HOME}/.claude}"
source "${HARNESS_ROOT}/scripts/harness/utils.sh"  # 또는
source "${HARNESS_ROOT}/harness/utils.sh"           # 폴백
```

### 5.2 hooks.json: settings.json 훅 대체

현재 `~/.claude/settings.json`의 `hooks` 섹션을 `hooks/hooks.json`으로 이전:

```json
{
  "description": "Harness Engineering — 에이전트 오케스트레이션 + 게이트 시스템",
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/harness-router.py\" auto 2>>/tmp/harness-hook-stderr.log; exit 0",
            "timeout": 30
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/harness-session-start.py\" auto 2>/dev/null || true",
            "timeout": 5
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/orch-rules-first.py\" 2>/dev/null || true",
            "timeout": 5
          },
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/agent-boundary.py\" 2>/dev/null || true",
            "timeout": 5
          }
        ]
      },
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/orch-rules-first.py\" 2>/dev/null || true",
            "timeout": 5
          },
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/agent-boundary.py\" 2>/dev/null || true",
            "timeout": 5
          }
        ]
      },
      {
        "matcher": "Read",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/agent-boundary.py\" 2>/dev/null || true",
            "timeout": 5
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/harness-drift-check.py\" 2>/dev/null || true",
            "timeout": 5
          },
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/commit-gate.py\" 2>/dev/null || true",
            "timeout": 5
          }
        ]
      },
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/agent-gate.py\" 2>/dev/null || true",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/harness-settings-watcher.py\" 2>/dev/null || true",
            "timeout": 5
          }
        ]
      },
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/post-agent-flags.py\" 2>/dev/null || true",
            "timeout": 5
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/post-commit-cleanup.py\" 2>/dev/null || true",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

### 5.3 에이전트 2-섹션 구조 보존

**핵심 결정**: 플러그인 agents/는 **공통 지침만** 포함. 프로젝트 특화 지침은 프로젝트 `.claude/agents/`에 유지.

Claude Code는 동일 이름 에이전트가 여러 스코프에 있으면 **머지**한다.
- 플러그인: `agents/engineer.md` → 공통 지침
- 프로젝트: `.claude/agents/engineer.md` → 프로젝트 특화 지침

```
# 플러그인 agents/engineer.md (공통)
## 공통 지침
...

# 프로젝트 .claude/agents/engineer.md (프로젝트)
## 프로젝트 특화 지침
...
```

이렇게 하면 `/agent-downSync`가 불필요해짐 — 플러그인 업데이트 = 공통 지침 자동 업데이트.

### 5.4 harness-router.py executor 경로

현재 executor 경로를 `CLAUDE_PLUGIN_ROOT` 기반으로 변경:

```python
# Before
global_executor = os.path.expanduser("~/.claude/harness/executor.sh")

# After  
plugin_root = os.environ.get('CLAUDE_PLUGIN_ROOT', os.path.expanduser('~/.claude'))
global_executor = os.path.join(plugin_root, 'scripts', 'harness', 'executor.sh')
```

### 5.5 _agent_call의 source 경로

```bash
# Before
source "${HOME}/.claude/harness/utils.sh"

# After
HARNESS_ROOT="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/scripts}"
HARNESS_ROOT="${HARNESS_ROOT:-${HOME}/.claude}"
source "${HARNESS_ROOT}/harness/utils.sh"
```

---

## 6. 프로젝트에서의 사용 흐름

### 6.1 최초 설치 (1회)

```bash
# 1. 마켓플레이스 추가 (개인 또는 조직)
/plugin marketplace add dongchan/harness-engineering

# 2. 플러그인 설치
/plugin install harness-engineering@dongchan-harness-engineering

# 3. 프로젝트 초기화 (harness.config.json 생성)
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup-project.sh"
#   → .claude/harness.config.json 생성
#   → .claude/settings.json (env + allowedTools만)
#   → .claude/agents/ 프로젝트 특화 템플릿 생성
```

### 6.2 일상 사용

기존과 동일 — 변경 없음:
```
유저 프롬프트 → harness-router.py → 분류
  → bash ${CLAUDE_PLUGIN_ROOT}/scripts/harness/executor.sh impl --impl ... --issue ...
```

### 6.3 업데이트

```bash
# 방법 A: 수동
/plugin update harness-engineering

# 방법 B: 자동 (settings.json에 설정)
# Claude Code가 세션 시작 시 자동 체크 + 업데이트

# 방법 C: 프로젝트 .claude/settings.json에 버전 핀 (안전)
{
  "enabledPlugins": {
    "harness-engineering@dongchan-harness-engineering": true
  }
}
```

### 6.4 프로젝트별 커스텀

프로젝트 `.claude/agents/` 파일은 플러그인과 **독립** — 플러그인 업데이트에 영향 없음.

```
플러그인 agents/engineer.md  (v2.0.0 업데이트 → 자동 반영)
     +
프로젝트 .claude/agents/engineer.md  (프로젝트 특화 → 유지)
     =
최종 에이전트 지침 (머지)
```

---

## 7. 마이그레이션 에픽 (작업 순서)

### Epic 1: 레포 구조 생성 + 메타데이터

| # | 태스크 | 산출물 |
|---|---|---|
| 1.1 | GitHub repo 생성 (`harness-engineering`) | 빈 repo |
| 1.2 | `.claude-plugin/plugin.json` 작성 | 메타데이터 |
| 1.3 | `.claude-plugin/marketplace.json` 작성 | 마켓플레이스 매니페스트 |
| 1.4 | 디렉토리 구조 생성 | hooks/, agents/, scripts/, skills/, orchestration/, tests/ |

### Epic 2: 경로 추상화 레이어

| # | 태스크 | 산출물 |
|---|---|---|
| 2.1 | `scripts/harness/utils.sh` 상단에 `HARNESS_ROOT` 폴백 로직 | utils.sh |
| 2.2 | `executor.sh` source 경로 → `HARNESS_ROOT` 기반 | executor.sh |
| 2.3 | `impl-process.sh` source 경로 → `HARNESS_ROOT` 기반 | impl-process.sh |
| 2.4 | 모든 `harness/*.sh` source 경로 변경 | impl.sh, design.sh, bugfix.sh, plan.sh |
| 2.5 | `harness-router.py` executor 경로 → `CLAUDE_PLUGIN_ROOT` 기반 | harness-router.py |
| 2.6 | 모든 `hooks/*.py`의 경로 참조 검사 + 수정 | hooks/*.py |

### Epic 3: hooks.json 전환

| # | 태스크 | 산출물 |
|---|---|---|
| 3.1 | `hooks/hooks.json` 작성 (settings.json hooks 이전) | hooks.json |
| 3.2 | `~/.claude/settings.json`에서 hooks 섹션 제거 | settings.json |
| 3.3 | `harness-settings-watcher.py` 플러그인 환경 대응 | watcher 수정 |

### Epic 4: 에이전트 공통/프로젝트 분리

| # | 태스크 | 산출물 |
|---|---|---|
| 4.1 | 현재 `~/.claude/agents/*.md`에서 공통 지침 추출 → `agents/` | 10개 에이전트 |
| 4.2 | `setup-project.sh` — 프로젝트 `.claude/agents/` 특화 템플릿 생성 | 셋업 스크립트 |
| 4.3 | `/agent-downSync`, `/agent-upSync` 스킬 → 플러그인 update로 대체 | 스킬 폐기 또는 리팩 |

### Epic 5: 스킬 이전

| # | 태스크 | 산출물 |
|---|---|---|
| 5.1 | 기존 skills/commands를 `skills/*/SKILL.md` 형식으로 변환 | harness-test, harness-review 등 |
| 5.2 | SKILL.md에서 `${CLAUDE_PLUGIN_ROOT}` 경로 사용 | SKILL.md 파일들 |

### Epic 6: 테스트 + 검증

| # | 태스크 | 산출물 |
|---|---|---|
| 6.1 | BATS 테스트 `HARNESS_ROOT` 폴백 검증 | tests/*.bats |
| 6.2 | 플러그인 설치 → smoke test (`/harness-test`) | 검증 결과 |
| 6.3 | 프로젝트에서 impl/bugfix/design/plan 루프 E2E 테스트 | 검증 결과 |

### Epic 7: 문서 + 배포

| # | 태스크 | 산출물 |
|---|---|---|
| 7.1 | README.md — 설치/사용법/업데이트 가이드 | README |
| 7.2 | CHANGELOG.md — 버전별 변경 내역 | CHANGELOG |
| 7.3 | v1.0.0 태그 + GitHub Release | 릴리스 |

---

## 8. 리스크 + 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| `CLAUDE_PLUGIN_ROOT` 미설정 환경 | 경로 깨짐 | 폴백 로직 (`${HOME}/.claude/`) 필수 |
| 플러그인 훅 + 전역 훅 충돌 | 중복 실행 | 전역 settings.json hooks 제거 필수. `HARNESS_INTERNAL` 방어선 유지 |
| 에이전트 머지 순서 불확실 | 프로젝트 지침이 덮어씌워질 수 있음 | 프로젝트 agents에 `## 프로젝트 특화 지침` 헤더 필수 + 테스트 |
| 플러그인 캐시 읽기 전용 | 런타임에 orchestration-rules.md 수정 불가 | orch-rules-first.py 대상을 프로젝트 경로로 한정. 플러그인 내 orch-rules는 참조 전용 |
| 하네스 로그/메모리 경로 | 플러그인 캐시에 쓸 수 없음 | `${CLAUDE_PLUGIN_DATA}` 또는 프로젝트 `.claude/` 사용 |

---

## 9. 호환성 전략

### 9.1 단계적 전환 (병행 운영)

```
Phase 1: 플러그인 레포 생성 + 경로 추상화 (HARNESS_ROOT 폴백)
  → 기존 ~/.claude/ 사용자: 변경 없이 동작
  → 플러그인 사용자: CLAUDE_PLUGIN_ROOT로 동작

Phase 2: 새 프로젝트는 플러그인으로 설치
  → 기존 프로젝트는 점진적으로 전환

Phase 3: ~/.claude/ 직접 설치 방식 deprecate
```

### 9.2 역방향 호환

`HARNESS_ROOT` 폴백 로직으로 두 환경 모두 지원:

```bash
# 모든 스크립트 상단
if [[ -n "${CLAUDE_PLUGIN_ROOT}" ]]; then
  HARNESS_ROOT="${CLAUDE_PLUGIN_ROOT}/scripts"
else
  HARNESS_ROOT="${HOME}/.claude"
fi
```

---

## 10. 예상 결과

| 항목 | Before | After |
|---|---|---|
| 설치 | `git clone` + 수동 파일 복사 + settings.json 수정 | `/plugin install` 1회 |
| 업데이트 | 수동 파일 교체 | `/plugin update` 또는 자동 |
| 에이전트 동기화 | `/agent-downSync` 수동 실행 | 플러그인 업데이트로 자동 |
| 프로젝트 초기화 | `bash ~/.claude/setup-harness.sh` + `bash ~/.claude/setup-agents.sh` | `/init-project` (setup-project.sh) |
| 훅 관리 | settings.json 직접 편집 | hooks.json 내장 (건드릴 필요 없음) |
| 버전 관리 | 없음 (항상 latest) | semantic versioning + CHANGELOG |
| 롤백 | 불가 | 이전 버전 캐시 7일 보존, 핀 가능 |
