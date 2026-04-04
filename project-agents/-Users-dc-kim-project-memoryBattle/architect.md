## 프로젝트 특화 — 컨텍스트 파악 순서

1. `CLAUDE.md`를 읽어 문서 목록과 현재 마일스톤을 파악한다.
2. GitHub Issues에서 현재 에픽 목록을 조회한다:
   `mcp__github__list_issues` — repo: `alruminum/memory-battle`, milestone: `Epics`, label: CLAUDE.md "현재 버전 레이블", state: `open`
3. 요청된 에픽의 GitHub Issue 본문 또는 `docs/milestones/vNN/epics/epic-NN-*/stories.md`를 읽어 스토리/태스크 맥락을 파악한다.
4. 에픽 내 기존 impl 파일을 읽어 기존 설계 결정을 확인한다.
5. 요청된 모듈과 관련된 설계 문서를 읽는다:
   - 화면/컴포넌트 모듈 → `docs/ui-spec.md` + `docs/architecture.md`
   - 게임 로직 모듈 → `docs/game-logic.md`
   - DB/랭킹 모듈 → `docs/db-schema.md`
   - SDK 연동 모듈 → `docs/sdk.md`
6. 해당 에픽 내 기존 impl 파일 1~2개를 읽어 포맷 패턴을 확인한다.
7. `docs/milestones/vNN/epics/epic-NN-*/impl/NN-모듈명.md` 파일을 작성한다.
8. 설계 결정 근거는 impl 파일 내 "결정 근거" 섹션에 직접 작성한다.
9. `stories.md`에 해당 태스크가 없으면 해당 스토리 아래 추가한다.
10. impl 파일 작성 완료 후 **GitHub Issues 생성** — base의 "이슈 생성 분기" 규칙에 따라 분기한다.

    **프로젝트 구체 값:**
    - repo: `alruminum/memory-battle`
    - feat 이슈: milestone=`Feature`, labels=`["feat", "{현재버전레이블}"]`
    - 현재버전레이블: `CLAUDE.md` "현재 버전 레이블" 항목 참조
    - milestone 번호는 이슈 생성 전 반드시 `CLAUDE.md`의 "이슈 생성 시 마일스톤 처리 규칙"에 따라 조회

    **`[epic-level]` 경로일 때 (product-planner 경유 또는 명시적 에픽 요청):**
    기존 Story 이슈 본문에 impl 파일 경로 업데이트 (`mcp__github__update_issue`).

11. impl 파일 작성 완료 후 **`CLAUDE.md`의 모듈 계획 파일 표를 반드시 업데이트**한다:
    - 해당 milestone/epic 섹션 아래 새 impl 항목 추가
    - 섹션이 없으면 `### vNN` + `**Epic NN — 이름** · [stories](경로)` 헤더 포함해 추가

## 계획 파일 형식

```
# NN. 기능명

## 생성 파일
- `src/경로/파일명.tsx`          ← 새 파일
- `src/경로/기존파일.ts` (수정)  ← 기존 파일 수정 시

---

## 파일명.tsx

### Props

​```typescript
interface 파일명Props {
  // 타입 정의
}
​```

### 핵심 로직

​```typescript
// 함수 시그니처, 의사코드 또는 핵심 스니펫
​```

### 주의사항
- 다른 모듈과의 경계
- 의존하는 모듈 번호 명시
```

## 설계 문서 수정 시 플래그 규칙

`docs/game-logic.md`, `docs/architecture.md`, `trd.md` 등 보호된 설계 문서를 수정하기 **직전**에 반드시 플래그 파일을 생성하고, 수정 완료 후 삭제한다:

```bash
# 수정 전
touch /tmp/mb_architect_active

# ... Write/Edit 수행 ...

# 수정 후
rm -f /tmp/mb_architect_active
```

이 플래그 없이 수정 시 PreToolUse 훅에 의해 차단된다.

---

## 규칙

- 타입은 항상 TypeScript 코드 블록으로 제시한다.
- 함수 시그니처는 실제 구현 가능한 수준으로 상세하게 작성한다.
- 추측 금지: SDK 관련 내용은 `docs/sdk.md` 기준으로만 작성한다.
- 파일 경로는 `src/` 기준 절대경로로 작성한다.
- 모듈 번호는 `CLAUDE.md`의 테이블 기준을 따른다.
- 계획 파일 작성 후 유저에게 파일 경로와 주요 내용을 간략히 보고한다.
- **어떤 방식으로 호출되든 공통 지침의 TRD 현행화 규칙을 항상 적용한다.** Mode 명시 없이 특정 파일 직접 수정 지시를 받은 경우에도 공통 지침의 TRD 현행화 섹션을 따라 trd.md를 비교·업데이트한다.
- **앱인토스 SDK API를 사용하는 모듈 설계 시, 반드시 MCP 도구로 공식 스펙을 먼저 확인한다.**
  - `Read` 도구로 `node_modules/@apps-in-toss/web-bridge/dist/index.d.ts` 직접 참조 (MCP보다 우선)
  - 또는 MCP 도구 사용 가능 시: `mcp__apps-in-toss__search_docs`, `mcp__apps-in-toss__get_doc`
  - 확인 없이 API 시그니처 작성 금지 — 기억이나 예시 코드 복붙 금지
  - 과거 확인한 스펙도 재확인 필수 (버전 업데이트 가능성)
