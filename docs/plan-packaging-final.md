# 하네스 프레임워크 패키징 최종 계획서

> 작성일: 2026-04-09
> 상태: DRAFT — 유저 검토 대기
> 선행 문서: [distribution-plan.md](distribution-plan.md) (oh-my-zsh 패턴), [plan-plugin-distribution.md](plan-plugin-distribution.md) (플러그인 패턴)

---

## 0. 전제: 별도 프로젝트에서 작업

**현재 `~/.claude/`를 직접 수정하지 않는다.** 별도 프로젝트 폴더를 만들어 패키징하고, 완성 후 설치 테스트를 거쳐 전환한다.

```
~/projects/claude-orchestration/     ← 새 프로젝트 (여기서 작업)
~/.claude/                           ← 현재 운영 환경 (건드리지 않음)
```

---

## 1. 두 계획서 비교

| 항목 | Plan A (플러그인) | Plan B (oh-my-zsh) | 최종 선택 |
|---|---|---|---|
| **설치** | `/plugin install` | `curl \| bash install.sh` | **B** — 플러그인 시스템은 hooks.json + agents만 지원, harness 스크립트 배포에 제약 |
| **경로 참조** | `${CLAUDE_PLUGIN_ROOT}` | `~/.claude/` 직접 | **하이브리드** — `HARNESS_ROOT` 변수로 추상화 + 폴백 |
| **훅 관리** | `hooks/hooks.json` 자동 활성화 | `settings.json` smart merge | **B** — 현재 훅이 `settings.json`에 깊게 통합됨. hooks.json 전환은 리스크 큼 |
| **에이전트 동기화** | 플러그인 자동 머지 | `framework/` → `~/.claude/` 복사 | **B** — 자동 머지 동작이 검증 안 됨 (공통+특화 섹션 충돌 리스크) |
| **버전 관리** | 플러그인 시스템 내장 | `VERSION` 파일 + git tag | **B** — 더 명시적이고 제어 가능 |
| **업데이트** | `/plugin update` | `claude-orch update` (git pull + 복사) | **B** — 하네스 스크립트까지 포함 |
| **롤백** | 7일 캐시 보존 | git tag checkout | **B** — 무제한 롤백 |
| **프로젝트별 커스텀** | `.claude/agents/` 프로젝트 특화 | `custom/` 디렉토리 | **B** — 프로젝트 특화는 기존 방식 유지 |
| **쓰기 가능 영역** | `${CLAUDE_PLUGIN_DATA}`만 | `~/.claude/` 전체 | **B** — harness-memory, 로그 등 쓰기 필요 |

### 결론: **oh-my-zsh 패턴 (Plan B) 기반 + Plan A의 경로 추상화 차용**

**이유**:
1. 플러그인 시스템은 hooks/agents만 지원 — harness 스크립트(7개 .sh), orchestration-rules, 커맨드(12개) 배포에 부적합
2. 플러그인 캐시는 **읽기 전용** — harness-memory.md, JSONL 로그 등 쓰기 불가
3. `hooks.json` 자동 활성화는 매력적이나, 현재 settings.json의 env/permissions/enabledPlugins와 깊게 결합돼 있어 분리 리스크 큼
4. oh-my-zsh 패턴은 10년+ 검증됨, 구현 간단, 완전한 제어 가능

---

## 2. 대상 레포 구조

```
claude-orchestration/                    # ← GitHub repo (새 프로젝트)
│
├── install.sh                           # 한 줄 설치 스크립트
├── update.sh                            # 업데이트 스크립트
├── uninstall.sh                         # 제거 스크립트
├── VERSION                              # semver (예: 1.0.0)
├── CHANGELOG.md
├── README.md
├── LICENSE
│
├── framework/                           # ─── 프레임워크 관리 (업데이트 시 덮어쓰기) ───
│   │
│   ├── agents/                          # 에이전트 공통 지침 (10개)
│   │   ├── architect.md
│   │   ├── engineer.md
│   │   ├── validator.md
│   │   ├── designer.md
│   │   ├── design-critic.md
│   │   ├── test-engineer.md
│   │   ├── pr-reviewer.md
│   │   ├── security-reviewer.md
│   │   ├── qa.md
│   │   └── product-planner.md
│   │
│   ├── hooks/                           # 훅 (11개)
│   │   ├── harness_common.py
│   │   ├── harness-router.py
│   │   ├── harness-session-start.py
│   │   ├── agent-boundary.py
│   │   ├── orch-rules-first.py
│   │   ├── agent-gate.py
│   │   ├── commit-gate.py
│   │   ├── harness-drift-check.py
│   │   ├── post-agent-flags.py
│   │   ├── post-commit-cleanup.py
│   │   └── harness-settings-watcher.py
│   │
│   ├── harness/                         # 하네스 엔진 (7개 + providers)
│   │   ├── executor.sh
│   │   ├── impl.sh
│   │   ├── impl-process.sh
│   │   ├── design.sh
│   │   ├── bugfix.sh
│   │   ├── plan.sh
│   │   ├── utils.sh
│   │   └── providers/                   # 플랫폼 추상화 provider 스크립트
│   │       ├── issues/
│   │       │   ├── github.sh
│   │       │   ├── gitlab.sh
│   │       │   └── none.sh
│   │       ├── test_runner/
│   │       │   ├── vitest.sh
│   │       │   ├── jest.sh
│   │       │   ├── pytest.sh
│   │       │   └── go.sh
│   │       └── notification/
│   │           ├── afplay.sh
│   │           ├── paplay.sh
│   │           └── none.sh
│   │
│   ├── orchestration/                   # 루프 정의 (6개)
│   │   ├── impl.md
│   │   ├── bugfix.md
│   │   ├── design.md
│   │   ├── plan.md
│   │   └── tech-epic.md
│   │
│   ├── commands/                        # 스킬/커맨드 (기존 .claude/commands/)
│   │   ├── init-project.md
│   │   ├── harness-review.md
│   │   ├── harness-test.md
│   │   ├── harness-status.md
│   │   ├── harness-kill.md
│   │   ├── harness-monitor.md
│   │   ├── deliver.md
│   │   ├── doc-garden.md
│   │   ├── design.md
│   │   └── ...
│   │
│   ├── scripts/                         # 유틸 스크립트
│   │   ├── harness-review.py
│   │   └── classify-miss-report.py
│   │
│   ├── templates/                       # 프로젝트 템플릿
│   │   └── CLAUDE-base.md
│   │
│   ├── orchestration-rules.md           # 마스터 룰북
│   └── CLAUDE.md                        # 전역 Claude 지침
│
├── project-init/                        # 프로젝트 초기화
│   ├── setup-harness.sh
│   └── setup-agents.sh
│
├── settings/                            # settings.json 관리
│   ├── settings.template.json           # 전역 settings 기본값
│   └── merge-settings.py               # smart merge 스크립트
│
├── migrations/                          # 버전 마이그레이션
│   └── (향후 추가)
│
└── tests/                               # 테스트
    ├── test_helper.bash
    ├── utils.bats
    ├── flow.bats
    ├── impl.bats
    ├── executor.bats
    ├── gates.bats
    ├── edge.bats
    ├── hooks.bats
    └── install.bats                     # 설치/업데이트 테스트
```

