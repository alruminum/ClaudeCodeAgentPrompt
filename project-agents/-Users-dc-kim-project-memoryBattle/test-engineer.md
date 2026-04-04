## 프로젝트 특화 — 테스트 환경

- **테스트 명령어**: `package.json`의 `test` 스크립트 확인 후 사용 (`test` 스크립트가 없고 vitest도 미설치인 경우에만 `npm install vitest --save-dev` 후 `npx vitest run --reporter=verbose`)
- **테스트 파일 위치**: 구현 파일과 같은 디렉토리 또는 `src/__tests__/`
- **파일 확장자**: `*.test.ts` 또는 `*.spec.ts`

---

## 프로젝트 특화 — Mock 패턴

아래 외부 의존은 반드시 mock 처리한다:

| 의존 | Mock 방법 |
|---|---|
| `src/lib/ait.ts` (앱인토스 SDK 래퍼) | `vi.mock('../../lib/ait')` |
| `src/lib/supabase.ts` | `vi.mock('../../lib/supabase')` |
| `src/store/gameStore.ts` | `vi.mock('../../store/gameStore')` 또는 실제 store 사용 |

---

## 프로젝트 특화 — 우선 테스트 대상

복잡한 로직 위주로 테스트한다. 단순 렌더링 테스트는 우선순위 낮음.

| 모듈 유형 | 테스트 우선순위 | 테스트 대상 |
|---|---|---|
| 게임 엔진 로직 (`useGameEngine`) | 높음 | 시퀀스 생성, 입력 검증, 콤보 계산, 타이머 |
| Zustand store 액션 | 높음 | 상태 전이, 점수 계산, 리셋 |
| 랭킹/DB 훅 | 중간 | Supabase 호출 파라미터, 에러 처리 |
| UI 컴포넌트 | 낮음 | 렌더링 여부만 확인 |

---

## 프로젝트 특화 — 점수/콤보 검증

`docs/game-logic.md`의 수치를 테스트 기댓값으로 사용한다.
수치가 불명확하면 `SPEC_GAP_FOUND`로 보고한다.

---

## 프로젝트 특화 — 테스트 플랜 대조

Phase 1.5 갭 체크 시 `docs/test-plan.md`의 A/B/C/D 섹션을 모듈별로 대조한다.

| 섹션 | 대상 모듈 |
|---|---|
| A | `src/lib/gameLogic.ts` |
| B | `src/store/gameStore.ts` |
| C/D | `src/hooks/useGameEngine.ts` |

`getInputTimeout`(A-6), 타이머 통합 TC(D-1~D-5)처럼 플랜에 없는 항목은 `TEST_PLAN_GAP`으로 보고한다.
