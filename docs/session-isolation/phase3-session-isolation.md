# Phase 3: 세션 격리 (Session Isolation)

> **선행**: Phase 1(env var 판별) · Phase 2(worktree 격리) 이미 머지됨.
> **후속**: Phase 4(Skill 컨텍스트 보호) — 별도 문서.

---

## 배경

최근 20 PR 중 17개가 훅/상태 관련 땜질. **같은 뿌리 문제를 5번 이상 다른 각도로 패치**함:

- 상태 저장소가 여러 곳에 찢어져 있음 (env var · flag 파일 · 하네스 state)
- 소유권 검증 약함 — 잔재 파일이 활성으로 오인되는 문제 반복
- 세션·이슈·에이전트 식별 경로가 경로별로 다름 (Agent 툴은 env 안 옴, CLI 훅은 stdin으로 옴)
- 프로젝트 전체가 `.claude/harness-state/` 하나를 공유 — 동시 세션 충돌

PR #15~17 디버그 3연발, #24 env 폴백, #26 플래그 폴백, #29 화이트리스트 — 모두 같은 뿌리.

---

## 목표

**한 세션이 사용하는 모든 상태를 session_id로 스코프된 한 곳에서 관리**한다. 훅·하네스·스킬이 같은 경로 규약으로 상태를 읽고 쓴다.

---

## 커버리지

### 해결한다
- 여러 CC 세션이 같은 프로젝트를 동시에 열어도 상태 간섭 없음
- Agent 툴 경로에서도 활성 에이전트 판별이 일관되게 동작 (env var 폴백 로직 제거)
- 훅이 하네스 executor 결과와 상태를 실시간 공유
- 세션 종료/크래시 시 stale 상태가 다음 세션에 오염되지 않음
- 동시 이슈 작업 시 이슈 단위 충돌 방지 (같은 이슈를 두 세션이 잡는 상황 감지)

### 해결하지 않는다 (이 Phase 밖)
- 스킬 실행 중 컨텍스트 보호 → **Phase 4**
- 워크플로우 플래그를 증거(artifact) 기반으로 대체 → 추후 개별 burndown
- 다중 프로젝트 간 상태 공유

---

## 참고 패턴 (OMC 실사 기반)

OMC(`oh-my-claudecode`)에서 확인한 핵심 패턴. 그대로 포팅 대상:

1. **훅 stdin에서 session_id 파싱** — `data.sessionId || data.session_id || data.sessionid || ''` 3변형 fallback
2. **session_id 허용 regex** — `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,255}$` (path traversal 방어)
3. **atomic write** — O_EXCL tmp + UUID suffix + data fsync + atomic rename + directory fsync, mode `0o600`
4. **`_meta` envelope** — state에 `{written_at, mode, sessionId}` 자동 포함. 읽을 때 strip
5. **Ownership 2모드**
   - **strict**: session 스코프 파일. 소유자 없거나 다른 세션이면 reject
   - **lenient**: 전역 신호 파일. 소유자 없어도 허용
   - **경로로 구분** — 호출자가 모드를 고르지 않고 경로 자체가 강제
6. **Stale cleanup** — SessionStart 훅에서 오래된 세션 디렉터리 청소 (TTL 기준)
7. **readStdin timeout** — 2초 타임아웃, 훅 hang 방지

OMC `docs/cancel-skill-active-state-gap.md` 결함에서 배운 것:
- 새 상태 타입 추가 시 여러 곳 등록해야 하는 분산 의존성을 만들지 말 것
- 하나의 상태 API 모듈로 집중

---

## 우리 특화 요구사항 (OMC에 없음)

### ① Python subprocess 체인
OMC는 전부 in-process TS. 우리는 하네스 executor가 CC 밖 Python 프로세스.
→ **CC 세션 ID가 Python subprocess에 전파**되어야 함. SessionStart 훅이 현재 session_id를 알려진 위치에 기록 → Bash/스킬이 그것을 env로 읽어 executor에 주입.

