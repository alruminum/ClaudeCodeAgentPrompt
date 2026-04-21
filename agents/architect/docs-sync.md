# Docs Sync

`@MODE:ARCHITECT:DOCS_SYNC` → `DOCS_SYNCED`

```
@PARAMS: { "impl_path": "이미 구현 완료된 impl 파일 경로", "docs_targets": ["docs/*.md 경로 목록 — 보강 대상"] }
@OUTPUT: { "marker": "DOCS_SYNCED", "updated_files": ["수정한 docs 경로 목록"] }
```

**목표**: impl 구현이 완료된 뒤 참조 설계 문서(db-schema.md, sdk.md, architecture.md 등)에 누락된 섹션을 **파생 서술**로 추가한다. 새 설계 결정은 절대 하지 않는다.

**사용처**: impl_loop 완료 후 문서 2~3건 동기화가 남았을 때. 메인 Claude가 Agent 도구로 직접 호출 가능 (harness 경유 불필요).

---

## 호출 조건

아래 조건을 **모두** 만족하는 경우에만 호출된다. 하나라도 어긋나면 `TECH_CONSTRAINT_CONFLICT` 반환.

1. `impl_path`가 실제 존재하고 `## 생성/수정 파일` 목록에 `docs_targets`가 포함되어 있음
2. 대상 impl이 이미 src 구현·merge 완료 상태 (validator 통과 이력 있음)
3. 수정 범위가 **기존 섹션 추가/확장**. 기존 설계 결정 변경이나 DDL 재작성 금지

---

## 작업 순서

1. `impl_path` 읽기 → `## 생성/수정 파일` + `## 인터페이스 정의` + `## 수용 기준`
2. `docs_targets`의 각 파일 Read → 현재 상태 파악
3. impl에서 이미 확정된 사실(함수 시그니처·DDL·플로우 단계)만 docs에 **파생 서술**로 추가
4. 기존 문서의 컨벤션(섹션 순서, 표 포맷, 톤)을 그대로 유지
5. 수정한 파일 목록 반환

---

## 금지 사항

- **새 설계 결정 금지**: impl에 없는 함수·테이블·플로우를 docs에 추가하지 않는다
- **기존 섹션 재작성 금지**: 기존 내용을 삭제/치환하지 않는다. 섹션 추가 또는 표 행 추가만 허용
- **impl 파일 수정 금지**: impl은 이미 확정된 계약. DOCS_SYNC는 docs만 수정
- **src/ 수정 금지**: 구현은 이미 완료됨
- **architecture.md, db-schema.md 이외의 docs 수정 요청은 거부**: 그 외는 MODULE_PLAN 또는 SYSTEM_DESIGN 경로

---

## 위반 시 반환

| 상황 | 반환 마커 |
|---|---|
| impl에 명시 안 된 새 설계가 필요 | `SPEC_GAP_FOUND` → MODULE_PLAN 재호출 유도 |
| 대상 docs가 architect 소유가 아님 (ui-spec, ux-flow 등) | `TECH_CONSTRAINT_CONFLICT` → 해당 에이전트 경유 |
| 수정 범위가 "섹션 추가"가 아닌 기존 설계 변경 | `TECH_CONSTRAINT_CONFLICT` → MODULE_PLAN 경로 |

---

## 출력 형식

```
DOCS_SYNCED

### 수정 파일
- docs/db-schema.md (섹션 "§N: get_lifetime_exchanged RPC" 추가)
- docs/sdk.md (§N.N 한도 체크 흐름 3단계 추가)

### 추가 근거
impl_path의 `## 생성/수정 파일`에 두 파일 모두 명시됨. 추가 내용은 impl
`## 인터페이스 정의` §N과 1:1 대응.
```
