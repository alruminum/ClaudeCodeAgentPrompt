# 하네스 엔지니어링 고도화 플랜 — SLIM (1인 개발자)

> 대상: 1인 개발자, 토큰 예산 제약, 게임/연습용 프로젝트
> 소스: Ben Shoemaker / Addy Osmani

---

## 현재 완료 베이스라인 ✅

Full 플랜과 동일 (harness-loop.sh, agent-boundary.py, security-reviewer 등)

---

## DROP 목록 (오버엔지니어링)

| Gap | 드롭 이유 |
|---|---|
| G1 크로스모델 리뷰 | 매 PR 토큰 2배. pr-reviewer 충분 |
| G4 커스텀 린트 | 제작 비용 큼. post-commit-scan.sh 충분 |
| G5 GC 에이전트 | 단일 앱에서 jscpd·knip 부담 대비 효용 낮음 |
| G6 PR 계약 | 리뷰어 혼자. 구조화 포맷 실익 없음 |
| G8 Git Worktree | 복잡성 대비 실익 없음 |
| G9 관측성 대시보드 | /tmp 로그 충분 |
| G10 Doc-Gardening | architect가 처리 |
| G11 뮤테이션 테스트 | 토큰·시간 비용 큼 |

---

## Phase 1 — 규칙 변경 (G3)

### G3. 수용 기준 메타데이터

스크립트 변경 없이 규칙 파일만 수정. 비용 거의 0.

**태그 의미**:
- `(TEST)` — vitest 자동 테스트
- `(BROWSER:DOM)` — Playwright DOM 요소 쿼리 (스크린샷 아님)
- `(MANUAL)` — curl·bash 먼저 시도 후 불가능할 때만

**Audit**: validator가 메타데이터 없는 태스크 → SPEC_GAP 반려 (작업 전 차단)

변경 파일:
- `~/.claude/agents/architect.md` — `## 수용 기준` + `[REQ-NNN]` 필수화
- `~/.claude/agents/validator.md` — SPEC_GAP 반려 규칙
- `~/.claude/orchestration-rules.md` — "메타데이터 없는 태스크 = 구현 진입 불가" 정책

---

## Phase 2 — 스크립트 수정 (G2)

### G2. 커버리지 게이트 (신규 파일 60%)

신규 추가 파일만 60% 기준. 기존 파일 제외.
UI 게임 앱에서 전체 70% 강제는 trivial 테스트 양산 → 비현실적.

변경 파일:
- `~/.claude/harness-loop.sh` — `vitest run --coverage`, 신규 파일 필터링, `coverage_fail`

---

## Phase 3 — 선택적 확장 (G7)

### G7. BROWSER:DOM 자동 검증 (opt-in)

기본 비활성. `(BROWSER:DOM)` 태그 있을 때만 실행.
impl 파일에 태그 달기 시작하면 자동으로 활성화됨.

변경 파일:
- `~/.claude/harness-loop.sh` — `grep "(BROWSER:DOM)"` 감지 + 조건부 Playwright 스텝, `browser_fail`

---

## 파일 변경 전체 목록

| 파일 | Phase | 작업 |
|---|---|---|
| `~/.claude/agents/architect.md` | 1 | 수용 기준 섹션 + REQ-ID + 태그 필수화 |
| `~/.claude/agents/validator.md` | 1 | SPEC_GAP 반려 규칙 |
| `~/.claude/orchestration-rules.md` | 1 | "메타데이터 없는 태스크 = 구현 진입 불가" |
| `~/.claude/harness-loop.sh` | 2-3 | vitest --coverage + BROWSER:DOM 스텝 |

---

## 검증

```bash
# Phase 1 완료 확인
grep -l "수용 기준" ~/.claude/agents/architect.md

# Phase 2 완료 확인
npx vitest run --coverage 2>&1 | tail -5

# Phase 3 완료 확인 (태그 없으면 스킵 확인)
grep "(BROWSER:DOM)" docs/milestones/v03/epics/*/impl/*.md || echo "no tags — browser step skipped"
```
