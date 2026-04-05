---
description: 문서-코드 불일치 리포트. docs/**와 src/**를 비교해 드리프트 항목을 탐지한다. 자동 수정 없음 — 리포트만 출력.
argument-hint: "[--scope game-logic|ui-spec|db|all]"
---

# /doc-garden

문서와 코드 사이의 드리프트를 탐지하고 리포트를 출력한다. **어떤 파일도 수정하지 않는다.**

**요청 스코프:** $ARGUMENTS (없으면 all)

---

## 실행 순서

### Step 1 — 스코프 결정

`$ARGUMENTS`가 없거나 `all`이면 아래 전체 매핑 테이블을 검사한다.
특정 스코프가 명시되면 해당 행만 검사한다.

### Step 2 — 탐지 대상 매핑

| 스코프 | 문서 | 비교 대상 소스 |
|---|---|---|
| `game-logic` | `docs/game-logic.md` | `src/store/**`, `src/engine/**`, `src/hooks/**` |
| `ui-spec` | `docs/ui-spec.md` | `src/components/**`, `src/pages/**` |
| `db` | `docs/db-schema.md` | `src/types/supabase.ts`, `supabase/migrations/**` |
| `sdk` | `docs/sdk.md` | `src/lib/**`, `src/utils/**` |
| `arch` | `docs/architecture.md` | 실제 디렉토리 구조 (`src/**`) |
| `claude-md` | `CLAUDE.md` impl 표 | impl 파일 경로 실재 여부 |

### Step 3 — 탐지 실행

각 문서를 Read로 읽고, 해당 소스 파일을 Glob/Grep/Read로 확인한다.

탐지 기준:
1. **삭제된 항목이 문서에 남은 경우** — 문서의 함수명·상수·컴포넌트명이 소스에서 grep 결과 없음
2. **수치 불일치** — 문서의 숫자 상수(타이머, 배율 등)가 소스의 실제 값과 다름
3. **신규 항목이 문서에 없는 경우** — 소스에서 export된 함수·타입이 문서에 언급 없음
4. **경로 불일치** — CLAUDE.md의 impl 파일 경로가 실제로 존재하지 않음
5. **섹션 누락** — 문서의 섹션 제목이 있으나 내용이 비어있거나 "TODO"로 남은 경우

### Step 4 — 리포트 출력

아래 형식으로 출력한다.

```
## Doc-Garden 리포트 — [오늘 날짜]

### 불일치 항목 (즉시 업데이트 권장)
| 문서 | 섹션 | 소스 위치 | 불일치 내용 |
|---|---|---|---|
| docs/game-logic.md | 콤보 배율 | src/store/gameStore.ts:42 | 문서: ×5, 코드: ×4 |

### 소스에서 삭제됐으나 문서에 남은 항목
| 문서 | 항목명 |
|---|---|

### 소스에 새로 생겼으나 문서에 없는 항목
| 소스 파일 | 항목명 |
|---|---|

### 경로 불일치 (CLAUDE.md)
| impl 표 경로 | 상태 |
|---|---|

### 정상 확인 (드리프트 없음)
- [확인된 문서 목록]

---
총 불일치: N건 / 확인 문서: N개
architect에게 위임 권장 항목: [목록 또는 "없음"]
```

---

## 주의

- **파일 수정 금지** — 리포트만 출력. 자동 수정, 자동 commit 없음.
- 불일치 수정이 필요하면 architect에게 해당 문서 업데이트 위임.
- 소스가 없는 프로젝트(백엔드·외부 서비스 의존)는 "확인 불가" 로 표기.
