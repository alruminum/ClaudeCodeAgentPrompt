## 프로젝트 특화 — Playwright 시각 검토 (HTML 미리보기 우선)

base의 심사 절차에 앞서 아래 순서로 실제 화면을 확인한다.

### 1순위: HTML 미리보기 파일 확인

```
1. Glob으로 프로젝트 루트에서 `design-preview-*.html` 검색
2. 파일 발견 시:
   a. browser_resize_window → 1200×900 (3열 grid 전체 보기)
   b. browser_navigate → `file:///절대경로/design-preview-{N}.html`
   c. browser_screenshot → 전체 화면 캡처 (3개 variant 동시 확인)
   d. browser_resize_window → 390×844 (모바일 뷰포트)
   e. 각 variant 카드 영역 스크린샷 (필요 시)
   f. 심사 완료 후 browser_close
```

### 2순위: HTML 미리보기 없는 경우 (localhost 시도)

```
1. browser_resize_window → 390×844
2. browser_navigate → http://localhost:5173
3. 접속 실패 시 → Bash로 `npm run dev &` 백그라운드 실행 후 3초 대기, 재시도
4. browser_screenshot → 현재 상태 캡처
5. 그래도 실패 시 → 코드 분석만으로 진행, 스크린샷 없음 명시
6. 심사 완료 후 browser_close
```

> **HTML 미리보기 파일이 있으면 localhost 시도 불필요.** 파일에 실제 애니메이션이 포함되어 있으므로 더 정확하게 심사 가능하다.

---

## 프로젝트 특화 — 컨텍스트 적합성 심사 기준

base의 "컨텍스트 적합성" 항목을 이 프로젝트 기준으로 적용한다:

- 앱인토스 WebView 환경 고려 (외부 폰트 로드 가능, 모바일 브라우저)
- 게임 앱의 긴장감·성취감을 디자인이 강화하는가
- 타겟 유저 (게임을 즐기는 토스 앱 유저)에게 어울리는가
