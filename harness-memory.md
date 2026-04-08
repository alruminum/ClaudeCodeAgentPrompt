# Harness Memory — Global

프로젝트를 넘어 반복되는 공통 실패/성공 패턴. 모든 프로젝트의 harness/executor.sh / harness/impl-process.sh가 읽는다.

> 쓰기 금지 (에이전트 자동 기록 불가). 수동 프로모션만 허용.
> 프로젝트 로컬 `.claude/harness-memory.md`에서 공통 패턴 발견 시 직접 옮길 것.

## Known Failure Patterns (Cross-Project)
<!-- 형식: YYYY-MM-DD | 패턴 유형 | 구체적 내용 -->
- 2026-04-07 | import_path | engineer가 docs/sdk.md 확인 없이 추측으로 import 경로 작성 → 빌드 실패. MUST: .d.ts 또는 실제 소스에서 확인 후 사용
- 2026-04-07 | test_mock_drift | test-engineer가 실제 API와 다른 mock 작성 → 테스트 통과하지만 런타임 실패. MUST: 실제 함수 시그니처 확인 후 mock 작성
- 2026-04-07 | stale_impl | architect impl 파일이 설계 변경을 반영하지 않아 engineer가 구 스펙으로 구현. MUST: architect Mode C(SPEC_GAP) 후 impl 갱신 확인

## Success Patterns (Cross-Project)
<!-- 형식: YYYY-MM-DD | 패턴 유형 | 구체적 내용 -->
- 2026-04-07 | early_spec_check | engineer Phase 1에서 SPEC_GAP 조기 발견 → 루프 재시도 0회로 완료. 스펙 검토 체크리스트 완주가 핵심
- 2026-04-07 | atomic_impl | impl 파일을 파일 1~2개 단위로 쪼개면 engineer 성공률 상승. 5개 이상 파일 변경 impl은 실패율 3배