---

## 3. 파일 매핑: 현재 → 패키지

### 3.1 framework/ 으로 이동 (업데이트 시 덮어쓰기 대상)

| 현재 경로 (`~/.claude/`) | 패키지 경로 | 비고 |
|---|---|---|
| `agents/*.md` | `framework/agents/` | 공통 지침만 추출 |
| `hooks/*.py` | `framework/hooks/` | 그대로 이동 |
| `harness/*.sh` | `framework/harness/` | 그대로 이동 |
| `orchestration/*.md` | `framework/orchestration/` | 그대로 이동 |
| `commands/*.md` | `framework/commands/` | 스킬 파일 이동 |
| `scripts/*.py` | `framework/scripts/` | 유틸 스크립트 |
| `templates/` | `framework/templates/` | 그대로 이동 |
| `orchestration-rules.md` | `framework/orchestration-rules.md` | 마스터 룰 |
| `CLAUDE.md` | `framework/CLAUDE.md` | 전역 지침 |

### 3.2 project-init/ 으로 이동

| 현재 경로 | 패키지 경로 |
|---|---|
| `setup-harness.sh` | `project-init/setup-harness.sh` |
| `setup-agents.sh` | `project-init/setup-agents.sh` |

### 3.3 유저 소유 (패키지에 포함 안 함)

| 경로 | 이유 |
|---|---|
| `memory/` | 자동 메모리 (유저 고유) |
| `projects/` | 프로젝트별 메모리 |
| `harness-logs/` | 실행 로그 |
| `harness-memory.md` | 실패 패턴 |
| `project-agents/` | 프로젝트별 에이전트 오버라이드 |
| `docs/` | 하네스 문서 (이 계획서 등) |
| `plugins/` | Claude Code 플러그인 캐시 |
| `settings.json` | smart merge 대상 |

---

## 4. 경로 추상화: `HARNESS_ROOT`

### 4.1 원칙

모든 스크립트에서 `~/.claude/`를 하드코딩하지 않고 `HARNESS_ROOT` 변수 사용:

```bash
# framework/harness/utils.sh 상단 (자동 감지)
if [[ -n "${CLAUDE_ORCH_ROOT}" ]]; then
  # 환경변수로 명시적 지정 (개발/테스트용)
  HARNESS_ROOT="${CLAUDE_ORCH_ROOT}"
elif [[ -f "${HOME}/.claude/.framework-version" ]]; then
  # 프레임워크 설치됨 → 표준 경로
  HARNESS_ROOT="${HOME}/.claude"
else
  # 폴백: 스크립트 자신의 위치에서 역추적
  HARNESS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fi
```

### 4.2 hooks에서의 경로

```python
# framework/hooks/harness_common.py
import os

def get_harness_root():
    """프레임워크 루트 경로 반환."""
    env = os.environ.get('CLAUDE_ORCH_ROOT')
    if env:
        return env
    # 표준 설치 경로
    default = os.path.expanduser('~/.claude')
    if os.path.exists(os.path.join(default, '.framework-version')):
        return default
    # 폴백: 훅 파일 위치에서 역추적
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```

### 4.3 harness-router.py executor 경로

```python
# Before
global_executor = os.path.expanduser("~/.claude/harness/executor.sh")

# After
harness_root = get_harness_root()
global_executor = os.path.join(harness_root, 'harness', 'executor.sh')
```

---

## 4B. Provider 추상화: 플랫폼 독립성

### 4B.1 문제

현재 시스템은 아래 외부 서비스/도구에 하드코딩되어 있어, 다른 환경의 유저가 그대로 쓸 수 없다.

