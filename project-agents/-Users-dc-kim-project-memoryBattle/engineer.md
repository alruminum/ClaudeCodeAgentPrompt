## 프로젝트 특화 — 스펙 갭 체크리스트 추가 항목

base의 SPEC_GAP 체크리스트에 아래 항목을 추가로 확인한다:

- 의존 모듈의 실제 인터페이스가 계획의 가정과 다른 경우
  (예: 계획은 `error` 필드를 가정했지만 실제 훅에 없는 경우)
- 두 모듈이 같은 함수명을 다른 의미로 사용하는 경우
  (예: `GameStore.startGame` vs `useGameEngine.startGame`)
- 페이지 전환 시점과 상태 초기화 순서가 명시되지 않은 경우
- 컴포넌트 간 데이터 흐름(props 전달 경로)이 불명확한 경우

---

## Stitch 시안 반영 규칙

메인 Claude가 Stitch screen ID를 전달하면:
1. `mcp__stitch__get_screen_code(projectId, screenId)`로 직접 HTML 추출
2. Stitch HTML의 Tailwind 클래스 → 프로젝트 인라인 style 객체로 변환
3. 색상 매핑: `text-primary-container` → `var(--vb-accent)`, `text-on-surface` → `var(--vb-text)`, `text-on-surface-variant` → `var(--vb-text-dim)`, `bg-surface-container-lowest` → `var(--vb-surface)`, `border-outline-variant` → `var(--vb-border)`, `font-headline` → `var(--vb-font-score)`
4. "건드리지 말 것" 명시된 섹션은 Stitch HTML 무시하고 기존 코드 유지

---

## 프로젝트 특화 — 구현 규칙

- **SDK**: `src/lib/ait.ts` 래퍼 함수만 사용. 직접 import 금지
- **Supabase**: `src/lib/supabase.ts` 클라이언트만 사용
- **전역 상태**: `src/store/gameStore.ts`의 기존 액션만 사용. store 수정 필요 시 보고 후 대기
- **스타일**: 인라인 style 객체로 작성 (Tailwind 미사용, CSS variables 사용)
- **샌드박스 분기**: `IS_SANDBOX` 플래그(`src/lib/ait.ts` 참조)가 필요한 경우 적용
