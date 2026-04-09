# Claude Orchestration Framework — 배포 가능 패키지 전환 계획서

> **작성일**: 2026-04-09
> **상태**: DRAFT — 유저 검토 대기

---

## 1. 배경 & 문제 정의

### 현재 상태
- `~/.claude/` 디렉토리에 에이전트(11개), 훅(13개), 하네스 스크립트(7개), 오케스트레이션 룰, 커맨드(12개), 템플릿 등 **~90개 핵심 파일**이 전역으로 관리됨
- 프로젝트 초기화는 `setup-harness.sh` + `setup-agents.sh`로 수행
- 에이전트 동기화는 `/agent-downSync` (전역→프로젝트), `/agent-upSync` (프로젝트→전역) 커맨드로 수동 수행

### 핵심 문제
| 문제 | 설명 |
|------|------|
| **싱크 단절** | 전역 에이전트/훅/스크립트 업데이트 시, 기존 프로젝트에 반영하려면 수동으로 downSync 실행 필요 |
| **버전 추적 불가** | 어떤 버전의 프레임워크가 프로젝트에 적용되어 있는지 알 수 없음 |
| **온보딩 비용** | 새 머신/팀원이 이 시스템을 사용하려면 파일 수십 개를 수동 복사해야 함 |
| **업데이트 롤백 불가** | 프레임워크 변경이 프로젝트를 깨뜨릴 때 이전 버전으로 돌아갈 방법이 없음 |

### 목표
1. `~/.claude/` 전역 설정을 **GitHub repo로 배포**
2. 한 줄 커맨드로 **설치 + 업데이트** 가능
3. 프레임워크 업데이트가 하위 프로젝트에 **자동 전파**되는 메커니즘
4. **버전 핀닝 + 롤백** 지원

---

## 2. 유사 프레임워크 분석 요약

| 프레임워크 | 설치 | 업데이트 | 전역↔프로젝트 관계 |
|---|---|---|---|
| **oh-my-zsh** | `curl \| bash` → git clone `~/.oh-my-zsh/` | `git pull --rebase`, 자동 업데이트 주기 설정 | `$ZSH/` (프레임워크) vs `$ZSH_CUSTOM/` (유저 오버라이드) — 업데이트가 custom을 건드리지 않음 |
| **chezmoi** | `brew install chezmoi` | `chezmoi update` — git pull + 템플릿 재적용 | 소스 상태(repo) + 머신별 `.chezmoidata.yaml` 오버라이드 |
| **awesome-claude-code-config** | `curl \| bash` | VERSION 파일 비교 → smart merge (hooks 중복 제거, env 보존) | 전역 `~/.claude/` 관리, 프로젝트별 설정은 별도 |

### 결론: **oh-my-zsh 패턴 + VERSION 기반 smart merge** 채택

