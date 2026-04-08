# Technical Epic

`@MODE:ARCHITECT:TECH_EPIC` → `SYSTEM_DESIGN_READY`

```
@PARAMS: { "goal": "개선 목표 설명", "scope": "영향 범위" }
@OUTPUT: { "marker": "SYSTEM_DESIGN_READY", "stories_doc": "생성된 stories.md 경로", "updated_files": ["backlog.md", "CLAUDE.md"] }
```

기술 부채, 인프라 개선, 리팩토링, 아키텍처 변경에 해당하는 에픽을 아키텍트가 직접 작성한다.
기능 에픽(비즈니스 가치 중심)은 product-planner 영역이므로 제외.

**해당 유형:**
- DB 마이그레이션 / 스키마 정합성 복구
- 타입 안전성 개선 (타입 자동화, any 제거)
- 성능·보안·의존성 개선
- 코드 구조 리팩토링

**작업 순서:**
1. 다음 에픽 번호 확인:
   - **GitHub Issues 사용 시**: `mcp__github__list_issues` (milestone=Epics)로 기존 에픽 이슈 목록 조회
   - **로컬 파일 폴백**: `backlog.md` 읽어 다음 에픽 번호 확인
2. 에픽 등록:
   - **GitHub Issues 사용 시**: `mcp__github__create_issue`로 에픽 이슈 생성 (milestone=Epics, label=버전레이블) + 스토리 이슈 생성 (milestone=Story, label=버전레이블, sub-issue 연결) — 구체적 milestone/repo/버전레이블은 프로젝트 에이전트 오버라이드 참조
   - **로컬 파일 폴백**: `docs/milestones/vNN/epics/epic-NN-[이름]/stories.md` 생성, `backlog.md`에 행 추가
3. 프로젝트 `CLAUDE.md` 에픽 목록 섹션 업데이트
4. 필요한 경우 각 스토리에 대응하는 impl 파일 작성 (Module Plan 실행)

### 출력 형식

```
Technical Epic 작성 완료: [stories.md 경로]

## 생성된 에픽
- 에픽 번호/이름
- 스토리 목록 요약

## 업데이트된 파일
- backlog.md
- CLAUDE.md
```
