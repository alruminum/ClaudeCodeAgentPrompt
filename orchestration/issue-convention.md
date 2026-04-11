# GitHub 이슈 형식

GitHub 이슈 생성 시 제목·본문 규칙. qa/architect 에이전트가 참조.

---

## 제목 규칙
모든 이슈의 제목은 `[milestone] 설명` 형식으로 고정한다. milestone은 반드시 포함한다.

| 이슈 유형 | 제목 예시 |
|---|---|
| 버그 | `[bugs] ComboIndicator 위치 불일정 + streak 0 미표시 스펙 변경` |
| Feature | `[v1] 로그인 기능 구현` |
| Story | `[v1] Story 2: 인증 토큰 갱신 처리` |
| Epic | `[v1] Epic 3: 인증 시스템 리팩토링` |

## 1이슈 1설명 원칙
유저가 이슈를 하나 설명하면 → **이슈 1개만** 생성한다. 증상이 여러 개라도 분리하지 않는다.
예: 증상 A + 증상 B + 기능 C 설명 → 이슈 3개 생성 금지. 하나의 이슈로 묶어 등록.

## 본문 템플릿

**버그 이슈 (QA 생성)**
```markdown
## 증상
[실제 동작 설명]

## 기대 동작
[기대하는 동작]

## 재현 조건
1. 단계 1
2. 단계 2

## 근본 원인
- 파일: `파일경로`
- 위치: `함수명` (Line N)
- 원인: [원인 설명]

## 수정 지점
- `파일경로`: [변경 내용]

## QA 분류
- 타입: FUNCTIONAL_BUG / SPEC_ISSUE / DESIGN_ISSUE
- 심각도: LOW / MEDIUM / HIGH
- 라우팅: engineer 직행 / architect 경유 / 디자인 루프

## 체크리스트
- [ ] [수정 항목]
```

**Feature 이슈 (Architect module-plan 생성)**
```markdown
## 목적
[이 기능이 필요한 이유]

## 구현 범위
- [ ] 항목1
- [ ] 항목2

## 관련 파일
- `파일경로`

## 완료 기준
- [ ] 기준1
```

**Story 이슈 (Architect tech-epic 생성)**
```markdown
## 목표
[이 스토리로 달성하는 것]

## 구현 태스크
- [ ] 태스크1
- [ ] 태스크2

## 완료 기준
- [ ] 기준1
```

**Epic 이슈 (Architect tech-epic 생성)**
```markdown
## 목적
[에픽의 기술 목표]

## 스토리 목록
- [ ] Story 1: ...
- [ ] Story 2: ...

## 완료 기준
- [ ] 기준1
```