**선택 이유**:
- 심플: git clone + install.sh → 추가 도구 불필요 (chezmoi는 과도)
- 검증됨: oh-my-zsh가 10년+ 이 패턴으로 운영
- Claude Code 호환: 심링크는 Claude Code 스킬/autocomplete 깨짐 이슈 있음 (anthropics/claude-code#36659) → **복사 기반**이 안전
- 유저 커스텀 보존: 2디렉토리 분리 (framework-managed vs user-custom)

---

## 3. 제안 아키텍처

### 3.1 디렉토리 구조 (배포 repo)

```
claude-orchestration/                    # ← GitHub repo
├── install.sh                           # 원라인 설치 스크립트
├── update.sh                            # 업데이트 스크립트 (install.sh에서도 호출)
├── uninstall.sh                         # 제거 스크립트
├── VERSION                              # semver (예: 1.0.0)
├── CHANGELOG.md                         # 버전별 변경 내역
│
├── framework/                           # 프레임워크 관리 파일 (업데이트 시 덮어쓰기)
│   ├── agents/                          # 전역 에이전트 정의 (11개)
│   │   ├── architect.md
│   │   ├── engineer.md
│   │   ├── validator.md
│   │   └── ...
│   ├── hooks/                           # 전역 훅 (13개)
│   │   ├── harness-router.py
│   │   ├── agent-boundary.py
│   │   └── ...
│   ├── harness/                         # 하네스 실행 엔진 (7개)
│   │   ├── executor.sh
│   │   ├── impl.sh
│   │   └── ...
│   ├── orchestration/                   # 루프 정의 문서 (7개)
│   │   ├── impl.md
│   │   ├── design.md
│   │   └── ...
│   ├── commands/                        # 슬래시 커맨드 (12개)
│   │   ├── init-project.md
│   │   ├── harness-review.md
│   │   └── ...
│   ├── scripts/                         # 유틸리티 스크립트
│   │   ├── harness-review.py
│   │   └── classify-miss-report.py
│   ├── templates/                       # 프로젝트 템플릿
│   │   └── CLAUDE-base.md
│   ├── orchestration-rules.md           # 마스터 룰북
│   ├── CLAUDE.md                        # 전역 Claude 지침
│   └── README.md                        # 시스템 개요
│
├── project-init/                        # 프로젝트 초기화 스크립트
│   ├── setup-harness.sh                 # 하네스 설정 초기화
│   └── setup-agents.sh                  # 에이전트 파일 생성
│
├── settings/                            # settings.json 템플릿
│   ├── settings.template.json           # 전역 settings 기본값
│   └── merge-settings.py                # 기존 settings와 smart merge
│
└── migrations/                          # 버전 마이그레이션 스크립트
    ├── migrate-1.0-to-1.1.sh
    └── migrate-1.1-to-1.2.sh
```

### 3.2 설치 후 `~/.claude/` 구조

```
~/.claude/
├── .framework-version                   # 설치된 프레임워크 버전 (예: 1.0.0)
├── .framework-repo/                     # 프레임워크 git clone (업데이트용)
│
├── agents/                ← framework/agents/ 에서 복사 (업데이트 시 덮어쓰기)
├── hooks/                 ← framework/hooks/
├── harness/               ← framework/harness/
├── orchestration/         ← framework/orchestration/
├── commands/              ← framework/commands/
├── scripts/               ← framework/scripts/
├── templates/             ← framework/templates/
├── orchestration-rules.md ← framework/orchestration-rules.md
├── CLAUDE.md              ← framework/CLAUDE.md
├── settings.json          ← settings/settings.template.json + 유저 커스텀 merge
│
├── custom/                              # 유저 커스텀 (업데이트가 절대 건드리지 않음)
│   ├── agents/                          # 유저 추가 에이전트
│   ├── hooks/                           # 유저 추가 훅
│   ├── commands/                        # 유저 추가 커맨드
│   └── settings-override.json           # 유저 settings 오버라이드
│
├── memory/                ← 유저 소유 (업데이트 건드리지 않음)
├── docs/                  ← 유저 소유
├── project-agents/        ← 유저 소유
├── harness-logs/          ← 유저 소유
└── harness-memory.md      ← 유저 소유
```

**핵심 원칙**: 
- `framework/` 출처 파일 → 업데이트 시 **덮어쓰기** (프레임워크가 관리)
- `custom/`, `memory/`, `docs/`, `project-agents/`, `harness-logs/` → **절대 건드리지 않음** (유저가 관리)
- `settings.json` → **smart merge** (프레임워크 기본값 + 유저 커스텀 합산)

---

## 4. 설치 흐름

### 4.1 신규 설치

```bash
# 한 줄 설치
bash <(curl -fsSL https://raw.githubusercontent.com/{owner}/claude-orchestration/main/install.sh)
```

**install.sh 내부 동작**:

```
1. 사전 검증
   ├── python3, git, bash ≥ 4.0 존재 확인
   ├── ~/.claude/ 존재 여부 확인 → 기존 설치면 update 모드로 분기
   └── Claude Code 설치 확인 (선택적 경고)

2. 프레임워크 다운로드
   ├── git clone {repo} ~/.claude/.framework-repo/
   └── VERSION 파일에서 버전 읽기 → ~/.claude/.framework-version에 기록

3. 파일 배포
   ├── framework/** → ~/.claude/** 복사 (디렉토리별)
   ├── project-init/** → ~/.claude/ 복사 (setup-*.sh)
   └── 유저 전용 디렉토리 생성 (custom/, memory/, docs/)

4. settings.json 초기화
   ├── 기존 settings.json 없음 → settings.template.json 복사
   └── 기존 settings.json 있음 → merge-settings.py 실행 (smart merge)

5. 완료 메시지
   └── 버전, 설치 경로, 다음 단계 안내 출력
```

### 4.2 기존 `~/.claude/` 마이그레이션 (최초 1회)

현재 직접 관리 중인 `~/.claude/`를 프레임워크 관리 구조로 전환:

```bash
# 마이그레이션 스크립트
bash <(curl -fsSL .../install.sh) --migrate
```

```
1. 기존 파일 백업: ~/.claude/.backup-pre-framework/
2. 유저 커스텀 파일 식별 (memory/, project-agents/, harness-logs/ 등)
3. 프레임워크 파일 배포 (기존 파일 덮어쓰기)
4. settings.json smart merge (기존 env/permissions 보존, hooks 업데이트)
5. .framework-version 생성
6. 검증: 주요 파일 존재 확인 + settings.json 파싱 테스트
```

---

## 5. 업데이트 메커니즘

### 5.1 업데이트 실행 방법

```bash
# 방법 1: 셸에서 직접
claude-orch update              # alias (install.sh가 등록)

# 방법 2: Claude Code 내에서
/init-harness --update          # 기존 커맨드 확장

# 방법 3: 수동
cd ~/.claude/.framework-repo && git pull && bash update.sh
```

### 5.2 update.sh 내부 동작

```
1. 현재 버전 확인
   ├── LOCAL_VER = ~/.claude/.framework-version 읽기
   └── REMOTE_VER = .framework-repo/VERSION 읽기

2. 버전 비교
   ├── 같으면 → "이미 최신" 출력, 종료
   └── 다르면 → 계속

3. 마이그레이션 실행 (필요 시)
   ├── LOCAL_VER과 REMOTE_VER 사이 migration 스크립트 순차 실행
   └── 예: 1.0.0 → 1.2.0 이면 migrate-1.0-to-1.1.sh → migrate-1.1-to-1.2.sh

4. 프레임워크 파일 업데이트
   ├── framework/** → ~/.claude/** 덮어쓰기
   │   (agents/, hooks/, harness/, orchestration/, commands/, scripts/, templates/)
   ├── custom/** → 건드리지 않음
   └── 유저 소유 파일 → 건드리지 않음

5. settings.json smart merge
   ├── 프레임워크 hooks 섹션 → 새 버전으로 교체
   ├── 유저 env → 보존
   ├── 유저 permissions → 보존 + 신규 기본값 추가
   ├── 유저 enabledPlugins → 보존
   └── 충돌 → 백업 생성 후 경고 출력

6. 버전 기록
   └── .framework-version 업데이트

7. 하위 프로젝트 알림
   └── "N개 프로젝트에서 /agent-downSync 실행 필요" 출력 (선택적)
```

### 5.3 settings.json smart merge 상세

현재 가장 복잡한 부분. `merge-settings.py`가 처리:

```python
# 병합 전략
{
    "env":              "USER_WINS",     # 유저 값 유지, 신규 키만 추가
    "permissions.allow": "UNION",         # 합집합
    "permissions.deny":  "UNION",         # 합집합
    "hooks":            "FRAMEWORK_WINS", # 프레임워크 훅으로 교체
    "enabledPlugins":   "USER_WINS",     # 유저 선택 유지
}
```

### 5.4 하위 프로젝트 업데이트

프레임워크 업데이트 후, 각 프로젝트에서 해야 할 일:

```
프레임워크 업데이트                  하위 프로젝트 영향
━━━━━━━━━━━━━━━━                  ━━━━━━━━━━━━━━━━━
전역 에이전트 변경    ─────→      /agent-downSync 실행 (공통 지침 동기화)
전역 훅 변경          ─────→      자동 반영 (전역 settings.json에서 관리)
하네스 스크립트 변경   ─────→      자동 반영 (~/.claude/harness/ 직접 참조)
orchestration-rules 변경 ──→      자동 반영 (~/.claude/orchestration-rules.md 직접 참조)
커맨드 변경           ─────→      자동 반영 (~/.claude/commands/ 직접 참조)
settings.json 구조 변경 ──→       smart merge가 자동 처리
```

**핵심**: 현재 구조에서 프로젝트가 전역 파일을 직접 참조하는 항목(훅, 하네스, orchestration-rules, 커맨드)은 **자동 반영**. 프로젝트에 복사하는 항목(에이전트)만 `/agent-downSync` 필요.

### 5.5 자동 업데이트 (선택적)

oh-my-zsh처럼 Claude Code 세션 시작 시 자동 체크:

```python
# harness-session-start.py에 추가
def check_framework_update():
    local_ver = read("~/.claude/.framework-version")
    # 마지막 체크로부터 7일 경과 시
    if days_since_last_check() >= 7:
        remote_ver = fetch_latest_version_from_github()
        if remote_ver > local_ver:
            print(f"⚠️ claude-orchestration {remote_ver} 사용 가능 (현재 {local_ver})")
            print("  업데이트: claude-orch update")
```

---

## 6. 버전 관리 전략

### 6.1 Semantic Versioning

```
MAJOR.MINOR.PATCH

MAJOR: 하위 호환 깨지는 변경 (훅 인터페이스 변경, 에이전트 삭제, 마커 이름 변경)
MINOR: 하위 호환되는 기능 추가 (새 에이전트, 새 커맨드, 새 정책)
PATCH: 버그 수정, 문서 개선
```

### 6.2 버전 핀닝

프로젝트별로 특정 프레임워크 버전 고정 가능:

```json
// .claude/harness.config.json
{
    "prefix": "mb",
    "framework_version": "1.2.0"    // ← 이 프로젝트는 1.2.0 사용
}
```

업데이트 시 pinned 버전이면 경고만 출력, 강제 업데이트하지 않음.

### 6.3 롤백

```bash
claude-orch rollback              # 직전 버전으로 롤백
claude-orch rollback 1.0.0        # 특정 버전으로 롤백
```

내부 동작: `.framework-repo`에서 해당 tag checkout → update.sh 재실행

---

## 7. 구현 로드맵

### Phase 1: 저장소 구조화 (1단계 — 현재 repo 정리)

- [ ] 현재 `~/.claude/` git repo를 배포용 구조로 재편성
  - `framework/` 디렉토리로 프레임워크 파일 이동
  - `project-init/` 디렉토리로 setup 스크립트 이동
  - `settings/` 디렉토리 생성 (템플릿 + merge 스크립트)
  - `migrations/` 디렉토리 생성
- [ ] `.gitignore` 정리 — 배포 대상 아닌 파일 제외
  - `memory/`, `harness-logs/`, `sessions/`, `plans/`, `cache/`, `file-history/`, `paste-cache/`, `session-env/`, `plugins/`, `tasks/`, `backups/`, `downloads/`, `telemetry/`, `history.jsonl`, `stats-cache.json`
- [ ] `VERSION` 파일 생성 (초기 `1.0.0`)
- [ ] `CHANGELOG.md` 작성

### Phase 2: 설치/업데이트 스크립트 (2단계)

- [ ] `install.sh` 작성
  - 사전 검증 (python3, git, bash)
  - git clone → 파일 배포
  - settings.json 초기화/merge
  - `--migrate` 플래그 지원 (기존 유저용)
- [ ] `update.sh` 작성
  - 버전 비교 → 마이그레이션 → 파일 덮어쓰기 → settings merge
- [ ] `uninstall.sh` 작성
- [ ] `settings/merge-settings.py` 작성
  - hooks: FRAMEWORK_WINS
  - env/permissions/plugins: USER_WINS
- [ ] alias 등록 (`claude-orch`)

### Phase 3: 자동 전파 개선 (3단계)

- [ ] `/agent-downSync` 개선 — 버전 태깅 추가
  - 동기화 시 프레임워크 버전을 에이전트 파일에 기록
  - 버전 불일치 시 경고 출력
- [ ] `harness-session-start.py` — 자동 업데이트 체크 추가
  - 7일 주기로 remote 버전 확인
  - 업데이트 가능하면 세션 시작 시 안내
- [ ] 프로젝트 등록 시스템 (선택적)
  - `~/.claude/.project-registry` — 이 프레임워크를 사용하는 프로젝트 목록
  - 업데이트 후 "N개 프로젝트에서 downSync 필요" 안내

### Phase 4: 문서화 & 배포 (4단계)

- [ ] GitHub repo 공개 설정
- [ ] README.md — 설치 가이드, 사용법, 업데이트 방법
- [ ] `custom/` 디렉토리 가이드 (유저 확장 방법)
- [ ] 기여 가이드 (PR 규칙, 버전 범프 규칙)
- [ ] 릴리스 태깅 (GitHub Releases + tag)

---

## 8. 고려사항 & 결정 필요 항목

### 8.1 결정 필요

| 항목 | 선택지 | 추천 |
|------|--------|------|
| **repo 위치** | 개인 GitHub / 조직 GitHub | 유저 결정 |
| **repo 이름** | `claude-orchestration` / `claude-harness` / `dotclaude` | `claude-orchestration` (명확) |
| **공개 여부** | public / private | 유저 결정 |
| **custom/ 디렉토리 도입** | 즉시 도입 / 나중에 | Phase 1에서 즉시 도입 추천 (유저 확장 파일이 덮어쓰기되는 사고 방지) |
| **자동 업데이트** | 기본 켜짐 / 기본 꺼짐 | 기본 꺼짐 (알림만), 수동 실행 추천 |
| **setup-agents.sh 복사 방식** | 현행 유지 (heredoc) / 템플릿 파일 참조 | 템플릿 파일 참조로 전환 추천 (유지보수성) |

### 8.2 리스크

| 리스크 | 대응 |
|--------|------|
| settings.json merge 실패 | 백업 파일 자동 생성 (`.settings.json.bak`), merge 실패 시 수동 merge 안내 |
| 프레임워크 파일에 유저가 직접 수정한 내용 덮어쓰기 | `custom/` 디렉토리 안내 + 업데이트 전 diff 표시 |
| git clone 실패 (네트워크/인증) | tarball 폴백 (`curl` 다운로드) 지원 |
| Claude Code 심링크 버그 | 복사 기반으로 우회 (심링크 사용 안 함) |

### 8.3 현재 구조에서 이미 "자동 반영"되는 항목

현재 프로젝트들이 `~/.claude/`의 파일을 **직접 참조**하는 항목은 프레임워크 업데이트만으로 자동 반영:

- **전역 훅** (`~/.claude/settings.json` → `~/.claude/hooks/*.py`)
- **하네스 스크립트** (프로젝트에서 `~/.claude/harness/executor.sh` 직접 실행... 은 아님)

⚠️ **주의**: 현재 `setup-agents.sh`가 `harness/executor.sh`를 프로젝트에 **복사**하고 있음 (247-256행). 이 복사를 제거하고 전역 참조로 전환하면 하네스 업데이트도 자동 반영됨.

**권장 변경**: `setup-harness.sh`에서 이미 "글로벌 전용" 원칙을 선언하고 낡은 복사본을 삭제하지만, `setup-agents.sh`가 여전히 `executor.sh`를 복사하는 불일치가 있음. 이를 통일해야 함.

---

## 9. 마이그레이션 체크리스트 (현재 유저용)

프레임워크 패키지 전환 후, 현재 사용 중인 유저가 해야 할 일:

```
1. 프레임워크 설치
   bash <(curl -fsSL .../install.sh) --migrate

2. 유저 커스텀 파일 확인
   - ~/.claude/custom/ 에 개인 에이전트/훅/커맨드 이동
   - memory/, project-agents/ 는 자동 보존

3. 기존 프로젝트 동기화
   - 각 프로젝트에서 /agent-downSync 실행
   - .claude/harness/executor.sh 복사본 삭제 (전역 참조로 전환)

4. 검증
   - claude 새 세션 시작 → 훅 정상 동작 확인
   - 테스트 프로젝트에서 /init-project 실행 → 정상 초기화 확인
```

---

## 10. 요약

```
현재                              전환 후
━━━━━━━━━━━━━━                  ━━━━━━━━━━━━━━━━━
수동 파일 관리                    GitHub repo + 버전 관리
setup-*.sh 로 개별 프로젝트 초기화  install.sh로 전역 한 번 설치
/agent-downSync 수동              프레임워크 업데이트 → 대부분 자동 반영
버전 추적 없음                    semver + CHANGELOG
롤백 불가                         git tag 기반 롤백
팀 공유 불가                      git clone으로 동일 환경 재현
```

**다음 단계**: 이 계획서에 대한 유저 피드백을 받고, 결정 필요 항목 (8.1) 확정 후 Phase 1부터 시작.
