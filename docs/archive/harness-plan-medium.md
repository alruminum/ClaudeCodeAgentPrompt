# 하네스 엔지니어링 고도화 플랜 — MEDIUM (팀 3~10인 서비스)

> 대상: 팀 3~10인, PR 리뷰어 복수, 토큰 예산 보통
> 소스: Ben Shoemaker / Heidenstedt / Addy Osmani / OpenAI Harness / Optio

---

## 현재 완료 베이스라인 ✅

Full 플랜과 동일 (harness-loop.sh, agent-boundary.py, security-reviewer 등)

---

## Phase 1 — 검증 강화 (G3·G2·G7)

### G3. 수용 기준 메타데이터 + 스펙 기반 워크플로우

Full과 동일. 팀에서 가장 가치 높음 — 에이전트 산출물에 대한 팀 합의 기준이 됨.

**태그 체계**:
- `(TEST)` — vitest 자동 테스트
- `(BROWSER:DOM)` — Playwright DOM 요소 쿼리
- `(MANUAL)` — curl·bash 먼저 시도 후 불가능할 때만

**Audit**: 메타데이터 없는 태스크 → validator SPEC_GAP 반려

변경 파일: `architect.md` + `validator.md` + `orchestration-rules.md`

### G2. 커버리지 게이트 (신규 파일 70%)

신규 추가 파일 기준 70%. 기존 레거시 파일은 게이트 제외 (기술부채 분리).

변경 파일: `harness-loop.sh` — `vitest run --coverage`, 신규 파일 필터링 + `coverage_fail`

### G7. BROWSER:DOM 자동 검증 (opt-in)

`(BROWSER:DOM)` 태그 있을 때만 실행. UI 변경 PR에서 자동 활성.

변경 파일: `harness-loop.sh` — 조건부 브라우저 스텝, `browser_fail`

> **G1 크로스모델 리뷰 — Phase 1 제외**: 팀에 pr-reviewer + 인간 리뷰어가 있으면
> 추가 모델 리뷰 비용 대비 실익 낮음. Phase 2로 이동.

---

## Phase 2 — 자동화 확장 (G6·G4·G1)

### G6. PR 계약 프레임워크

팀 리뷰어가 있으므로 구조화 PR 포맷이 실질적으로 유용.

```
## What/Why (1-2문장)
## 작동 증거 (테스트 결과)
## 위험 + AI 역할 (HIGH/MEDIUM/LOW)
## 리뷰 포커스
```

변경 파일: `harness-loop.sh` — PR 본문 생성 포맷 적용

### G4. 커스텀 린트 (표준 규칙만)

전체 커스텀 규칙 대신 eslint-plugin-sonarjs + import 정렬만. 에이전트 친화 에러 메시지 포함.

변경 파일: `.eslintrc` 업데이트 + `harness-loop.sh` lint 단계 추가

### G1. 크로스모델 리뷰 (보안 코드에만 적용)

보안 관련 파일(auth, api, db) 변경 시에만 Haiku 세컨드 오피니언. 전체 PR에는 미적용.

변경 파일: `harness-loop.sh` — 보안 파일 감지 조건부 크로스리뷰

---

## Phase 3 — 장기 발전 (G5·G9·G10)

### G5. GC 에이전트 (월 1회 트리거)

cron 또는 `/scan` 수동 커맨드. 자동 PR 생성은 없고 리포트만. 팀이 PR 여부 결정.

### G9. 관측성 로그 (대시보드 없음)

Optio 패턴 참고. Web UI 없이 `/tmp/{prefix}_observability/` 파일 로그만.
팀이 필요 시 Grafana 연동 확장 가능한 구조로 저장.

### G10. Doc-Gardening (수동 트리거)

`/doc-garden` 커맨드. 자동 PR은 없고 불일치 리포트만. 팀 검토 후 수동 반영.

> **G8 Worktree, G11 뮤테이션 테스트 — DROP**
> G8: 팀 브랜치 전략(feature branch)으로 이미 격리됨
> G11: 토큰·시간 비용 대비 일반 서비스 코드에서 실익 불분명

---

## 파일 변경 전체 목록

| 파일 | Phase | 작업 |
|---|---|---|
| `orchestration-rules.md` | 1 | G3 정책 + G2/G7 단계 |
| `architect.md` | 1 | 수용 기준 섹션 필수화 |
| `validator.md` | 1 | SPEC_GAP 반려 |
| `harness-loop.sh` | 1-2 | coverage/browser/PR포맷/lint/보안크로스리뷰 |
| `.eslintrc` | 2 | sonarjs + import 규칙 |
| `skills/scan.md` | 3 | 리포트 전용 GC 스킬 |

---

## G1 크로스모델 리뷰 적용 기준 (Medium 특화)

```bash
# 보안 파일 감지 예시
security_files=$(git diff --name-only HEAD | grep -E 'auth|api|token|password|secret|db' || echo "")
if [[ -n "$security_files" ]]; then
  # 크로스모델 리뷰 실행
fi
```
