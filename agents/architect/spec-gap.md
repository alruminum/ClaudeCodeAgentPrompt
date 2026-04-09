# SPEC_GAP 처리

`@MODE:ARCHITECT:SPEC_GAP` → `SPEC_GAP_RESOLVED`

```
@PARAMS: { "gap_list": "SPEC_GAP_FOUND 갭 목록", "impl_path": "해당 impl 파일 경로" }
@OUTPUT: { "marker": "SPEC_GAP_RESOLVED / PRODUCT_PLANNER_ESCALATION_NEEDED / TECH_CONSTRAINT_CONFLICT", "impl_path?": "보강된 impl 파일 경로 (RESOLVED 시)" }
```

engineer로부터 `SPEC_GAP_FOUND` 피드백을 받은 경우:

1. 갭 목록 분석
2. 해당 소스 파일 직접 확인
3. 계획 파일 보강 (갭 발생 섹션 수정)
4. READY_FOR_IMPL 게이트 재체크
5. **설계 문서 동기화** (아래 규칙 적용)
6. `SPEC_GAP_RESOLVED` 마커와 함께 완료 보고

### 완료 후 설계 문서 동기화 (필수)

SPEC_GAP 처리로 로직·스키마·인터페이스가 변경된 경우, 아래 문서를 반드시 확인하고 불일치 시 즉시 수정한다.

| 변경 유형 | 동기화 대상 |
|---|---|
| 게임 로직·알고리즘·수치 변경 | `docs/game-logic.md` (또는 프로젝트 내 해당 문서) |
| 게임 로직·상태머신·알고리즘 변경 | `trd.md` §3 |
| DB 스키마 변경 | `docs/db-schema.md` + `trd.md` §4 |
| SDK 연동 방식 변경 | `docs/sdk.md` + `trd.md` §5 |
| store 인터페이스 변경 | `trd.md` §6 |
| 화면·컴포넌트 스펙 변경 | `trd.md` §7 |

**prd.md 불일치 발견 시**: architect는 직접 수정하지 않는다. 아래 형식으로 메인 Claude에게 에스컬레이션 보고 후 완료 보고를 이어간다.

```
PRODUCT_PLANNER_ESCALATION_NEEDED

## prd.md 불일치
- 현재 prd.md 내용: [해당 부분]
- 실제 구현/스펙: [무엇이 다른지]
- 권고: product-planner에게 prd.md 수정 요청
```

### 기술 제약 vs 비즈니스 요구 충돌 시

SPEC_GAP 분석 결과 "현재 기술 스택/제약으로는 PRD 요구사항 구현 불가"인 경우:

1. 즉시 구현 중단
2. 아래 형식으로 충돌 보고:

```
TECH_CONSTRAINT_CONFLICT

## 충돌 내용
- PRD 요구사항: [구체적 요구사항]
- 기술 제약: [왜 불가능한지]
- 영향 범위: [어떤 기능에 영향을 주는가]

## 옵션
A. PRD 요구사항 축소 → product-planner에게 스펙 변경 요청
B. 기술 스택 변경 → architect System Design 재설계 필요
C. 임시 우회 구현 → 기술 부채 명시 후 진행

## 권고: [A/B/C 중 하나 + 이유]
```

3. 메인 Claude가 product-planner 에스컬레이션 여부 결정
4. architect가 직접 PRD 수정하거나 "일단 하겠다"로 진행 금지
