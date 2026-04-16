# 오케스트레이션 변경 로그

시간순 변경 이력. 규칙 변경 시 엔트리 추가.

| 날짜 | 변경 | 이유 |
|------|------|------|
| 2026-04-11 | 카탈로그 + 분산 상세 재구성 | 428줄 단일 파일 → 카탈로그 ~70줄 + 상세 6개 파일. 진입 장벽 감소 |
| 2026-04-11 | 정책 번호 재정렬 (1~21) | 추가 순서로 꼬인 번호(9a→9→10→12→14→11→15…)를 논리적 그룹별 순차로 정리 |
| 2026-04-11 | `parse_marker()` BSD grep 버그픽스 — `grep -oEm1` → `grep -oEm1 -e` | macOS BSD grep이 `---MARKER:...` 패턴을 long option으로 오인 → 1차 마커 검출 실패 → 2차 fallback에서 본문 속 "FAIL" 단어 오탐. `-e` 플래그로 패턴 명시 |
| 2026-04-11 | `impl.sh` PLAN_VALIDATION_PASS 후 직접 dispatch | 기존: exit 0 → 플래그 재진입 → engineer. 플래그 영속성 버그로 재진입 실패 반복. 변경: validation PASS → engineer 루프 직접 진입 (재호출 불필요) |
| 2026-04-11 | `harness-review.py` EXPECTED_SEQUENCE에 `simple` 키 추가 | depth=simple에서 test-engineer/validator 스킵은 정상인데 MISSING_PHASE로 오탐 |
| 2026-04-15 | UI 디자인 게이트: 키워드 스캔 → opt-in frontmatter(`design: required`) 전환 | impl 텍스트에 "컴포넌트/디자인" 등 포함 시 무조건 UI_DESIGN_REQUIRED 트리거 → dead code 삭제 같은 비시각적 작업도 차단. "스크린샷이 달라지는가?"는 단어로 판단 불가하므로 명시적 opt-in으로 전환 |
| 2026-04-15 | `agent-boundaries.md`에 인프라 파일 접근 금지 규칙 추가 | engineer, pr-reviewer의 WASTE_INFRA_READ 반복 — `.claude/harness-*` 경로 Read/Glob 금지 명시 |
| 2026-04-15 | 모호성 정량화 (product-plan 스킬 + CLARITY_INSUFFICIENT 마커) | OMC deep-interview 참고. 5차원 모호성 점수 + 라운드 기반 인터뷰 + product-planner 에스컬레이션 |
| 2026-04-15 | Handoff 문서 패턴 (generate_handoff + write_handoff + explore_instruction 확장) | OMC handoff 참고. 에이전트 간 구조화된 인수인계 자동 생성. 에이전트 프롬프트 변경 없음 |
| 2026-04-15 | HUD Statusline (HUD 클래스 + hud.json + harness-monitor 전용 세션) | 진행 바 시각화 + 별도 세션 실시간 모니터링. Osmani 기사 참고 |
| 2026-04-15 | POLISH 모드 (@MODE:ENGINEER:POLISH + regression revert) | pr-reviewer LGTM 후 NICE TO HAVE 경량 정리. regression 실패 시 revert. OMC ai-slop-cleaner 참고 |
| 2026-04-15 | Circuit Breaker (시간 윈도우 120초 내 동일 fail_type 2회 → 조기 에스컬레이션) | harness_framework 참고. 기존 max 3 attempts와 독립 동작 |
| 2026-04-15 | `impl_loop.py` fallback import 블록에 `HUD`, `generate_handoff`, `write_handoff` 누락 수정 | `except ImportError` 경로에서 HUD 미import → `NameError: name 'HUD' is not defined` 크래시. try 블록과 동기화 |
| 2026-04-15 | `core.py` HUD.cleanup() 삭제 대신 완료 상태 기록으로 변경 | cleanup()이 HARNESS_DONE 직전에 hud.json 삭제 → harness-monitor가 최종 상태를 못 읽음. 삭제 대신 `status: "done"` 기록 후 파일 유지 |
| 2026-04-15 | Second Reviewer v1 → v3 전환 — 파일별 분할 + providers.py 어댑터 | v1(전체 diff stdin, 타임아웃)을 제거. v3: 파일별 patch + threading 병렬 + 2단계 프롬프트(NEED_FULL_FILE). providers.py에 BaseProvider/GeminiProvider 어댑터 패턴 |
| 2026-04-15 | Handoff 전 파이프라인 확장 — architect→validator→engineer→pr-reviewer | 기존 handoff는 engineer→test-engineer, SPEC_GAP만 커버. simple 모드 전체 체인에 handoff 추가. JSONL에 handoff 이벤트 로깅. harness-review.py가 handoff 유무에 따라 WASTE_DUPLICATE_READ 심각도/fix 분기 |
| 2026-04-15 | HUD 전체 라이프사이클 커버 — run_impl() 진입 시 생성 | 기존: run_simple/run_std 내부에서만 HUD 생성 → architect/plan-validation 사각지대. 변경: run_impl()에서 depth="auto"로 HUD 생성, preamble(architect+plan-validation) 포함, set_depth()로 depth별 에이전트 확장. run_simple/run_std/run_deep에 hud 파라미터 전달 |
| 2026-04-15 | `core.py` agent_call() active 플래그 경로 `/tmp/` → `state_dir`로 수정 | 훅(agent-boundary/issue-gate)은 `.claude/harness-state/`에서 탐색, agent_call은 `/tmp/`에 생성 → 경로 불일치로 에이전트를 메인 Claude로 오판 → src/** Edit·이슈 생성 차단 |
| 2026-04-15 | `harness-review.py` INFRA_EXCLUSIONS에 `handoff` 추가 | handoff 파일은 에이전트 간 인수인계 문서로 의도된 Read인데 `.claude/` 경로 포함으로 WASTE_INFRA_READ 오탐 |
| 2026-04-15 | HUD `_write_json` 진단 강화 + fallback 경로 | `_hud_path`가 None일 때 cwd 기반 fallback 추론, `except OSError: pass` → 에러 메시지 출력, 첫 agent_start 시 one-time 진단 로그 |
| 2026-04-15 | `harness-router.py` 대폭 간소화 — 7카테고리 → 3카테고리(BUG/UI/IMPL) | Haiku 폴백 90% 타임아웃, Adaptive Interview 0.2% 성공률, GREETING/QUESTION/GENERIC/AMBIGUOUS 전부 동일 동작(sys.exit). Haiku·Interview·extract_intent·socrates 에이전트 전부 제거. 스킬(/qa /ux /product-plan)이 정밀 라우팅 담당 |
| 2026-04-15 | QA 에이전트에 `update_issue`+`add_issue_comment` 도구 추가 + `issue-gate.py`에 update_issue 차단 추가 | 메인 Claude가 이슈 수정(edit)도 직접 하면 안 됨. QA/designer 에이전트만 이슈 생성+수정 가능. #106에서 메인이 직접 edit해서 요구사항 왜곡 3회 발생 |
| 2026-04-15 | QA 이슈 본문에 유저 원문 인용 필수 | #106에서 architect가 QA 요약을 과잉 해석하여 3회 재작업. 유저 원문이 이슈 → impl → engineer까지 전달되면 architect의 자체 해석 방지 |
| 2026-04-15 | `plan_loop.py` product-planner 타임아웃 300s → 600s | MCP 문서 검색(apps-in-toss)에 시간 소모되어 PRD 작성 전 타임아웃. 코인 시스템 기획에서 발생 |
| 2026-04-15 | Marker Safety 규칙 추가 — UNKNOWN 마커 시 진행 금지 | product-planner가 마커 없이 Q1/Q2 질문 → UNKNOWN → plan_loop가 architect까지 폭주. 전체 parse_marker 감사 후 진행 게이트 4곳 수정: plan_loop(pp/arch_sd/arch_mp) + impl_router(arch). orchestration-rules.md에 Marker Safety 원칙 추가, product-planner.md에 마커 필수 경고 추가 |
| 2026-04-15 | Plan 루프 HUD 추가 + 로그 보강 | plan_loop.py에 HUD 없어서 진행 상태 파악 불가. HUD depth="plan" 추가 (agents: product-planner→architect-sd→design-validation→architect-mp→plan-validation). 각 단계 마커 결과를 `[HARNESS] agent → MARKER` 형식으로 출력 |
| 2026-04-15 | drift-check에 스크립트→orchestration 상세 문서 역매핑 추가 | plan_loop.py 변경 시 orchestration/plan.md 동기화 누락 방지 |
| 2026-04-15 | plan_loop architect에 pp_out 전문 대신 prd.md 경로만 전달 | architect가 pp_out(수만 토큰)을 prd.md로 다시 쓰려고 Bash heredoc 루프에 빠져 900초 타임아웃. 경로만 넘기고 Read하게 변경 |
| 2026-04-15 | plan 루프 전면 타임아웃 조정 + 도구 차단 | Bash 20분 < plan loop 50분(worst case) 문제. product-plan 스킬에 timeout 3600000(60분) 명시. architect-sd/mp 900s→600s. agent_call에 에이전트별 disallowedTools 추가 (product-planner: Bash 차단, validator/pr-reviewer/critic: Bash+Write+Edit 차단) |
| 2026-04-16 | plan_loop architect-mp: design_doc 오탐 수정 + module 파라미터 + TASK_DECOMPOSE 분기 | 1) design_doc regex가 docs/sdk.md를 먼저 매칭 → architecture*.md 우선 매칭으로 변경. 2) MODULE_PLAN에 module 파라미터 누락 → stories.md에서 추출. 3) stories.md impl 3개 이상이면 TASK_DECOMPOSE로 자동 분기 |
| 2026-04-16 | 하네스 26개 항목 일괄 개선 (Ralph 10회) | FIX 9건: plan 체크포인트(prd/architecture 스킵), plan 메타데이터 저장, std/deep pr-reviewer handoff, test-engineer handoff 경로, SPEC_GAP 마커 기반 추출, validator handoff, kill_check rework, watchdog stdout.close, merge checkout 체크. SKIP 14건(의도적/오탐). DEFER 4건. |
| 2026-04-16 | PR 워크플로우 전면 재구성: 매 커밋 push + PR 자동 생성 + squash merge | push_and_ensure_pr() 신규, merge_to_main() --squash 전환, impl_loop 7곳에 push 추가 |
| 2026-04-16 | 브랜치 전략: 로컬 merge → GitHub PR 경유로 전환 | feature branch를 remote에 push → gh pr create → gh pr merge. branch 이력이 GitHub에 남고 PR로 변경 추적 가능. merge_to_main() 전면 재작성. simple depth도 LGTM 게이트에 포함 |
| 2026-04-16 | 실전 10회 로그 기반 버그 6건 수정 | A) POLISH revert `git reset --hard` → 선택적 파일 복원으로 merge conflict 해소. B) automated_checks no_changes → `git diff main..HEAD` 커밋 변경 감지 추가. D) architect module-plan TS 타입 체크리스트 추가. E) automated_checks에 lint_command 실행 추가. F) pr-reviewer 240s→360s. C) DEFER(에이전트 판단). WASTE_INFRA_READ: handoff 추가로 자연 해소. |
