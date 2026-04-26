# Document Update Record (WHAT)

Task-ID 기반 변경 추적 로그. 모든 코드/규칙/훅 변경은 **여기에 1행 추가**한다.
**WHY**(결정 근거·검토 대안·follow-up)는 [`rationale-history.md`](rationale-history.md)에서 같은 Task-ID로 추적.

## Task-ID 형식

```
HARNESS-CHG-YYYYMMDD-NN
```

- `YYYYMMDD`: 커밋 날짜 (UTC 아니어도 됨, 로컬 기준 일관성만 유지)
- `NN`: 그 날짜의 일련번호 (01부터)

## Change-Type 토큰

| 토큰 | 감시 경로 |
|---|---|
| `agents` | `agents/**` |
| `hooks` | `hooks/**`, `settings.json` |
| `harness-core` | `harness/{core,helpers,config}.py` |
| `plan-loop` | `harness/plan_loop.py` |
| `impl-loop` | `harness/{impl_loop,impl_router}.py` |
| `commands` | `commands/**` |
| `orchestration` | `orchestration/**`, `orchestration-rules.md` |
| `tests` | `harness/tests/**` |
| `docs-only` | 위 전부에 해당 안 됨 |

## Document-Exception

필수 동반 문서를 **의도적으로** 생략하는 경우 커밋 diff의 **추가 라인**에 아래 형식으로 명시:

```
Document-Exception: <Task-ID> <사유>
```

과거 누적 예외는 자동 무효(현재 diff 스코프만 유효). drift-check가 git diff 추가 라인만 파싱한다.

---

## 엔트리

| Task-ID | Date | Change-Type | Files | Exception |
|---|---|---|---|---|
| HARNESS-CHG-20260426-01 | 2026-04-26 | docs+orchestration | setup-harness.sh, orchestration-rules.md, orchestration/update-record.md | - |
| HARNESS-CHG-20260425-02 | 2026-04-25 | hooks+orchestration+docs | hooks/harness-drift-check.py, orchestration/update-record.md (신규), orchestration/rationale-history.md (신규), orchestration-rules.md, orchestration/changelog.md | - |
| HARNESS-CHG-20260425-01 | 2026-04-25 | plan-loop+agents+commands+orchestration | harness/plan_loop.py, agents/plan-reviewer.md, commands/product-plan.md, orchestration/plan.md, orchestration-rules.md, orchestration/changelog.md, harness/tests/test_parity.py | - |
| HARNESS-CHG-20260424-04 | 2026-04-24 | hooks+plan-loop+orchestration | hooks/harness-session-start.py, harness/plan_loop.py, orchestration-rules.md, harness/tests/test_parity.py | - |
| HARNESS-CHG-20260424-03 | 2026-04-24 | docs | docs/{distribution-plan,plan-packaging-final}.md (→ archive/), docs/plan-plugin-distribution.md, settings.json, harness-projects.json | `docs-only` 수준 재배치 + 개인 설정 — Document-Exception: HARNESS-CHG-20260424-03 문서 리오가니제이션 |
| HARNESS-CHG-20260424-02 | 2026-04-24 | harness-core+orchestration | harness/notify.py (신규), harness/impl_loop.py, orchestration/changelog.md | - |
| HARNESS-CHG-20260424-01 | 2026-04-24 | agents+plan-loop+hooks+orchestration+commands+tests | agents/plan-reviewer.md (신규), harness/plan_loop.py, harness/core.py, hooks/agent-boundary.py, commands/product-plan.md, orchestration/{plan,agent-boundaries,changelog}.md, orchestration-rules.md, harness/tests/test_parity.py | - |

---

## 워크플로우

1. **작업 시작**: Task-ID 부여 — `HARNESS-CHG-$(date +%Y%m%d)-{NN}` 형식.
2. **작업 수행**: 관련 파일 수정.
3. **커밋 전**: 이 파일 맨 위 엔트리에 1행 추가 (Task-ID, 파일 목록, 필요 시 Exception).
4. **필요 시**: [`rationale-history.md`](rationale-history.md)에 같은 Task-ID로 상세 근거 기록.
5. **커밋**: drift-check 훅이 `Change-Type → 필수 동반 파일` 규칙을 자동 검증.
6. **FAIL 시**: 누락 파일 수정 후 재커밋, 또는 `Document-Exception: <Task-ID> <사유>` 라인을 커밋 메시지·diff에 추가.
