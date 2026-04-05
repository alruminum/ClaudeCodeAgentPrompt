# 하네스 고도화 백로그 — 보류 항목

> 1인 개발자 기준 현재 건너뛴 항목들. 팀 규모 증가·프로젝트 성숙 시 재검토.
> 최종 업데이트: 2026-04-05

---

## 완료 항목 ✅

| 항목 | 설명 | 완료일 |
|---|---|---|
| **G3 수용 기준 메타데이터** | impl 파일 `## 수용 기준` 필수화, (TEST)/(BROWSER:DOM)/(MANUAL) 태그, validator SPEC_GAP 반려 | 2026-04-05 |
| **G6 PR 계약 프레임워크** | HARNESS_DONE 후 `/tmp/{prefix}_pr_body.txt` 자동 생성 (What/Why/증거/위험/포커스) | 2026-04-05 |
| **G10 Doc-Gardening** | `/doc-garden` 커맨드 — 문서-코드 불일치 리포트 (수동 트리거, 자동 수정 없음) | 2026-04-05 |

---

## 보류 — SLIM 플랜 스킵 항목

### G2. 커버리지 게이트 (신규 파일 60%)

**재검토 조건**: test-engineer가 너무 얕은 테스트만 반복 작성할 때

**왜 보류**: Phase 1(수용 기준)으로 test-engineer 품질이 올라가면 coverage 게이트 불필요. bash에서 JSON 파싱 + 신규 파일 필터링 로직이 fragile.

**구현 위치**: `~/.claude/harness-loop.sh`
```bash
# vitest run → vitest run --coverage
# 신규 파일 필터: git diff HEAD~1 HEAD --name-only --diff-filter=A
# coverage_fail 분기 추가
```

**선행 작업**: `npm install -D @vitest/coverage-v8` + `vite.config.ts` coverage 섹션 추가

---

### G7. BROWSER:DOM 자동 검증 (opt-in)

**재검토 조건**: UI 버그가 vitest로 잡히지 않고 반복 발생할 때

**왜 보류**: 루프마다 dev server + Playwright = 30~60초 추가. design-critic이 디자인 루프에서 이미 Playwright 사용 중 → 중복.

**구현 위치**: `~/.claude/harness-loop.sh` (test-engineer 완료 후, validator 호출 전)
```bash
if grep -qc "(BROWSER:DOM)" "$IMPL_FILE"; then
  npm run dev &
  DEV_PID=$!
  # design-critic 에이전트 호출 (DOM 검증 모드)
  kill $DEV_PID
fi
```

**선행 작업**: architect.md에 UI 태스크 = (BROWSER:DOM) 태그 필수 규칙 추가 (현재 미정의)

---

## 보류 — MEDIUM 플랜 스킵 항목

### G1. 크로스모델 리뷰 (보안 파일에만)

**재검토 조건**: auth/api/db 파일에서 보안 사고가 발생했을 때, 또는 팀이 2인 이상이 될 때

**왜 보류**: `security-reviewer` 에이전트가 이미 존재 → 역할 중복. 토큰 비용 추가.

**구현 위치**: `~/.claude/harness-loop.sh` (security-reviewer 이후)
```bash
security_files=$(git diff --name-only HEAD | grep -E 'auth|api|token|password|secret|db' || echo "")
if [[ -n "$security_files" ]]; then
  # Haiku 모델로 2nd opinion 요청
fi
```

---

### G4. 커스텀 린트 (sonarjs + import 정렬)

**재검토 조건**: 코드베이스가 10개 파일 이상으로 커지고 중복 로직이 자주 등장할 때

**왜 보류**: 소규모 코드베이스에서 sonarjs false positive 많음. pr-reviewer가 이미 중복 로직 지적.

**구현 위치**: `.eslintrc` + `harness-loop.sh` lint 단계 추가

---

### G5. GC 에이전트 (월 1회 dead code 스캔)

**재검토 조건**: 에픽 5개 이상 완료 후 dead code가 쌓였다고 느껴질 때

**왜 보류**: 단일 앱에서 jscpd·knip 실익이 낮음. 수동 확인으로 충분.

**구현 형태**: `/scan` 커맨드 (리포트만, 자동 PR 없음)

---

### G9. 관측성 로그 (파일 기반)

**재검토 조건**: 프로덕션 트래픽이 생기고 버그 재현이 어려워질 때

**왜 보류**: `/tmp` 로그로 현재 충분. 트래픽 없는 미니앱에서 오버엔지니어링.

**구현 형태**: Optio 패턴 참고, `/tmp/{prefix}_observability/` 파일 로그 (Grafana 확장 가능 구조)

---

### G8. Git Worktree 격리

**재검토 조건**: 브랜치 전략이 생기거나 팀 병렬 개발이 시작될 때

**왜 보류**: 1인 개발에서 feature branch가 없으면 불필요.

---

### G11. 뮤테이션 테스트

**재검토 조건**: 테스트 신뢰도 문제가 반복되고 토큰 예산이 넉넉할 때

**왜 보류**: 토큰·시간 비용 대비 일반 서비스 코드에서 실익 불분명.

---

## 재검토 트리거 요약

| 상황 | 재검토 항목 |
|---|---|
| test-engineer 테스트 품질 반복 하락 | G2 (coverage gate) |
| UI 버그가 vitest 통과 후 발견 반복 | G7 (BROWSER:DOM) |
| 보안 사고 또는 팀 합류 | G1 (크로스모델 리뷰) |
| 코드베이스 10개 파일 이상 + 중복 반복 | G4 (커스텀 린트) |
| 에픽 5개 완료 후 dead code 체감 | G5 (GC 에이전트) |
| 프로덕션 트래픽 발생 | G9 (관측성 로그) |
