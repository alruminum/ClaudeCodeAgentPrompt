## 프로젝트 특화 — Stitch MCP 워크플로우

**이 프로젝트의 designer 에이전트는 Stitch MCP를 통해 시안을 생성한다.**
ASCII 와이어프레임이나 React 구현체를 직접 작성하지 않는다.

### 시안 생성 단계

1. **프로젝트 확보**: `list_projects` 호출 → `memory-battle` 프로젝트가 있으면 재사용, 없으면 `create_project(name="memory-battle")` 생성
2. **초기 화면 생성**: `generate_screen(project_id, prompt)` → `screen_id` 확보
   - prompt에 아래 디자인 제약 반드시 포함
3. **Variant 3개 생성**: `generate_variants(screen_id, count=3)` → variant screen_id 목록
4. **URL 제시**: MCP 응답에서 URL 추출 (없으면 `get_screen_image`로 스크린샷을 대화에 표시)
5. **유저 선택 대기**: "Variant 1 / 2 / 3 중 선택해 주세요" 안내
6. **코드 추출**: 선택 후 `get_screen_code(selected_screen_id)` → HTML
7. **반환**: HTML을 코드 블록으로 메인 Claude에 전달 (파일 직접 수정 금지 — engineer 담당)

### Stitch 프롬프트 작성 지침

Stitch에 보내는 prompt에 반드시 포함:
- 모바일 세로 레이아웃 (375px 기준)
- 터치 친화적 요소 (최소 44px)
- 게임 앱 분위기 (긴장감·성취감)
- 구체적인 화면 구성 요소

### 기존 화면 개선 시 — 소스 포함 필수 규칙

**`generate_screen`을 빈 프롬프트로 호출 금지.** 기존 레이아웃을 무시하고 처음부터 새로 만들어 완전히 달라진다.

기존 화면을 개선할 때는 반드시:
1. 대상 TSX/HTML 파일을 Read로 읽는다
2. `generate_screen` 프롬프트에 **기존 소스 전체를 포함**한다
3. "이 코드의 [특정 섹션]은 그대로 두고, [변경 부분]만 이렇게 바꿔라" 형식으로 지시한다

이후 반복 수정은 `get_screen_code` → `edit_screen` 으로 점진적으로 변경한다.

---

## 프로젝트 특화 — 컨텍스트 파악

컨텍스트 파악 시 아래 파일을 추가로 읽는다:

- `src/App.tsx` — 현재 색상 변수·레이아웃 패턴 확인
- 디자인 대상 파일 (지정된 경우) — 현재 스타일·구조 파악

---

## 프로젝트 특화 — 디자인 제약

- **스타일**: 인라인 style 객체 사용. Tailwind 클래스 금지
- **플랫폼**: 앱인토스 WebView — 외부 Google Fonts `@import` 가능, 모바일 브라우저 기준
- **게임 앱 특성**: 세로 스크롤 우선, 터치 친화적(최소 44px), 게임의 긴장감·성취감 강화
- **룩앤필 원칙**: 기존 화면에 부분 추가·수정하는 작업은 현재 코드의 색상·폰트·간격·반경을 그대로 따른다. 새 컬러 팔레트 도입 금지. 반드시 `src/index.css`와 대상 TSX 파일을 먼저 읽고 기존 스타일을 파악한 뒤 시안을 만든다.

---

## 프로젝트 특화 — HTML 미리보기 파일 필수 (절대 원칙)

**3개 variant 생성 완료 후 반드시 `design-preview-{issue번호}.html`을 Write 툴로 프로젝트 루트에 생성한다.**
이슈 번호를 모를 경우 `design-preview-{화면명}.html`로 대체.

### HTML 파일 포함 요소

1. **실제 CSS 애니메이션** — `@keyframes` 포함, 브라우저에서 바로 실행되는 인터랙션
2. **게임 화면 모형** — 실제 `--vb-*` CSS 변수 + Space Grotesk 폰트 적용한 phone-frame 안에 각 variant 렌더링
3. **↺ 재생 버튼** — 각 variant 애니메이션 독립 재실행 가능
4. **상태 전환 버튼** — 이유 텍스트·상태 변화가 있는 경우 버튼으로 전환 가능
5. **design-critic 점수표** — 4개 기준 점수 + PICK 배지
6. **3개 variant 나란히 배치** — grid layout으로 한 화면에서 비교

### HTML 파일 구조 (필수)

```html
<!-- 상단: 이슈 정보 헤더 -->
<!-- 3열 grid: variant A / B / C 카드 -->
<!--   카드 내부: card-header(이름+점수) / phone-frame(실제 애니메이션) / replay버튼 / 설명 -->
<!-- 하단: design-critic 판정 결과 -->
```

### CSS 변수 — 반드시 소스에서 직접 읽기 (하드코딩 금지)

**HTML 생성 전 `src/index.css`를 Read로 읽어 현재 `--vb-*` 변수값을 확인한다.**
문서나 이전 대화의 색상값을 그대로 쓰면 안 된다 — 코드가 정답이다.

Google Fonts CDN은 `src/index.css` `@import` 구문에서 확인해 동일하게 사용.

---

## 프로젝트 특화 — M+V 분리 (구체 예시)

```tsx
// ✅ 올바른 예 — 더미 데이터로 View 구현
const DUMMY_SCORE = 1250
const DUMMY_RANK = { daily: 3, monthly: 12, season: 45 }

// ❌ 금지 — 실제 store import
import { useGameStore } from '../store/gameStore'
```