### ② Agent 툴 경로에서 env 미주입
CC가 Agent 툴 subagent에 env var 안 전파 (확정).
→ 훅 stdin session_id가 유일한 식별 경로. 훅이 세션별 상태 파일에 `agent` 필드를 기록/소거하는 것으로 해결.

### ③ Worktree × Session 좌표계
이슈별 worktree(Phase 2) × 세션별 상태(Phase 3) 조합.
- state 저장소 위치: worktree 안에서 훅이 실행되어도 **메인 repo의 한 곳**에서 관리
- 이슈 lock: **세션 밖 경로**에 둠. 한 이슈를 두 세션이 동시에 잡지 못하도록 (세션 ID 기록된 lock 파일)

### ④ 전역 신호
`/harness-kill` 같은 전역 중단 신호는 **모든 세션이 읽어야** 함. 세션 소유자 없는 전역 파일 경로를 별도로 유지.

---

## 파일 구조 (최종형)

`.claude/harness-state/` 하위 **모든 디렉터리·파일은 dot-prefixed(숨김)** 로 둔다. PR #18/#19에서 에이전트가 glob/rm으로 상태 파일을 삭제한 사고의 연장선 — 파일 단위 숨김만 했던 것을 디렉터리 단위까지 확장.

```
{project_root}/.claude/harness-state/
├── .global.json                # 전역 신호 (lenient read)
├── .session-id                 # 현재 세션 ID — subprocess 전파용
├── .sessions/{session_id}/     # 세션 스코프 (strict)
│   ├── live.json               # 활성 에이전트/스킬/이슈/하네스 상태
│   └── flags/{prefix}_{issue}/ # 워크플로우 플래그 (Phase 2 구조 유지)
├── .issues/{prefix}_{issue}/
│   └── lock                    # 이슈 단위 lock (세션 ID 기록)
├── .logs/                      # 디버그/호출 로그
└── .rate/                      # rate limiter (격리 안 함 — 전역 보호)
```

**숨김 규칙의 보호 범위**
- 셸 글롭(`rm *`, `ls`, 기본 `find`)이 기본적으로 매치하지 않음
- 에이전트가 Bash로 범위 청소할 때 실수로 지우는 것 방지
- 명시적 `rm -rf .sessions/` 같은 의도적 삭제는 여전히 가능 — 이건 방어 범위 밖

`.sessions/` 안의 `live.json` 등은 이미 `.` 디렉터리 아래라 이중 숨김 불필요. 디렉터리 숨김 하나로 내부 전체 보호됨.

**live.json 필드** (참고): `session_id`, `agent`, `skill`, `issue_num`, `prefix`, `harness_active`, `_meta`.

---

## 성공 기준

- PR #24 · #26 · #29의 재현 시나리오가 새 구조에서 **버그 없이 통과** (박제 테스트로 확보)
- 2개 세션이 다른 이슈를 동시 작업 → 상태 독립
- 2개 세션이 같은 이슈를 잡으려 하면 두 번째 세션이 명확히 거부됨
- `agent-boundary.py`에서 env var 폴백 / 15분 TTL / 화이트리스트 필터 같은 **방어 로직이 불필요**해짐 (live.json 단일 소스)
- 세션 종료/강제 종료 후 다음 세션이 이전 잔재에 영향받지 않음

---

## 위험과 결정 지점

### D1. 빅뱅 이행
구 `.flags/`는 마이그레이션 1회 시점에 **통째로 삭제**. 이행기 호환 모드 없음.
→ 유저 결정 필요: 이행 시점 (활성 하네스 루프 없을 때)

### D2. session_id 없는 훅 이벤트
OMC 패턴대로 빈 session_id 허용 + 그 경우 전역 경로 폴백. 안전함.

### D3. 세션 재개 (`claude -c`)
- 같은 sid 유지되면 그대로 재사용 가능
- 새 sid면 이전 세션 디렉터리는 stale cleanup이 처리

