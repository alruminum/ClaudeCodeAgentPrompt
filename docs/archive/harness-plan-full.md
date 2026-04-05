# 하네스 엔지니어링 고도화 플랜 — FULL (엔터프라이즈/팀 10+)

> 대상: 팀 10인 이상, CI/CD 완비, 토큰 예산 여유 있는 서비스
> 소스: Ben Shoemaker / Heidenstedt / Addy Osmani / OpenAI Harness / Optio

---

## 현재 완료 베이스라인 ✅

| 항목 | 구현 |
|---|---|
| 결정론적 게이트 | harness-executor.sh + harness-loop.sh |
| 플래그 기반 상태머신 | /tmp/{prefix}_{flag} 10+개 |
| Ground truth 테스트 | npx vitest run (LLM 독립) |
| 에이전트 도구 경계 물리적 차단 | agent-boundary.py |
| 보안 감사 게이트 | security-reviewer (OWASP+WebView) |
| 스마트 컨텍스트 | build_smart_context() 50KB 캡 |
| 실패 유형별 수정 전략 | fail_type 분기 (test/validator/pr/security) |
| 실패 패턴 자동 프로모션 | Auto-Promoted Rules 3회 반복 시 |
| 단일 소스 원칙 물리적 강제 | orch-rules-first.py |
| 의도 분류 라우터 | regex + LLM 하이브리드 |

---

## Phase 1 — 검증 강화 (G1·G2·G3·G7)

### G3. 수용 기준 메타데이터 + 스펙 기반 워크플로우

**태그 체계**:
- `(TEST)` — vitest 자동 테스트
- `(BROWSER:DOM)` — Playwright DOM 요소 존재/속성 쿼리
- `(MANUAL)` — 마지막 수단, curl·bash 먼저 시도

**Audit 원칙**: 메타데이터 없는 태스크 = validator SPEC_GAP 반려 (작업 전 차단)

**요구사항 ID**: `[REQ-NNN]` → prd.md → impl → 테스트 전 구간 추적

변경 파일:
- `architect.md` — `## 수용 기준` 섹션 + [REQ-NNN] + 태그 필수화
- `validator.md` — 메타데이터 미존재 시 SPEC_GAP 반려
- `orchestration-rules.md` — "메타데이터 없는 태스크 = 구현 진입 불가" 정책

### G2. 커버리지 게이트 70% (전체 파일)

전체 파일 기준 70% 미만이면 `coverage_fail`.

변경 파일: `harness-loop.sh` — `vitest run --coverage`, 파싱 + `coverage_fail`

### G7. BROWSER:DOM 자동 검증 (opt-in)

`(BROWSER:DOM)` 태그 있을 때 Playwright DOM 쿼리 자동 실행. `browser_fail` 유형 추가.

변경 파일: `harness-loop.sh` — 조건부 브라우저 스텝

### G1. 크로스모델 리뷰

pr-reviewer LGTM 후 Haiku로 세컨드 오피니언. `cross_review_fail`.

변경 파일: `harness-loop.sh` — `claude --model haiku --print` 스텝

---

## Phase 2 — 자동화 확장 (G4·G5·G6)

### G4. 커스텀 린트 + 에이전트 친화 에러 메시지

pre-commit 단계에서 ESLint + 커스텀 규칙. 에러 출력에 "수정 방법: ..." 포함.

변경 파일: `harness-lint.sh` (신규) + `harness-loop.sh` vitest 전 lint 단계

### G5. 엔트로피/GC 에이전트

`/scan` 커맨드로 중복 코드(jscpd)·미사용 export(knip)·파일 크기 점검. `docs/quality-grades.md` 업데이트.

변경 파일: `skills/scan.md` (신규)

### G6. PR 계약 프레임워크

PR 본문에 구조화 포맷 강제:
```
## What/Why
## 작동 증거 (테스트 결과, 스크린샷)
## 위험 + AI 역할 (HIGH/MEDIUM/LOW)
## 리뷰 포커스
```

변경 파일: `harness-loop.sh` — `generate_commit_msg()` PR 포맷 확장

---

## Phase 3 — 장기 발전 (G8·G9·G10·G11)

### G8. Git Worktree 격리 실행

각 구현 시도를 별도 worktree에서 실행. 성공 시만 메인에 병합.
`isolation: "worktree"` 활용.

### G9. 관측성 스택 (Optio 패턴)

라이브 로그 스트리밍 + 파이프라인 진행도 + 비용 분석 Web UI (localhost:30310 패턴).
`/tmp/{prefix}_observability/` 디렉터리에 로그·메트릭 수집.

### G10. Doc-Gardening 에이전트

`/doc-garden` 커맨드. 설계 문서 vs 코드 diff 비교 → 자동 수정 PR.

### G11. 뮤테이션 테스트

stryker-js 도입. 테스트 통과 후 뮤테이션 테스트로 테스트 품질 검증.
harness-loop.sh 선택적 단계.

---

## 파일 변경 전체 목록

| 파일 | Phase | 작업 |
|---|---|---|
| `orchestration-rules.md` | 1 | G3 정책 + G2/G7/G1 단계 |
| `architect.md` | 1 | 수용 기준 섹션 + REQ-ID 필수화 |
| `validator.md` | 1 | SPEC_GAP 반려 규칙 |
| `harness-loop.sh` | 1-2 | coverage/browser/cross-review 스텝 + lint 단계 |
| `harness-lint.sh` | 2 | 신규 |
| `skills/scan.md` | 2 | 신규 GC 스킬 |
| `harness-loop.sh` | 3 | worktree + observability 연동 |

---

## 검증

```bash
grep -c "(TEST)\|(BROWSER:DOM)\|(MANUAL)" docs/milestones/**/impl/*.md
npx vitest run --coverage 2>&1 | grep "All files"
grep "(BROWSER:DOM)" docs/milestones/**/impl/*.md
echo "test diff" | claude --model haiku --print -p "이 diff에서 버그 찾아라"
```
