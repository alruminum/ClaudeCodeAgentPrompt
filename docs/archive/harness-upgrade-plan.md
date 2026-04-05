# 하네스 엔지니어링 고도화 플랜 — 1인 개발자 슬림 버전

> 작성일: 2026-04-05  
> 소스: Ben Shoemaker / Heidenstedt / Addy Osmani / OpenAI Harness / Optio

## Context

5개 소스 대조 결과, 현재 4기둥(컨텍스트·게이트·도구경계·피드백)은 갖춰져 있으나 **검증 명확성**에서 다음 단계 여지가 있다.

1인 개발자 + 토큰 예산 제약 → ROI 높은 3개만 구현, 나머지는 DROP.

---

## 오버엔지니어링 DROP 목록

| Gap | 드롭 이유 |
|---|---|
| G1 크로스모델 리뷰 | 매 PR 토큰 2배. pr-reviewer 이미 충분 |
| G4 커스텀 린트 | harness-lint.sh 제작 비용 큼. post-commit-scan.sh로 충분 |
| G5 GC 에이전트 | 단일 게임앱에서 jscpd·knip 주기 점검 부담 대비 효용 낮음 |
| G6 PR 계약 | 리뷰어가 나 혼자. 구조화 포맷 실익 없음 |
| G8 Git Worktree | 3회 루프에서 worktree 관리 복잡성 대비 실익 없음 |
| G9 관측성 대시보드 | /tmp 로그 + 터미널 충분. 팀 규모 불일치 |
| G10 Doc-Gardening | architect가 이미 처리 |
| G11 뮤테이션 테스트 | 토큰·시간 비용 큼. UI 게임 로직에서 실익 불분명 |

---

## 구현 대상 — 3개

### G3. 수용 기준 메타데이터 (최우선)

**왜**: impl 파일에 섹션 하나 추가만으로 "무엇을 어떻게 검증할지"가 명확해짐. 후속 G2·G7의 전제조건.

**태그 의미**:
- `(TEST)` — vitest 자동 테스트
- `(BROWSER:DOM)` — Playwright로 DOM 요소 존재/속성 쿼리 (스크린샷 아님)
- `(MANUAL)` — 마지막 수단. curl·bash 자동 체크 먼저 시도

**Audit 원칙**: 메타데이터 없는 태스크 = validator가 SPEC_GAP 반려 (작업 전 차단)

**요구사항 ID**: `[REQ-NNN]` 형식으로 prd.md 항목 → impl 태스크 → 테스트 추적 가능하게

**변경 파일**:
- `~/.claude/agents/architect.md` — impl 파일에 `## 수용 기준` 섹션 + 태그 필수화
- `~/.claude/agents/validator.md` — Plan Validation 시 메타데이터 미존재 태스크 SPEC_GAP 반려
- `~/.claude/orchestration-rules.md` — "메타데이터 없는 태스크 = 구현 진입 불가" 정책 추가

---

### G2. 커버리지 게이트 (조건부 완화)

**왜**: 테스트 없는 구현 병합 방지. 단, 70% 전체 강제는 UI 게임 앱에 비현실적.

**완화 조건**: 신규 추가 파일(git diff --name-only) 기준 60%, 기존 파일은 게이트 제외.

**변경 파일**:
- `~/.claude/harness-loop.sh` — `vitest run --coverage` 추가, 신규 파일 커버리지 파싱, `coverage_fail` 유형

---

### G7. BROWSER:DOM 자동 검증 (opt-in)

**왜**: UI 게임 앱에서 DOM 검증은 가치 있음. 단 기본 비활성 — `(BROWSER:DOM)` 태그 있을 때만 실행.

**동작**:
1. `grep -c "(BROWSER:DOM)" "$IMPL_FILE"` → 0이면 스텝 스킵
2. 태그 있으면 dev server 띄우고 `claude --agent design-critic` 으로 DOM 쿼리 검증
3. `browser_fail` → engineer에게 DOM 수정 지시

**변경 파일**:
- `~/.claude/harness-loop.sh` — BROWSER:DOM 감지 + 조건부 브라우저 스텝, `browser_fail` 유형

---

## 구현 순서

```
1. G3 (architect.md + validator.md + orchestration-rules.md) — 규칙 변경만, 스크립트 없음
2. G2 (harness-loop.sh) — vitest --coverage 파싱 추가
3. G7 (harness-loop.sh) — BROWSER:DOM 조건부 스텝 추가
```

---

## 변경 대상 파일 요약

| 파일 | 작업 |
|---|---|
| `~/.claude/agents/architect.md` | `## 수용 기준` 섹션 + [REQ-NNN] + (TEST/BROWSER:DOM/MANUAL) 필수화 |
| `~/.claude/agents/validator.md` | Plan Validation에 메타데이터 검증 + SPEC_GAP 반려 규칙 |
| `~/.claude/orchestration-rules.md` | "메타데이터 없는 태스크 = 구현 진입 불가" 정책, G2/G7 단계 추가 |
| `~/.claude/harness-loop.sh` | vitest --coverage (신규파일 60%), BROWSER:DOM 조건부 스텝 |

---

## 소스 참고

| # | 소스 | 채택한 인사이트 |
|---|---|---|
| 1 | Ben Shoemaker | (TEST)/(BROWSER:DOM)/(MANUAL) 태그 체계 |
| 2 | Heidenstedt | 엄격한 린팅 → post-commit-scan.sh로 이미 커버 |
| 3 | Addy Osmani | 커버리지 게이트 개념 → 완화 적용 |
| 4 | OpenAI Harness | 에이전트 친화 에러 메시지 → fail_type 분기로 이미 구현 |
| 5 | Optio | 대시보드 패턴 참고 → P2 이후 재검토 |

---

## 검증

```bash
# G3: impl 파일 메타데이터 존재 확인
grep -l "(TEST)\|(BROWSER:DOM)\|(MANUAL)" docs/milestones/v03/epics/*/impl/*.md

# G2: 커버리지 dry-run
npx vitest run --coverage 2>&1 | tail -5

# G7: BROWSER:DOM 태그 감지 테스트
grep "(BROWSER:DOM)" docs/milestones/v03/epics/epic-11-ui-improvements/impl/*.md || echo "no BROWSER:DOM tags yet"
```
