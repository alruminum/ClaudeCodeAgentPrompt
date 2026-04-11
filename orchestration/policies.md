# 정책 (절대 원칙)

정책 전문. 번호는 논리적 그룹별 순차 정렬. 메인 Claude·모든 에이전트가 참조.

---

### 핵심 금지

**1. 메인 Claude — src/** 직접 Edit/Write 절대 금지**
이유 불문. 규모 불문. 상황 불문.
반드시 `bash ~/.claude/harness/executor.sh`를 통해서만 구현.

**2. 메인 Claude — 에이전트 직접 호출 절대 금지 (qa·designer 예외 있음)**
architect, engineer, validator 등 하네스 내부 에이전트를 메인 Claude가 Agent 도구로 직접 호출 금지.
반드시 `bash ~/.claude/harness/executor.sh <mode> ...` 를 통해서만 에이전트를 실행한다.

**qa 예외**: qa 스킬이 QA 에이전트를 Agent 도구로 직접 호출해 분류 + 이슈 생성을 수행한다.
분류 결과에 따라 qa 스킬이 직접 라우팅한다 (executor.sh impl --issue <N> / ux 스킬 / 유저 보고).

**designer 예외**: designer 에이전트는 결과물이 Pencil 캔버스(파일 변경 없음, git 없음)이므로 하네스 루프 적용 대상이 아니다.
ux 스킬이 designer 에이전트를 Agent 도구로 직접 호출한다. executor.sh design 경유 금지.

금지 예시:
- 구현 전 analyst 직접 호출 ❌ → `executor.sh impl` 로 진입 ✅

예외:
- 버그 보고 → qa 스킬 → QA 에이전트 직접 호출 ✅ (분류 + 이슈 생성 후 executor.sh impl --issue <N> 라우팅)
- UX 디자인 요청 → ux 스킬 → designer 에이전트 직접 호출 ✅ (Pencil 캔버스 결과물, 하네스 불필요)

**3. 메인 Claude — 하네스 진입 전 GitHub 이슈 직접 생성 금지**
`create_issue` MCP를 하네스 진입 전 메인 Claude가 직접 호출 금지.
이슈 생성은 qa 에이전트가 내부에서 처리한다.
유저가 이슈 번호를 직접 지정한 경우에만 `--issue <N>` 플래그로 전달하면 된다.

**4. 구현 루프 예외 없음**
`src/**` 변경이 발생하는 모든 작업은 구현 루프를 반드시 거친다.
"줄 수가 적다", "간단한 수정", "빨리 해달라" — 어느 것도 루프 자체를 건너뛰는 근거가 되지 않는다.
단, `--depth=simple` 플래그로 루프 깊이를 줄이는 것은 허용된다. → depth 상세: [orchestration/impl.md](impl.md)

---

### 유저 게이트

**5. 유저 게이트 — 자동 진행 절대 금지**

| 게이트 | 금지 행동 |
|--------|-----------|
| `READY_FOR_IMPL` | 유저 명시 승인 전 구현 루프 자동 진입 금지 |
| `DESIGN_HANDOFF` | 유저 선택 전 구현 루프 자동 진입 금지 |
| `HARNESS_DONE` | 유저 보고 후 대기. 다음 모듈 자동 진입 금지 |
| ~~`PLAN_DONE`~~ | **폐기** — `PRODUCT_PLAN_READY` + `READY_FOR_IMPL` 유저 게이트로 대체. |
| `PLAN_VALIDATION_PASS` | 유저 확인 전 impl 자동 호출 금지 |

---

### 실행 규칙

**6. 서브에이전트 포어그라운드 순차 실행**
메인 Claude가 Bash 도구로 `~/.claude/harness/executor.sh`를 직접 실행한다.
백그라운드 스폰(Popen) 금지. 한 에이전트가 완료된 후 다음 에이전트 호출.
실행 중 출력은 대화창에 그대로 노출되며, /cancel로 중단 가능.

**7. 하네스 Bash 포어그라운드 강제**
메인 Claude가 `harness/executor.sh`를 Bash로 실행할 때
**반드시 포어그라운드**(기본값)로 실행한다. `run_in_background` 금지.
포어그라운드면 Bash 완료까지 Claude가 블로킹되므로 Stop 트리거 자체가 발생하지 않는다.

유저는 `/cancel` 또는 `/harness-kill`로 언제든 중단 가능.

---

### 에스컬레이션

**8. 에스컬레이션 → 메인 Claude 보고 후 대기 + 복귀 옵션 제시**
에스컬레이션 마커 수신 시 자동 복구 시도 금지.
반드시 유저에게 보고 후 지시를 기다린다.
보고 시 아래 복귀 옵션을 제시한다:
- **재시도**: 카운터 리셋 후 실패 단계부터 재실행
- **롤백**: 이전 페이즈(설계/기획)로 돌아가 재작업
- **중단**: 현재 브랜치 보존 후 루프 종료

**9. SPEC_GAP는 attempt를 소비하지 않는다 (동결)**
SPEC_GAP_FOUND → architect SPEC_GAP → SPEC_GAP_RESOLVED 사이클은 attempt 카운터를 소비하지 않고 **동결**한다.
대신 별도 `spec_gap_count` (max 2)를 사용한다.
- attempt(SPEC_GAP 제외)가 3회 도달 → IMPLEMENTATION_ESCALATE
- spec_gap_count가 2회 도달 → IMPLEMENTATION_ESCALATE
- 최대 시도: attempt 3 + spec_gap 2 = 라운드 5회
이전의 "리셋" 방식(attempt 카운터를 0으로 되돌림)은 폐기. 오실레이션 방지.

**10. 재시도 루프는 반드시 한도 체크 분기를 가진다**
다이어그램에서 재시도 루프(예: TE_SELF, ENG_RETRY)를 표현할 때, "max N회" 텍스트만으로는 부족하다.
반드시 `LIMIT_CHK{{"count > max?"}}` 분기 노드를 다이어그램에 포함하고, 초과 시 에스컬레이션 또는 FAIL_ROUTE에 연결한다.

---

### 유지보수

**11. 단일 소스 원칙 — orchestration-rules.md 선행 수정 강제**
워크플로우 변경(에이전트 추가/삭제, 루프 순서 변경, 마커 추가, 플래그 추가)이 필요할 때:
1. **먼저** `orchestration-rules.md`에 변경 사항을 반영한다.
2. **그 다음** 스크립트(`harness/executor.sh`, `harness/impl.sh`, `harness/impl_simple.sh`, `harness/impl_std.sh`, `harness/impl_deep.sh`, `harness/design.sh`, `harness/plan.sh`, `setup-harness.sh` 등)를 업데이트한다.
3. 스크립트를 먼저 수정하고 이 파일을 나중에 수정하는 것은 **절대 금지**.
위반 시 PreToolUse 훅이 차단한다 (`orch_rules_first` 게이트).

**12. 하네스 관련 수정 순서**
`harness/executor.sh` / `harness/{impl,impl_simple,impl_std,impl_deep,design,plan}.sh` / `hooks/*.py` / `settings.json(hooks 섹션)` / 에이전트 파일 변경 시:
1. **먼저** `docs/harness-backlog.md` — 해당 항목 상태 업데이트 또는 신규 항목 추가
2. **그 다음** 실제 파일 수정
3. **마지막** `docs/harness-state.md` 관련 섹션 현행화 (완료 기능 / 플래그 / 파일 인벤토리)
순서 위반(backlog 없이 수정, state 나중에 안 하는 것) 금지.
물리적 강제: 현재는 written policy. 향후 `orch-rules-first.py` 확장으로 물리적 차단 예정.

**13. 마커 동기화 — 에이전트 → 루프 → 스크립트**
에이전트 파일(`agents/*.md`)에서 마커(인풋/아웃풋)를 추가·변경·삭제할 때:
1. 에이전트 파일 수정
2. 해당 루프 파일(`orchestration/*.md`) 마커 흐름 반영
3. 하네스 스크립트 파싱 로직 반영
단독 수정 금지. 1→2→3 순서 강제.

---

### 하네스 내부

**14. 실패 패턴 자동 프로모션**
`harness-memory.md`에 같은 파일+유형 조합의 실패가 3회 이상 누적되면:
1. 해당 패턴을 `## Auto-Promoted Rules` 섹션으로 이동
2. 이후 CONSTRAINTS 로드 시 Auto-Promoted Rules를 최우선 포함
3. 프로모션된 규칙은 수동 삭제 전까지 영구 적용

**15. 수용 기준 메타데이터 없는 태스크 = 구현 진입 불가**
impl 파일의 모든 요구사항 항목은 `## 수용 기준` 섹션에 검증 방법 태그가 있어야 한다.

**impl 파일 필수 포맷 요구사항**:
- `## 수용 기준` 섹션 필수 (섹션 자체가 없으면 PLAN_VALIDATION_FAIL)
- 각 요구사항 행에 `(TEST)` / `(BROWSER:DOM)` / `(MANUAL)` 중 하나 필수

**검증 방법 태그 의미**:
| 태그 | 의미 | 사용 조건 |
|---|---|---|
| `(TEST)` | vitest 자동 테스트 | 기본값 — 로직·상태·훅 검증 |
| `(BROWSER:DOM)` | Playwright DOM 쿼리 | UI 렌더링·DOM 상태 검증이 필요한 경우 |
| `(MANUAL)` | curl/bash 수동 절차 | 자동화가 불가능한 경우에만 (이유 명시 필수) |

impl 진입 게이트 상세 (validator Plan Validation 내부에서 통합 수행):
```
validator [Plan Validation — 체크리스트 A·B·C 통합]
  A: 구현 가능성
  B: 스펙 완결성
  C: 수용 기준 메타데이터 감사  ← 정책 15 게이트
  태그 없는 요구사항 발견 → PLAN_VALIDATION_FAIL (architect 재보강)
  ↓ PASS (A+B+C 모두 통과)
READY_FOR_IMPL
```
> Note: 정책 15 게이트는 별도 validator 호출이 아닌 Plan Validation 체크리스트 C로 통합 수행.

**16. kill_check 공용화**
`kill_check()` 함수는 `harness/impl_{simple,std,deep}.sh`와 `harness/executor.sh` 양쪽에서 사용한다.
`harness/utils.sh`에 정의하여 양쪽에서 source로 공유한다.

**17. 하네스 완료 후 자동 리뷰**
HARNESS_DONE / IMPLEMENTATION_ESCALATE / HARNESS_CRASH / KNOWN_ISSUE / PLAN_VALIDATION_PASS / PLAN_VALIDATION_ESCALATE 수신 후,
메인 Claude는 `/harness-review`를 자동 실행한다.
HARNESS_CRASH 시에는 `write_run_end()`이 백그라운드로 리뷰를 자동 트리거하므로,
결과 파일(`*_review.txt`)이 이미 존재할 수 있다.
유저 보고 전 리뷰 완료를 기다린다 (블로킹).

**리포트 원문 그대로 출력 (절대 준수):**
- 리포트 마크다운을 한 글자도 바꾸지 않고 그대로 출력한다
- 테이블을 박스·리스트·요약표로 재가공 금지
- 섹션 생략·축약·재배치 금지
- "핵심 원인은~" 같은 자체 해석을 리포트 중간에 삽입 금지
- 추가 코멘트는 리포트 전문 출력 **후** 별도 줄에서만 허용

**18. JSONL run_end에 결과 마커 기록**
`write_run_end()` 호출 시 `HARNESS_RESULT` 환경변수의 값을 `run_end` 이벤트의 `result` 필드에 기록한다.
각 종료 경로에서 `HARNESS_RESULT`를 설정해야 한다:

| 종료 경로 | HARNESS_RESULT 값 |
|---|---|
| 정상 완료 (commit 성공) | `HARNESS_DONE` |
| 3회 실패 | `IMPLEMENTATION_ESCALATE` |
| 킬 스위치 | `HARNESS_KILLED` |
| 비용 상한 초과 | `HARNESS_BUDGET_EXCEEDED` |
| simple 루프 성공 | `HARNESS_DONE` |
| 크래시/unhandled exit | `HARNESS_CRASH` (write_run_end이 unknown 감지 시 자동 변환) |
| merge 충돌 | `MERGE_CONFLICT_ESCALATE` |

**19. post-commit-scan (선택적)**
`hooks/post-commit-scan.sh`는 커밋 후 간단한 정적 분석(console.log, any 타입, TODO 잔류)을 수행한다.
현재 settings.json에 미등록 — 필요 시 PostToolUse(Bash)에 추가하거나 git post-commit 훅으로 직접 사용.
결과는 `/tmp/{prefix}_scan_report.txt`에 저장.

**20. 쉘 스크립트 코드 품질 규칙**
하네스 쉘 스크립트(`harness/executor.sh`, `harness/{impl,impl_simple,impl_std,impl_deep,design,plan}.sh`, `harness/utils.sh`) 수정 시:
- **변수 인용**: `$var` → `"$var"` (for 루프, grep 패턴, 조건식). 예외: `${array[@]}`, `$?`, `$#`
- **grep 리터럴**: 파이프(`|`) 등 메타문자가 포함된 패턴은 `grep -F` 사용
- **원자적 쓰기**: 공유 파일(harness-memory.md 등) append 시 `mktemp` → `cat >> target` → `rm` 패턴 사용
- **for 루프**: 파일 경로 목록 순회 시 `for f in $var` 대신 `while IFS= read -r f` 사용

**21. 에이전트 자율 탐색 원칙 (Phase A+B)**
에이전트 간 결과 전달 시 요약/발췌를 인라인 주입하지 않는다.
대신 `explore_instruction()` 함수(`harness/utils.sh`)로 이전 출력 파일 경로를 전달하고, 에이전트가 스스로 필요한 파일을 선택해 읽게 한다.

- **금지**: `task="[테스트 실패] ${error_1line} …"` 처럼 에러 발췌를 인라인으로 붙이는 것
- **허용**: 특정 파일의 **경로 힌트**(hint)만 제공하는 것 (읽을지 말지는 에이전트 판단)
- `explore_instruction <loop_out_dir> [hint_file]` → 표준 탐색 지시 문자열 반환 (탐색 예산: 최대 5개 파일, 합계 100KB 이내)
- 히스토리 구조: `HIST_DIR=/tmp/${PREFIX}_history/` 하위에 루프별 attempt-N/ 디렉토리로 보존
  - impl: `HIST_DIR/impl/attempt-N/` (engineer.log, test-results.log, validator.log, pr.log, meta.json)
  - design: `HIST_DIR/design/round-N/` (designer.log, critic.log, meta.json)
  - ~~bugfix: 폐기 — QA/DESIGN_HANDOFF는 impl 루프로 통합~~
- `LOOP_OUT_DIR = HIST_DIR/{loop}` — 이중 저장 금지. 플랫 파일(`attempt-N-agent.log`)은 사용하지 않음
- `write_attempt_meta <meta_file> …` — jq 우선, 없으면 python3 fallback
- `prune_history <loop_dir>` — attempt 5개 초과/단일 로그 50KB 초과/design round 3개 초과/전체 5MB 초과 시 정리
  - 호출 시점: attempt 디렉토리 생성 직후, 파일 기록 전 (race condition 방지)
- 이 원칙은 impl/design/plan/tech-epic 모든 루프에 적용 (tech-epic.sh 구현 시 처음부터 HIST_DIR 구조 적용)
