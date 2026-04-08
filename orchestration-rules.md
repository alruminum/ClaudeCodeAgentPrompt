# 오케스트레이션 룰

모든 프로젝트에서 공통으로 적용되는 에이전트 워크플로우 규칙.
**룰 변경 시 이 파일만 수정** → 스크립트·에이전트 업데이트의 단일 기준점.

---

## 루프 진입 기준 (메인 Claude)

| 상황 | 호출 |
|------|------|
| 신규 프로젝트 / PRD 변경 | → **[기획 루프](orchestration/plan.md)** |
| UI 변경 요청 (design_critic_passed 없음) | → **[디자인 루프](orchestration/design.md)** |
| 구현 요청 (READY_FOR_IMPL 또는 plan_validation_passed) | → **[구현 루프](orchestration/impl.md)** (`bash .claude/harness/executor.sh impl ...`) — plan_validation_passed 시 architect+validator 자동 스킵 |
| 버그 보고 | → **[버그픽스 루프](orchestration/bugfix.md)** (`bash .claude/harness/executor.sh bugfix ...`) — qa 라우팅 기반 4-way 분기 |
| 기술 에픽 / 리팩 / 인프라 | → **[기술 에픽 루프](orchestration/tech-epic.md)** |
| **AMBIGUOUS** | → **Adaptive Interview** (Haiku Q&A → 충분하면 product-planner → 기획 루프) |

---

→ 상세: [orchestration/plan.md](orchestration/plan.md)
→ 상세: [orchestration/design.md](orchestration/design.md)
→ 상세: [orchestration/impl.md](orchestration/impl.md)
→ 상세: [orchestration/bugfix.md](orchestration/bugfix.md)
→ 상세: [orchestration/tech-epic.md](orchestration/tech-epic.md)

---

## 에스컬레이션 마커 — 모두 "메인 Claude 보고 후 대기"

| 마커 | 발행 주체 | 처리 |
|------|-----------|------|
| `DESIGN_REVIEW_ESCALATE` | validator Mode A (재검 후 재FAIL) | 메인 Claude 보고 |
| `VALIDATION_ESCALATE` | validator Mode B (3회 초과) | 메인 Claude 보고 |
| `REVIEW_LOOP_ESCALATE` | pr-reviewer (3라운드 초과) | 메인 Claude 보고 |
| `KNOWN_ISSUE` | qa (원인 특정 3회 실패) | 메인 Claude 보고 |
| `SPEC_MISSING` | validator Mode B (impl 없음) | architect Module Plan 호출 |
| `PRODUCT_PLANNER_ESCALATION_NEEDED` | architect Mode C | product-planner 에스컬레이션 |
| `IMPLEMENTATION_ESCALATE` | harness/impl-process.sh (3회 실패 or SPEC_GAP 리셋 초과) | architect SPEC_GAP 권장 |
| `DESIGN_LOOP_ESCALATE` | designer (3라운드 후에도 ITERATE) | 유저 직접 선택 |
| `TECH_CONSTRAINT_CONFLICT` | architect Mode C (기술 제약 충돌) | 메인 Claude 보고 |
| `PLAN_VALIDATION_ESCALATE` | validator Plan Validation (재검 후 재FAIL) | 메인 Claude 보고 |
| `MERGE_CONFLICT_ESCALATE` | harness/impl-process.sh / harness/executor.sh (merge 실패) | 메인 Claude 보고 |

---

## 정책 (절대 원칙)