| 카테고리 | 하드코딩 대상 | 영향 파일 | 심각도 |
|---|---|---|---|
| **이슈 트래커** | `mcp__github__*` (18개 도구), `gh issue/api`, `Closes #NNN` | settings.json, agents/architect.md, agents/qa.md, setup-agents.sh, CLAUDE-base.md, harness/bugfix.sh, harness/utils.sh | CRITICAL |
| **테스트 러너** | `npx vitest run` (ground truth) | harness/impl-process.sh, harness/bugfix.sh, agents/test-engineer.md, orchestration/impl.md | HIGH |
| **UI 프레임워크** | React 코드 생성, TypeScript Props 가정 | agents/designer.md, agents/engineer.md, agents/architect/*.md | HIGH |
| **패키지 매니저** | `npm install/run/build`, `npx` | CLAUDE-base.md, setup-agents.sh, commands/deliver.md | MEDIUM |
| **브라우저 자동화** | `mcp__playwright__*` (22개 도구) | settings.json, agents/design-critic.md | MEDIUM |
| **디자인 도구** | Figma MCP, Stitch MCP | agents/designer.md, agents/engineer.md | MEDIUM |
| **OS 알림** | `afplay` (macOS 전용) | settings.json | LOW |

### 4B.2 추상화 전략: `providers` 설정 + 룩업 테이블

**참고 패턴** (실제 프로젝트 검증):

| 패턴 | 복잡도 | 실사용처 | 우리 적용 대상 |
|---|---|---|---|
| **정적 룩업 테이블** | 최저 | `ni` (패키지매니저 감지) | 패키지 매니저, 테스트 러너, OS 알림 |
| **설정 타입 셀렉터** | 낮음 | Turborepo `turbo.json` | 빌드/테스트 명령어 |
| **코어 인터페이스 + capability** | 중간 | git-town (3메서드 코어 + 선택 capability) | 이슈 트래커, Git 호스팅 |

**핵심 원칙**: 무거운 플러그인 아키텍처 없이 **설정 파일 + 룩업 테이블**로 80% 커버.

### 4B.3 `harness.config.json` 확장

```json
// .claude/harness.config.json (프로젝트별)
{
  "prefix": "mb",
  "providers": {
    "issues": "github",
    "test_runner": "vitest",
    "package_manager": "pnpm",
    "ui_framework": "react",
    "browser": "playwright",
    "notification": "afplay"
  },
  "commands": {
    "test": "npx vitest run",
    "build": "pnpm run build",
    "typecheck": "pnpm run typecheck",
    "dev": "pnpm run dev",
    "install": "pnpm install"
  }
}
```

- `providers` — 어떤 플랫폼을 쓸지 선언. **항상 구체적인 값으로 저장** (auto 없음).
- `commands` — 실제 실행 명령어 오버라이드. 하네스 스크립트는 이 명령어를 직접 사용.

### 4B.3a Provider 감지 흐름: 자동 감지 → 유저 확인

`setup-harness.sh` 실행 시 **자동 감지 후 유저에게 확인**을 받는다. 자동 감지 결과를 무조건 적용하지 않는다.

```
$ bash ~/.claude/setup-harness.sh

📌 프로젝트 prefix: mb_
🔍 Provider 자동 감지 중...

  이슈 트래커:    github      (git remote: github.com/user/repo)
  테스트 러너:    vitest      (vitest.config.ts 발견)
  패키지 매니저:  pnpm        (pnpm-lock.yaml 발견)
  UI 프레임워크:  react       (package.json → react 의존성)
  브라우저:       playwright  (기본값)
  알림:           afplay      (macOS 감지)

  이대로 진행? [Y/n/편집]
```

- **`Y` (기본)**: 감지 결과를 `harness.config.json`에 저장
- **`n`**: 중단
- **`편집`**: 개별 항목 변경 후 저장

#### 자동 감지 가능 수준 (provider별)

| Provider | 감지 방법 | 신뢰도 | 감지 불가 시 |
|---|---|---|---|
| **패키지 매니저** | lockfile (`yarn.lock`, `pnpm-lock.yaml`, `bun.lockb`) | 확실 | `npm` 폴백 |
| **테스트 러너** | config 파일 (`vitest.config.ts`, `jest.config.js`, `pytest.ini`, `go.mod`) | 높음 | 유저에게 질문 |
| **알림** | OS 감지 (`uname` → macOS/Linux/WSL) | 확실 | `none` 폴백 |
| **이슈 트래커** | git remote URL에서 `github.com` / `gitlab.com` 추출 | 부분 | 유저에게 질문 (self-hosted, Jira, Linear 등) |
| **UI 프레임워크** | `package.json` dependencies (`react`, `vue`, `svelte`) | 부분 | 유저에게 질문 (비JS 프로젝트) |
| **브라우저** | 감지 불가 | — | `playwright` 기본값, 유저 변경 가능 |

#### 감지 로직 (setup-harness.sh 내부)

```bash
detect_providers() {
  # 이슈 트래커: git remote URL에서 추론
  local remote_url
  remote_url=$(git remote get-url origin 2>/dev/null || echo "")
  case "$remote_url" in
    *github.com*)  DETECTED_ISSUES="github" ;;
    *gitlab.com*)  DETECTED_ISSUES="gitlab" ;;
    *)             DETECTED_ISSUES="???" ;;   # 유저에게 질문
  esac

  # 테스트 러너: config 파일 존재 여부
  if   [[ -f "vitest.config.ts" || -f "vitest.config.js" ]]; then DETECTED_TEST="vitest"
  elif [[ -f "jest.config.js"   || -f "jest.config.ts"   ]]; then DETECTED_TEST="jest"
  elif [[ -f "pytest.ini"       || -f "pyproject.toml"   ]]; then DETECTED_TEST="pytest"
  elif [[ -f "go.mod"           ]];                          then DETECTED_TEST="go"
  else DETECTED_TEST="???"
  fi

  # 패키지 매니저: lockfile
  if   [[ -f "bun.lockb"       ]]; then DETECTED_PM="bun"
  elif [[ -f "pnpm-lock.yaml"  ]]; then DETECTED_PM="pnpm"
  elif [[ -f "yarn.lock"       ]]; then DETECTED_PM="yarn"
  elif [[ -f "package-lock.json" ]]; then DETECTED_PM="npm"
  else DETECTED_PM="???"
  fi

  # UI 프레임워크: package.json dependencies
  if [[ -f "package.json" ]]; then
    if   grep -q '"react"'  package.json; then DETECTED_UI="react"
    elif grep -q '"vue"'    package.json; then DETECTED_UI="vue"
    elif grep -q '"svelte"' package.json; then DETECTED_UI="svelte"
    else DETECTED_UI="none"
    fi
  else
    DETECTED_UI="none"
  fi

  # 알림: OS
  case "$(uname -s)" in
    Darwin) DETECTED_NOTIFY="afplay" ;;
    Linux)  command -v paplay &>/dev/null && DETECTED_NOTIFY="paplay" || DETECTED_NOTIFY="none" ;;
    *)      DETECTED_NOTIFY="none" ;;
  esac

  # 브라우저: 기본값
  DETECTED_BROWSER="playwright"
}
```

`???`로 감지된 항목은 유저에게 선택지를 제시:
```
  이슈 트래커:    ???  ← 자동 감지 불가
    선택: [1] github  [2] gitlab  [3] jira  [4] none
    > 
```

#### 감지 후 commands 자동 생성

provider가 확정되면 `commands`도 자동으로 채워진다:

```bash
generate_commands() {
  local pm="$1" test="$2"
  case "$pm" in
    npm)  CMD_INSTALL="npm install"; CMD_RUN="npm run" ;;
    pnpm) CMD_INSTALL="pnpm install"; CMD_RUN="pnpm run" ;;
    yarn) CMD_INSTALL="yarn install"; CMD_RUN="yarn run" ;;
    bun)  CMD_INSTALL="bun install"; CMD_RUN="bun run" ;;
  esac
  case "$test" in
    vitest) CMD_TEST="npx vitest run" ;;
    jest)   CMD_TEST="npx jest" ;;
    pytest) CMD_TEST="pytest" ;;
    go)     CMD_TEST="go test ./..." ;;
  esac
}
```

유저가 `commands`를 직접 수정하면 자동 생성보다 **우선** 적용.

### 4B.4 Provider별 상세 설계

#### A. 이슈 트래커 (`providers.issues`)

가장 복잡한 영역. git-town의 **코어 + capability** 패턴 적용:

```
코어 인터페이스 (필수):
  - create_issue(title, body, labels)    → 이슈 생성
  - get_issue(number)                    → 이슈 조회
  - list_issues(filters)                 → 이슈 목록
  - close_issue(number)                  → 이슈 닫기

선택 capability:
  - milestones: create_milestone(), assign_to_milestone()
  - labels: create_label(), assign_label()
  - pull_requests: create_pr(), merge_pr()
```

**구현 방식**: `harness/providers/issues/` 디렉토리에 provider별 셸 스크립트:

```
framework/harness/providers/
├── issues/
│   ├── github.sh      # gh CLI 기반
│   ├── gitlab.sh      # glab CLI 기반
│   ├── jira.sh        # jira CLI 기반
│   └── none.sh        # 이슈 트래커 없음 (로컬 markdown 관리)
├── test_runner/
│   ├── vitest.sh
│   ├── jest.sh
│   ├── pytest.sh
│   └── go.sh
└── notification/
    ├── afplay.sh      # macOS
    ├── paplay.sh      # Linux (PulseAudio)
    ├── powershell.sh  # Windows (WSL)
    └── none.sh        # 무음
```

**예시 — `issues/github.sh`**:
```bash
issue_create() { gh issue create --title "$1" --body "$2" --label "$3"; }
issue_get()    { gh issue view "$1" --json body -q .body; }
issue_list()   { gh issue list --limit "$1" --label "$2" --state "$3" --json number,title; }
issue_close()  { gh issue close "$1"; }
```

**예시 — `issues/gitlab.sh`**:
```bash
issue_create() { glab issue create --title "$1" --description "$2" --label "$3"; }
issue_get()    { glab issue view "$1" --output json | jq -r .description; }
issue_list()   { glab issue list --per-page "$1" --label "$2" --state "$3"; }
issue_close()  { glab issue close "$1"; }
```

**에이전트 도구 매핑**: `setup-agents.sh`가 provider에 따라 MCP 도구 목록을 동적 생성:

| provider | 에이전트 tools |
|---|---|
| `github` | `mcp__github__create_issue`, `mcp__github__list_issues`, ... |
| `gitlab` | `mcp__gitlab__create_issue`, `mcp__gitlab__list_issues`, ... |
| `none` | *(이슈 도구 제외)* |

#### B. 테스트 러너 (`providers.test_runner`)

**Turborepo 패턴** — 명령어 문자열로 추상화. 하네스는 exit code만 본다:

```bash
# harness/impl-process.sh — 현재
npx vitest run > "/tmp/${PREFIX}_test_out.txt" 2>&1

# 변경 후
TEST_CMD=$(get_command "test")  # harness.config.json의 commands.test 읽기
eval "$TEST_CMD" > "/tmp/${PREFIX}_test_out.txt" 2>&1
```

룩업 테이블 (자동 감지용):
```bash
detect_test_runner() {
  [[ -f "vitest.config.ts" ]] && echo "npx vitest run" && return
  [[ -f "jest.config.js" ]]   && echo "npx jest" && return
  [[ -f "pytest.ini" ]]       && echo "pytest" && return
  [[ -f "go.mod" ]]           && echo "go test ./..." && return
  echo "npx vitest run"  # 폴백
}
```

#### C. 패키지 매니저 (`providers.package_manager`)

**`ni` 패턴** — lockfile 기반 자동 감지:

```bash
detect_package_manager() {
  [[ -f "bun.lockb" ]]        && echo "bun" && return
  [[ -f "pnpm-lock.yaml" ]]   && echo "pnpm" && return
  [[ -f "yarn.lock" ]]        && echo "yarn" && return
  echo "npm"  # 폴백
}

# 명령어 룩업
PM_COMMANDS=(
  [npm_install]="npm install"   [npm_run]="npm run"   [npm_add]="npm install"
  [pnpm_install]="pnpm install" [pnpm_run]="pnpm run" [pnpm_add]="pnpm add"
  [yarn_install]="yarn install" [yarn_run]="yarn run"  [yarn_add]="yarn add"
  [bun_install]="bun install"   [bun_run]="bun run"   [bun_add]="bun add"
)
```

#### D. UI 프레임워크 (`providers.ui_framework`)

에이전트 지침에만 영향. 코드 생성 방향을 바꿈:

| provider | designer 출력 | engineer 가정 |
|---|---|---|
| `react` | ASCII + React 컴포넌트 | TypeScript, Props 타입 |
| `vue` | ASCII + Vue SFC | TypeScript, Props 정의 |
| `svelte` | ASCII + Svelte 컴포넌트 | TypeScript |
| `html` | ASCII + vanilla HTML/CSS/JS | JavaScript |
| `none` | ASCII만 (코드 생성 안 함) | 백엔드 전용 프로젝트 |

구현: `setup-agents.sh`가 provider에 따라 에이전트 `## 프로젝트 특화 지침`에 프레임워크별 가이드를 삽입.

#### E. 브라우저 자동화 (`providers.browser`)

| provider | 도구 | design-critic에서 사용 |
|---|---|---|
| `playwright` | `mcp__playwright__*` | 스크린샷 + DOM 검증 |
| `none` | *(도구 제외)* | ASCII 리뷰만 수행 |

#### F. OS 알림 (`providers.notification`)

```bash
notify() {
  case "$(get_provider notification)" in
    afplay)     afplay /System/Library/Sounds/Glass.aiff ;;
    paplay)     paplay /usr/share/sounds/freedesktop/stereo/complete.oga ;;
    powershell) powershell.exe -c '[console]::beep(800,200)' ;;
    none)       : ;;  # 무음
    auto)
      command -v afplay &>/dev/null && afplay /System/Library/Sounds/Glass.aiff && return
      command -v paplay &>/dev/null && paplay /usr/share/sounds/freedesktop/stereo/complete.oga && return
      ;;
  esac
}
```

### 4B.5 에이전트 도구 동적 생성

`setup-agents.sh`가 `harness.config.json`의 providers를 읽어 에이전트 파일의 `tools:` 행을 동적 구성:

```bash
# setup-agents.sh 내부
ISSUES_PROVIDER=$(read_provider "issues")
case "$ISSUES_PROVIDER" in
  github) ISSUE_TOOLS="mcp__github__create_issue, mcp__github__list_issues, mcp__github__get_issue, mcp__github__update_issue" ;;
  gitlab) ISSUE_TOOLS="mcp__gitlab__create_issue, mcp__gitlab__list_issues, mcp__gitlab__get_issue, mcp__gitlab__update_issue" ;;
  none)   ISSUE_TOOLS="" ;;
esac

# architect.md tools 행 생성
ARCHITECT_TOOLS="Read, Glob, Grep, Write, Edit, Bash${ISSUE_TOOLS:+, $ISSUE_TOOLS}"
```

### 4B.6 마이그레이션 영향

기존 프로젝트는 `harness.config.json`에 `providers` 키가 없으면 **전부 기본값** 적용:

```json
// 기본값 (providers 키 없을 때)
{
  "issues": "github",
  "test_runner": "vitest",
  "package_manager": "auto",
  "ui_framework": "react",
  "browser": "playwright",
  "notification": "auto"
}
```

→ 기존 프로젝트는 동작 변경 없음 (하위 호환).

---

## 5. install.sh 상세

```bash
#!/bin/bash
# claude-orchestration install.sh
set -euo pipefail

REPO_URL="https://github.com/{owner}/claude-orchestration.git"
INSTALL_DIR="${HOME}/.claude"
FRAMEWORK_REPO="${INSTALL_DIR}/.framework-repo"

# ── 사전 검증 ──
command -v python3 >/dev/null || { echo "❌ python3 필요"; exit 1; }
command -v git >/dev/null     || { echo "❌ git 필요"; exit 1; }

# ── 모드 감지 ──
MODE="install"
[[ -f "${INSTALL_DIR}/.framework-version" ]] && MODE="update"
[[ "${1:-}" == "--migrate" ]] && MODE="migrate"

# ── 기존 환경 백업 (migrate 시) ──
if [[ "$MODE" == "migrate" ]]; then
  BACKUP="${INSTALL_DIR}/.backup-$(date +%Y%m%d_%H%M%S)"
  echo "📦 기존 환경 백업: $BACKUP"
  mkdir -p "$BACKUP"
  for d in agents hooks harness orchestration commands scripts templates; do
    [[ -d "${INSTALL_DIR}/$d" ]] && cp -R "${INSTALL_DIR}/$d" "$BACKUP/"
  done
  for f in orchestration-rules.md CLAUDE.md settings.json; do
    [[ -f "${INSTALL_DIR}/$f" ]] && cp "${INSTALL_DIR}/$f" "$BACKUP/"
  done
fi

# ── 프레임워크 다운로드 ──
if [[ -d "$FRAMEWORK_REPO" ]]; then
  echo "🔄 기존 repo 업데이트"
  git -C "$FRAMEWORK_REPO" pull --ff-only
else
  echo "📥 프레임워크 다운로드"
  git clone "$REPO_URL" "$FRAMEWORK_REPO"
fi

# ── 버전 읽기 ──
REMOTE_VER=$(cat "${FRAMEWORK_REPO}/VERSION")
LOCAL_VER="0.0.0"
[[ -f "${INSTALL_DIR}/.framework-version" ]] && LOCAL_VER=$(cat "${INSTALL_DIR}/.framework-version")

if [[ "$MODE" == "update" && "$REMOTE_VER" == "$LOCAL_VER" ]]; then
  echo "✅ 이미 최신 (v${LOCAL_VER})"
  exit 0
fi

echo "📋 v${LOCAL_VER} → v${REMOTE_VER}"

# ── 마이그레이션 실행 (필요 시) ──
# migrations/ 디렉토리에서 순차 실행
# (생략 — 향후 구현)

# ── 프레임워크 파일 배포 ──
echo "📂 프레임워크 파일 배포"
for d in agents hooks harness orchestration commands scripts templates; do
  mkdir -p "${INSTALL_DIR}/$d"
  # 기존 파일 제거 후 복사 (잔여 파일 방지)
  rm -rf "${INSTALL_DIR:?}/$d/"*
  cp -R "${FRAMEWORK_REPO}/framework/$d/"* "${INSTALL_DIR}/$d/" 2>/dev/null || true
done
for f in orchestration-rules.md CLAUDE.md; do
  cp "${FRAMEWORK_REPO}/framework/$f" "${INSTALL_DIR}/$f"
done

# setup 스크립트 배포
cp "${FRAMEWORK_REPO}/project-init/"*.sh "${INSTALL_DIR}/" 2>/dev/null || true

# ── 유저 전용 디렉토리 생성 (존재하면 스킵) ──
for d in memory docs project-agents harness-logs custom custom/agents custom/hooks custom/commands; do
  mkdir -p "${INSTALL_DIR}/$d"
done

# ── settings.json smart merge ──
if [[ -f "${INSTALL_DIR}/settings.json" ]]; then
  echo "🔧 settings.json smart merge"
  python3 "${FRAMEWORK_REPO}/settings/merge-settings.py" \
    "${FRAMEWORK_REPO}/settings/settings.template.json" \
    "${INSTALL_DIR}/settings.json"
else
  cp "${FRAMEWORK_REPO}/settings/settings.template.json" "${INSTALL_DIR}/settings.json"
fi

# ── 버전 기록 ──
echo "$REMOTE_VER" > "${INSTALL_DIR}/.framework-version"

# ── 완료 ──
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ claude-orchestration v${REMOTE_VER} 설치 완료"
echo ""
echo "  프레임워크: ${INSTALL_DIR}/"
echo "  유저 커스텀: ${INSTALL_DIR}/custom/"
echo "  버전 파일: ${INSTALL_DIR}/.framework-version"
echo ""
echo "다음 단계:"
echo "  프로젝트 초기화: cd <project> && bash ~/.claude/setup-harness.sh"
echo "  업데이트: claude-orch update"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
```

---

## 6. 업데이트 흐름: 프레임워크 → 하위 프로젝트

```
프레임워크 업데이트               하위 프로젝트 영향
━━━━━━━━━━━━━━━━               ━━━━━━━━━━━━━━━━━━━
agents/ 변경         ─────→    /agent-downSync 실행 (프로젝트에 복사된 에이전트 동기화)
hooks/ 변경          ─────→    즉시 반영 (전역 settings.json이 ~/.claude/hooks/ 참조)
harness/*.sh 변경    ─────→    즉시 반영 (executor.sh가 ~/.claude/harness/ 직접 참조)
orchestration/ 변경  ─────→    즉시 반영 (직접 참조)
commands/ 변경       ─────→    즉시 반영 (직접 참조)
settings.json 구조   ─────→    smart merge가 처리
```

**대부분 즉시 반영** — 에이전트만 `/agent-downSync` 필요 (프로젝트에 복사본이 있으므로).

### 6.1 자동 업데이트 알림 (선택적)

oh-my-zsh처럼 Claude Code 세션 시작 시 자동 체크. 기본 꺼짐 — 유저가 명시적으로 활성화해야 동작.

```python
# framework/hooks/harness-session-start.py에 추가
import os, json, time

def check_framework_update():
    """7일 주기로 remote 버전 확인 → 업데이트 가능하면 안내."""
    root = get_harness_root()
    ver_file = os.path.join(root, '.framework-version')
    check_file = os.path.join(root, '.last-update-check')

    if not os.path.exists(ver_file):
        return

    # 마지막 체크로부터 7일 경과 확인
    if os.path.exists(check_file):
        last = os.path.getmtime(check_file)
        if time.time() - last < 7 * 86400:
            return

    local_ver = open(ver_file).read().strip()
    repo_dir = os.path.join(root, '.framework-repo')
    if not os.path.isdir(repo_dir):
        return

    # git fetch (네트워크 실패 시 무시)
    os.system(f'git -C "{repo_dir}" fetch --quiet 2>/dev/null')
    remote_ver_path = os.path.join(repo_dir, 'VERSION')
    if os.path.exists(remote_ver_path):
        remote_ver = open(remote_ver_path).read().strip()
        if remote_ver != local_ver:
            print(f"⚠️ claude-orchestration {remote_ver} 사용 가능 (현재 {local_ver})")
            print("  업데이트: claude-orch update")

    # 체크 시간 기록
    open(check_file, 'w').write(str(time.time()))
```

활성화: `settings.json`에 `"CLAUDE_ORCH_AUTO_CHECK": "1"` 추가 시에만 동작.

### 6.2 버전 핀닝 (프로젝트별)

특정 프로젝트에서 프레임워크 버전을 고정하고 싶을 때:

```json
// .claude/harness.config.json
{
    "prefix": "mb",
    "framework_version": "1.2.0"
}
```

**동작**:
- `claude-orch update` 실행 시 pinned 프로젝트가 있으면 경고만 출력, 전역 업데이트는 수행
- `/agent-downSync` 실행 시 pinned 버전의 에이전트를 동기화 (최신이 아닌 고정 버전)
- 핀 해제: `framework_version` 키 삭제

**롤백**:
```bash
claude-orch rollback              # 직전 버전으로 롤백
claude-orch rollback 1.0.0        # 특정 버전으로 롤백
```
내부 동작: `.framework-repo`에서 해당 tag checkout → install.sh 재실행

### 6.3 merge-settings.py 병합 전략 상세

`settings/merge-settings.py`가 처리하는 필드별 병합 전략:

```python
MERGE_STRATEGY = {
    "env":               "USER_WINS",      # 유저 값 유지, 신규 키만 추가
    "permissions.allow":  "UNION",          # 합집합 (유저 + 프레임워크)
    "permissions.deny":   "UNION",          # 합집합
    "hooks":             "FRAMEWORK_WINS",  # 프레임워크 훅으로 교체 (핵심)
    "enabledPlugins":    "USER_WINS",      # 유저 선택 유지
    "effortLevel":       "USER_WINS",      # 유저 설정 유지
    "skipDangerousModePermissionPrompt": "USER_WINS",
}
```

| 전략 | 동작 | 적용 대상 |
|------|------|-----------|
| `USER_WINS` | 유저 값 보존, 프레임워크에만 있는 신규 키 추가 | env, plugins, effortLevel |
| `FRAMEWORK_WINS` | 프레임워크 값으로 전체 교체 | hooks (훅 구조는 프레임워크가 관리) |
| `UNION` | 양쪽 값을 합집합 (중복 제거) | permissions allow/deny |

**충돌 시**: `.settings.json.bak` 자동 백업 생성 + 콘솔 경고 출력.

---

## 7. 작업 순서 (에픽)

### Epic 0: 프로젝트 폴더 생성 (안전)

```bash
mkdir -p ~/projects/claude-orchestration
cd ~/projects/claude-orchestration
git init
```

> **주의: 이 작업은 `~/.claude/` 밖에서 진행. 현재 운영 환경은 건드리지 않는다.**

### Epic 1: 구조 + 파일 복사

| # | 태스크 | 상세 |
|---|---|---|
| 1.1 | 디렉토리 구조 생성 | `framework/`, `project-init/`, `settings/`, `migrations/`, `tests/` |
| 1.2 | `~/.claude/`에서 파일 복사 | agents, hooks, harness, orchestration, commands, scripts, templates |
| 1.3 | `VERSION` = `1.0.0` | 초기 버전 |
| 1.4 | `.gitignore` 작성 | 유저 데이터 제외 |
| 1.5 | `settings.template.json` 작성 | 현재 settings.json에서 hooks 섹션 추출 |

### Epic 2: 경로 추상화

| # | 태스크 | 상세 |
|---|---|---|
| 2.1 | `harness_common.py`에 `get_harness_root()` 추가 | `CLAUDE_ORCH_ROOT` → `.framework-version` → 스크립트 위치 폴백 |
| 2.2 | `harness/utils.sh`에 `HARNESS_ROOT` 추상화 | 모든 source 경로 대체 |
| 2.3 | `executor.sh`, `impl-process.sh` source 경로 수정 | `${HOME}/.claude/` → `${HARNESS_ROOT}/` |
| 2.4 | `harness-router.py` executor 경로 수정 | `get_harness_root()` 기반 |
| 2.5 | 나머지 hooks/*.py 경로 참조 점검 | 하드코딩된 `~/.claude/` 제거 |

### Epic 2B: Provider 추상화

| # | 태스크 | 상세 |
|---|---|---|
| 2B.1 | `harness.config.json` 스키마 확장 + `setup-harness.sh` 감지 흐름 | `providers` + `commands` 키 추가, `detect_providers()` 자동 감지 → 유저 확인 → 저장 |
| 2B.2 | `harness/providers/` 디렉토리 구조 생성 | `issues/{github,gitlab,none}.sh`, `test_runner/`, `notification/` |
| 2B.3 | `harness/utils.sh`에 `get_provider()`, `get_command()` 함수 추가 | harness.config.json 읽기 → 폴백 → 기본값 |
| 2B.4 | `harness/impl-process.sh` 테스트 러너 추상화 | `npx vitest run` → `get_command "test"` |
| 2B.5 | `harness/bugfix.sh` 이슈 조회 추상화 | `gh issue view` → `source providers/issues/${PROVIDER}.sh` |
| 2B.6 | `harness/utils.sh` 브랜치 생성 시 이슈 제목 조회 추상화 | `gh issue view` → provider 함수 |
| 2B.7 | `setup-agents.sh` 에이전트 도구 동적 생성 | provider에 따라 `tools:` 행 변경 |
| 2B.8 | `settings.json` 알림음 추상화 | `afplay` → `notify()` 함수 (OS 자동 감지) |
| 2B.9 | 에이전트 지침에서 프레임워크 가정 제거 | React/TypeScript → provider 기반 조건부 지침 |

### Epic 3: 설치/업데이트 스크립트

| # | 태스크 | 상세 |
|---|---|---|
| 3.1 | `install.sh` 작성 | install / update / migrate 3모드 |
| 3.2 | `settings/merge-settings.py` 작성 | hooks=FRAMEWORK_WINS, env=USER_WINS |
| 3.3 | `update.sh` 작성 (install.sh 래퍼) | `install.sh --update` 호출 |
| 3.4 | `uninstall.sh` 작성 | 프레임워크 파일만 제거, 유저 데이터 보존 |

### Epic 4: 에이전트 분리

| # | 태스크 | 상세 |
|---|---|---|
| 4.1 | 각 에이전트에서 공통 지침 추출 | `## 공통 지침` 섹션만 `framework/agents/`에 |
| 4.2 | `setup-agents.sh` 수정 | 프로젝트 특화 템플릿만 생성 (공통은 전역 참조) |
| 4.3 | `/agent-downSync` 수정 | framework 버전 대조 + 동기화 |

### Epic 5: 테스트

| # | 태스크 | 상세 |
|---|---|---|
| 5.1 | `tests/install.bats` | install/update/rollback 테스트 |
| 5.2 | 기존 BATS 테스트 `HARNESS_ROOT` 대응 | 경로 추상화 후에도 115건 PASS 확인 |
| 5.3 | 격리 환경 E2E | 임시 디렉토리에 설치 → 루프 smoke test |

### Epic 6: 문서 + 배포

| # | 태스크 | 상세 |
|---|---|---|
| 6.1 | `README.md` | 설치/사용/업데이트/롤백/커스텀 가이드 |
| 6.2 | `CHANGELOG.md` | v1.0.0 기준 작성 |
| 6.3 | GitHub repo 생성 + push | public 또는 private |
| 6.4 | v1.0.0 태그 + Release | 첫 릴리스 |

### Epic 7: 전환 (현재 환경 → 프레임워크)

| # | 태스크 | 상세 |
|---|---|---|
| 7.1 | 테스트 머신에서 `install.sh --migrate` 검증 | 기존 환경 보존 + 프레임워크 설치 |
| 7.2 | 실제 전환 실행 | `~/.claude/` 환경을 프레임워크 관리로 전환 |
| 7.3 | 기존 프로젝트 `/agent-downSync` 실행 | 에이전트 동기화 |

---

## 8. 결정 필요 항목

| # | 항목 | 선택지 | 추천 |
|---|---|---|---|
| 1 | **repo 이름** | `claude-orchestration` / `claude-harness` / `dotclaude` | `claude-orchestration` |
| 2 | **GitHub 위치** | 개인 / 조직 | 유저 결정 |
| 3 | **공개 여부** | public / private | 유저 결정 |
| 4 | **자동 업데이트** | 기본 켜짐 / 꺼짐 | 기본 꺼짐 (알림만) |
| 5 | **프로젝트 폴더 위치** | `~/projects/claude-orchestration` / 기타 | 유저 결정 |
| 6 | **기본 이슈 트래커** | `github` / `gitlab` / `none` | `github` (현재 구현 기준) |
| 7 | **기본 UI 프레임워크** | `react` / `vue` / `svelte` / `html` / `none` | `react` (현재 구현 기준) |
| 8 | **provider 추상화 범위 (v1.0)** | 전체 / 이슈+테스트+패키지만 / 이슈만 | 이슈+테스트+패키지 (HIGH 이상만 v1.0) |

---

## 9. 리스크 + 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| settings.json merge 실패 | 훅/env 깨짐 | `.settings.json.bak` 자동 백업 + merge 실패 시 수동 안내 |
| 유저가 framework 파일 직접 수정 | 다음 업데이트에서 덮어씌워짐 | `custom/` 가이드 + 업데이트 전 diff 표시 |
| 에이전트 공통/특화 분리 오류 | 에이전트 지침 누락 | E2E 테스트 + `/agent-downSync` 전후 비교 |
| 경로 추상화 누락 | 특정 환경에서 파일 못 찾음 | `HARNESS_ROOT` 폴백 3단계 + BATS 테스트 |
| `~/.claude/` 전환 시 기존 환경 깨짐 | 작업 중단 | `--migrate` 모드가 백업 필수 생성 + 롤백 안내 |
| provider 셸 스크립트 인터페이스 불일치 | GitLab/Jira에서 명령어 실패 | 각 provider에 BATS 테스트 추가 + `none.sh` 폴백 |
| provider 자동 감지 오류 | 잘못된 패키지매니저/테스트러너 사용 | `commands`에 명시적 오버라이드 → 자동 감지보다 우선 |
| 에이전트 지침에 프레임워크 가정 잔류 | React 아닌 프로젝트에서 혼란 | Epic 2B.9에서 전수 점검 + `ui_framework: none` E2E 테스트 |

---

## 10. 요약

```
현재                              전환 후
━━━━━━━━━━━━━━                  ━━━━━━━━━━━━━━━━━
~/.claude/ 직접 관리              GitHub repo + VERSION 관리
수동 파일 복사                    install.sh 한 줄 설치
업데이트 = 파일 직접 수정          claude-orch update (git pull + 복사)
버전 추적 없음                    semver + CHANGELOG + git tag
롤백 불가                         git tag checkout
에이전트 sync = /agent-downSync   그대로 (프레임워크 → 프로젝트 복사 구조)
훅/하네스/orchestration           즉시 반영 (전역 참조)
```

**핵심**: 별도 프로젝트(`~/projects/claude-orchestration/`)에서 작업 → 완성 후 `install.sh --migrate`로 안전하게 전환.
