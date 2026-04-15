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
| 2026-04-15 | Second Reviewer — 외부 AI(Gemini/GPT) 병렬 리뷰 | pr-reviewer와 동시 실행, LGTM 시 findings → POLISH 합산. config.second_reviewer로 on/off. CLI 미설치 시 자동 스킵 |
| 2026-04-15 | Handoff 전 파이프라인 확장 — architect→validator→engineer→pr-reviewer | 기존 handoff는 engineer→test-engineer, SPEC_GAP만 커버. simple 모드 전체 체인에 handoff 추가. JSONL에 handoff 이벤트 로깅. harness-review.py가 handoff 유무에 따라 WASTE_DUPLICATE_READ 심각도/fix 분기 |