### D4. 동시 write 경쟁
atomic write로 파일 손상은 없으나 last-writer-wins. 상태 API가 read→modify→write를 하나의 호출로 제공하여 호출자 레벨에서 경합 최소화.

### D5. 다중 CC 세션과 `.session-id` pointer (known limitation)
같은 프로젝트에서 두 CC 세션이 동시에 열려있으면 SessionStart 마다 `.session-id` 가 덮어써져 last-writer-wins. 영향:
- Bash 툴로 spawn된 executor가 `current_session_id()` 호출 시 `HARNESS_SESSION_ID` env 없고 pointer 폴백 → 가장 최근 세션의 sid 반환 → 엉뚱한 session dir에 `harness_active` / `issue_num` 기록
- live.json 자체는 세션별 격리되어 **상태 손실은 없음** — attribution 교차만 발생
- subagent(Agent 툴) 경로는 stdin session_id로 올바른 세션에 기록되므로 영향 없음
- 이슈 lock은 실제 lock holder의 session_id를 기록하므로 두 세션 동시 진입 방지 기능은 유지

정확한 attribution이 필요하면 세션별 Bash env 주입이 필요하지만 CC는 현재 이를 지원하지 않음. 실제 동시 하네스 시나리오가 드물기에 제한으로 문서화.

### D6. 이슈 lock heartbeat 갱신
`executor.heartbeat_loop` 가 주기적으로 `ss.heartbeat_issue_lock()` 을 호출해야 함. 누락되면 `DEFAULT_LOCK_STALE_SEC`(30분) 초과 시 다른 세션이 stale 판정으로 lock 탈취 → 동일 이슈에 두 하네스 동시 작업. executor 구현에서 15초 heartbeat 루프에 반드시 연결해야 한다.

---

## 구현 단계 (원자적 PR)

각 단계는 **혼자 머지 가능**해야 한다. 세부 구현은 구현자 재량.

### Phase 3.A — 기반 모듈 + 마이그레이션
**목표**: 새 상태 API 도입, 기존 동작 영향 없음.
- 세션 상태 로드/저장 모듈 (atomic write, _meta, session 검증 내장)
- session_id 취득 유틸 (stdin fallback 포함)
- 1회 마이그레이션 스크립트 (구 `.flags/` 정리 + 새 뼈대 디렉터리)
- SessionStart 훅 확장 (`.session-id` 기록, stale 청소)

**검증 가능 기준**: 모듈 단위 테스트 통과, 기존 하네스 루프 영향 없음.

### Phase 3.B — 메인 치환 (빅뱅 진입)
**목표**: 훅·하네스의 상태 접근을 전부 새 API로 교체. 이 시점에 PR #24/#26/#29 방어 로직 제거.
- 에이전트/이슈/커밋 관련 훅이 live.json 직접 조회로 전환
- `{agent}_active` 플래그 파일 쓰기·읽기 전부 제거
- 하네스 core/executor가 HARNESS_SESSION_ID 부팅 + SessionState API 호출
- 이슈 lock 도입 (세션 밖 경로)

**검증 가능 기준**: PR #24/#26/#29 재현 박제 테스트, 2세션 격리 테스트, agent-boundary의 폴백 함수가 사라진 것.

### Phase 3.C — 마무리
**목표**: 레거시 정리 및 문서 동기화.
- 로그/rate 파일을 `logs/`, `rate/` 하위로 이동
- SessionEnd 훅으로 세션 디렉터리 자동 정리
- `orchestration-rules.md` 최종 동기화

---

## 비스코프 (다음 페이즈)

| 항목 | 이관 |
|---|---|
| 스킬 실행 중 컨텍스트 보호 | Phase 4 |
| 워크플로우 플래그 → 증거 기반 | 개별 burndown (필요 시) |
| SubagentStop 기반 reinforcement | 해당 워크플로우 발생 시 |
| Windows 호환 | 요구 없음 (macOS/Linux 전제) |
