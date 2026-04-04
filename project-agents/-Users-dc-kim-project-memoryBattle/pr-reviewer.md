## 프로젝트 특화 — 컨벤션

이 프로젝트의 확정된 컨벤션이다. 위반 시 MUST FIX.

| 규칙 | 내용 |
|---|---|
| 스타일 | 인라인 `style` 객체 사용. Tailwind 클래스 금지 |
| CSS 변수 | 색상은 `var(--vb-*)` 변수 사용. 하드코딩 hex/rgb 금지 |
| SDK | `src/lib/ait.ts` 래퍼 함수만 사용. `@apps-in-toss/web-framework` 직접 import 금지 |
| Supabase | `src/lib/supabase.ts` 클라이언트만 사용. `@supabase/supabase-js` 직접 import 금지 |
| Store | `src/store/gameStore.ts`의 공개 액션만 사용. store 내부 직접 변경 금지 |
| 샌드박스 분기 | SDK 호출 시 `IS_SANDBOX` 분기 누락 → MUST FIX |

---

## 프로젝트 특화 — 게임 로직 주석

게임 수치(점수 계산식, 속도, 콤보 배율 등)가 코드에 인라인으로 등장하면
`docs/game-logic.md` 참조 주석이 없을 경우 NICE TO HAVE로 기록한다.

---

## 프로젝트 특화 — 출력 형식

첫 줄은 반드시 `LGTM` 또는 `CHANGES_REQUESTED`로 시작한다.

```
LGTM  (또는 CHANGES_REQUESTED)

### MUST FIX
1. [파일경로:라인] 문제 — 수정 방향

### NICE TO HAVE
- [파일경로:라인] 제안

### 총평
한 줄 평가
```
