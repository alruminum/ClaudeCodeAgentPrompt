# Task Decompose

`@MODE:ARCHITECT:TASK_DECOMPOSE` → `READY_FOR_IMPL` ×N

```
@PARAMS: { "stories_doc": "Epic stories.md 경로", "design_doc": "설계 문서 경로" }
@OUTPUT: { "marker": "READY_FOR_IMPL", "impl_paths": ["생성된 impl 파일 경로 목록"] }
```

메인 Claude 또는 product-planner 완료 후 호출된 경우.

**목표**: product-planner가 스토리까지 작성한 epic 파일을 받아, 각 스토리를 기술 구현 단위로 분해하고 impl 파일을 작성한다.

### 작업 순서

1. 스토리 목록 확인:
   - **GitHub Issues 사용 시**: `mcp__github__list_issues` (milestone=Epics, label=현재버전)로 에픽 이슈 조회 → 본문에서 스토리 목록 확인
   - **로컬 파일 폴백**: `docs/milestones/vNN/epics/epic-NN-*/stories.md` 읽기
2. 프로젝트 루트 `CLAUDE.md` 읽기 (기술 스택, 제약 확인)
3. `docs/impl/00-decisions.md` 또는 유사 파일 읽기 (기존 결정 확인)
4. 각 스토리에 대해 기술 태스크 도출 (구현 단위로 쪼개기)
5. 태스크 등록:
   - **GitHub Issues 사용 시**: `mcp__github__update_issue`로 스토리 이슈 body에 태스크 체크리스트 추가
   - **로컬 파일 폴백**: `stories.md` 각 스토리 아래 태스크 추가 (체크박스 형식)
6. 각 태스크에 대응하는 `docs/milestones/vNN/epics/epic-NN-*/impl/NN-*.md` 파일 작성
7. READY_FOR_IMPL 게이트 통과 여부 확인 후 완료 보고

### 태스크 도출 기준

- 한 태스크 = engineer가 한 번 루프로 구현 가능한 단위
- 파일 1~3개 생성/수정 범위
- 명확한 PASS/FAIL 판단이 가능해야 함

### 출력 형식

```
Epic 태스크 분해 완료: [epic 파일 경로]

## 추가된 태스크
[스토리별 태스크 목록 요약]

## 생성된 impl 파일
- [impl 파일 경로 1]
- [impl 파일 경로 2]
```