**1. 메인 Claude — src/** 직접 Edit/Write 절대 금지**
이유 불문. 규모 불문. 상황 불문.
반드시 `bash .claude/harness/executor.sh`를 통해서만 구현.

**2. 구현 루프 예외 없음**
`src/**` 변경이 발생하는 모든 작업은 구현 루프를 반드시 거친다.
"줄 수가 적다", "간단한 수정", "빨리 해달라" — 어느 것도 루프 자체를 건너뛰는 근거가 되지 않는다.
단, `--depth=fast` 플래그로 루프 깊이를 줄이는 것은 허용된다. → depth 상세: [orchestration/impl.md](orchestration/impl.md)

**3. 유저 게이트 — 자동 진행 절대 금지**

| 게이트 | 금지 행동 |
|--------|-----------|
| `READY_FOR_IMPL` | 유저 명시 승인 전 구현 루프 자동 진입 금지 |
| `DESIGN_HANDOFF` | 유저 선택 전 구현 루프 자동 진입 금지 |
| `HARNESS_DONE` | 유저 보고 후 대기. 다음 모듈 자동 진입 금지 |
| `PLAN_DONE` | 유저 결정 전 다음 단계 진입 금지 |
| `PLAN_VALIDATION_PASS` | 유저 확인 전 impl 자동 호출 금지 |

**4. 서브에이전트 포어그라운드 순차 실행**
메인 Claude가 Bash 도구로 `harness/executor.sh`를 직접 실행한다.
백그라운드 스폰(Popen) 금지. 한 에이전트가 완료된 후 다음 에이전트 호출.
실행 중 출력은 대화창에 그대로 노출되며, /cancel로 중단 가능.

**5. 에스컬레이션 → 메인 Claude 보고 후 대기**
에스컬레이션 마커 수신 시 자동 복구 시도 금지.
반드시 유저에게 보고 후 지시를 기다린다.

**6. 단일 소스 원칙 — orchestration-rules.md 선행 수정 강제**
워크플로우 변경(에이전트 추가/삭제, 루프 순서 변경, 마커 추가, 플래그 추가)이 필요할 때:
1. **먼저** 이 파일(`orchestration-rules.md`)에 변경 사항을 반영한다.
2. **그 다음** 스크립트(`harness/executor.sh`, `harness/impl.sh`, `harness/impl-process.sh`, `harness/design.sh`, `harness/bugfix.sh`, `harness/plan.sh`, `setup-harness.sh` 등)를 업데이트한다.
3. 스크립트를 먼저 수정하고 이 파일을 나중에 수정하는 것은 **절대 금지**.
위반 시 PreToolUse 훅이 차단한다 (`orch_rules_first` 게이트).

**7. 실패 패턴 자동 프로모션**
`harness-memory.md`에 같은 파일+유형 조합의 실패가 3회 이상 누적되면:
1. 해당 패턴을 `## Auto-Promoted Rules` 섹션으로 이동
2. 이후 CONSTRAINTS 로드 시 Auto-Promoted Rules를 최우선 포함
3. 프로모션된 규칙은 수동 삭제 전까지 영구 적용

**8. 수용 기준 메타데이터 없는 태스크 = 구현 진입 불가**
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

impl 진입 게이트 상세:
```
validator [Plan Validation]
  ↓ PASS (기존 A/B 체크)
validator [수용 기준 메타데이터 감사]  ← 정책 8 게이트
  태그 없는 요구사항 발견 → PLAN_VALIDATION_FAIL (architect 재보강)
  ↓ PASS
READY_FOR_IMPL
```

**9a. kill_check 공용화**
`kill_check()` 함수는 `harness/impl-process.sh`와 `harness/executor.sh` 양쪽에서 사용한다.
`harness/utils.sh`에 정의하여 양쪽에서 source로 공유한다.

**9. 하네스 관련 수정 순서**
`harness/executor.sh` / `harness/{impl,design,bugfix,plan}.sh` / `harness/impl-process.sh` / `hooks/*.py` / `settings.json(hooks 섹션)` / 에이전트 파일 변경 시:
1. **먼저** `docs/harness-backlog.md` — 해당 항목 상태 업데이트 또는 신규 항목 추가
2. **그 다음** 실제 파일 수정
3. **마지막** `docs/harness-state.md` 관련 섹션 현행화 (완료 기능 / 플래그 / 파일 인벤토리)
순서 위반(backlog 없이 수정, state 나중에 안 하는 것) 금지.
물리적 강제: 현재는 written policy. 향후 `orch-rules-first.py` 확장으로 물리적 차단 예정.

**10. 하네스 완료 후 자동 리뷰**
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

**12. JSONL run_end에 결과 마커 기록**
`write_run_end()` 호출 시 `HARNESS_RESULT` 환경변수의 값을 `run_end` 이벤트의 `result` 필드에 기록한다.
각 종료 경로에서 `HARNESS_RESULT`를 설정해야 한다:

| 종료 경로 | HARNESS_RESULT 값 |
|---|---|
| 정상 완료 (commit 성공) | `HARNESS_DONE` |
| 3회 실패 | `IMPLEMENTATION_ESCALATE` |
| 킬 스위치 | `HARNESS_KILLED` |
| 비용 상한 초과 | `HARNESS_BUDGET_EXCEEDED` |
| bugfix engineer_direct 성공 | `HARNESS_DONE` |
| 크래시/unhandled exit | `HARNESS_CRASH` (write_run_end이 unknown 감지 시 자동 변환) |
| merge 충돌 | `MERGE_CONFLICT_ESCALATE` |

**13. post-commit-scan (선택적)**
`hooks/post-commit-scan.sh`는 커밋 후 간단한 정적 분석(console.log, any 타입, TODO 잔류)을 수행한다.
현재 settings.json에 미등록 — 필요 시 PostToolUse(Bash)에 추가하거나 git post-commit 훅으로 직접 사용.
결과는 `/tmp/{prefix}_scan_report.txt`에 저장.

**14. 쉘 스크립트 코드 품질 규칙**
하네스 쉘 스크립트(`harness/executor.sh`, `harness/{impl,design,bugfix,plan}.sh`, `harness/impl-process.sh`, `harness/utils.sh`) 수정 시:
- **변수 인용**: `$var` → `"$var"` (for 루프, grep 패턴, 조건식). 예외: `${array[@]}`, `$?`, `$#`
- **grep 리터럴**: 파이프(`|`) 등 메타문자가 포함된 패턴은 `grep -F` 사용
- **원자적 쓰기**: 공유 파일(harness-memory.md 등) append 시 `mktemp` → `cat >> target` → `rm` 패턴 사용
- **for 루프**: 파일 경로 목록 순회 시 `for f in $var` 대신 `while IFS= read -r f` 사용

**11. 하네스 Bash 포어그라운드 강제**
메인 Claude가 `harness/executor.sh`를 Bash로 실행할 때
**반드시 포어그라운드**(기본값)로 실행한다. `run_in_background` 금지.
포어그라운드면 Bash 완료까지 Claude가 블로킹되므로 Stop 트리거 자체가 발생하지 않는다.

유저는 `/cancel` 또는 `/harness-kill`로 언제든 중단 가능.

**15. 마커 동기화 — 에이전트 → 루프 → 스크립트**
에이전트 파일(`agents/*.md`)에서 마커(인풋/아웃풋)를 추가·변경·삭제할 때:
1. 에이전트 파일 수정
2. 해당 루프 파일(`orchestration/*.md`) 마커 흐름 반영
3. 하네스 스크립트 파싱 로직 반영
단독 수정 금지. 1→2→3 순서 강제.

---

## 브랜치 전략 (Feature Branch)

### 브랜치 네이밍
구현 루프 / 버그픽스 루프 실행은 feature branch에서 수행한다.
네이밍: `{type}/{milestone}-{issue}-{slug}` (# 없이 숫자만)

- `type`: `feat` (구현 루프) / `fix` (버그픽스 루프 bugfix)
- `milestone`: harness.config.json의 milestone 값 (없으면 생략)
- `issue`: GitHub issue 번호 (숫자만)
- `slug`: issue title에서 영문/숫자만 추출, 30자 캡. 한국어만이면 생략

예시: `feat/mvp-42-add-login` / `fix/57` (한국어 제목)

### 브랜치 생성 시점
- harness/impl-process.sh impl 모드 engineer 루프 진입 직후 (engineer 호출 전)
- harness/executor.sh _run_bugfix_direct() 진입 직후

### 커밋 규칙
- feature branch: commit-gate의 pr_reviewer_lgtm 면제, engineer 자유 커밋
- 실패 시: git stash 대신 변경 유지 + 다음 attempt에서 추가 커밋

### main 머지 조건
| depth | 머지 전 필수 |
|---|---|
| fast | 없음 (engineer 커밋만으로 머지) |
| std | validator_b_passed |
| deep | pr_reviewer_lgtm + security_review_passed |
| bugfix | validator_b_passed (bugfix-direct 경로) |

머지: `git merge --no-ff`, 충돌 시 `MERGE_CONFLICT_ESCALATE` → 메인 Claude 보고

### 브랜치 정리
| 결과 | 처리 |
|---|---|
| HARNESS_DONE | 브랜치 삭제 |
| IMPLEMENTATION_ESCALATE | 브랜치 보존 (디버깅용) |
| MERGE_CONFLICT_ESCALATE | 브랜치 보존 |

---

## 에이전트 역할 경계

| 에이전트 | 담당 | 절대 금지 |
|----------|------|-----------|
| architect | 설계 문서 · impl 파일 작성 | src/** 수정 |
| engineer | 소스 코드 구현 | 설계 문서 수정, Agent 도구 사용 |
| validator | PASS/FAIL 판정 리포트 | 파일 수정 |
| designer | variant 3개 생성 | src/** 수정 |
| design-critic | PICK/ITERATE/ESCALATE 판정 | 파일 수정 |
| qa | 원인 분석 + 라우팅 추천 | 코드·문서 수정 |
| product-planner | PRD/TRD 작성 | 코드·설계 문서 수정 |
| test-engineer | 테스트 코드 작성 | 소스 수정 |
| pr-reviewer | 코드 품질 리뷰 | 파일 수정 |
| security-reviewer | OWASP+WebView 보안 감사 | 파일 수정 |

### 에이전트별 Write/Edit 허용 경로 매트릭스 (물리적 강제)

PreToolUse 훅 `agent-boundary.py`가 아래 매트릭스를 물리적으로 차단한다.
`{agent}_active` 플래그가 활성화된 상태에서 허용 경로 외 파일을 Write/Edit하면 deny.

| 에이전트 | 허용 경로 | 비고 |
|----------|-----------|------|
| engineer | `src/**` | 테스트 포함 |
| architect | `docs/**`, `backlog.md` | impl 파일 포함 |
| designer | `design-preview-*.html`, `docs/ui-spec*` | architecture 계열 금지 |
| test-engineer | `src/__tests__/**` | src 본체 수정 금지 |
| product-planner | `prd.md`, `trd.md` | 설계 문서 금지 |
| validator, design-critic, pr-reviewer, qa, security-reviewer | *(없음 — ReadOnly)* | 모든 Write/Edit deny |

---

## 이 파일 변경 시 함께 업데이트할 대상

| 변경 내용 | 업데이트 대상 |
|-----------|---------------|
| 루프 순서 / 조건 변경 | `harness/executor.sh`, `harness/{impl,design,bugfix,plan}.sh`, `harness/impl-process.sh`, `docs/harness-state.md` |
| 마커 추가 / 변경 | 해당 에이전트 md 파일 + 해당 루프 파일(`orchestration/*.md`) |
| 에이전트 역할 경계 변경 | 해당 에이전트 md 파일 |
| 에이전트 추가 / 삭제 | 역할 경계 표 + 해당 루프 다이어그램 + 마커 표 + 스크립트 |
| 하네스 기능 추가 / 변경 | `docs/harness-state.md` (완료/한계 섹션) + `docs/harness-backlog.md` (항목 상태) |
| architect Mode 추가/변경 | `CLAUDE.md` (프로젝트) architect 호출 규칙 표 |
