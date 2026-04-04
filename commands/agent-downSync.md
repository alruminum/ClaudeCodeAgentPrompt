---
description: 전역 에이전트(~/.claude/agents/)의 공통 지침을 현재 프로젝트 에이전트(.claude/agents/)에 동기화한다. 프로젝트 특화 지침(~/.claude/project-agents/{id}/)은 보존한다.
argument-hint: "[agent-name ...] (생략 시 전체)"
---

# /agent-downSync

전역 에이전트 공통 지침을 현재 프로젝트에 동기화한다.

**인수:** $ARGUMENTS

---

## 소스 구조

| 소스 | 경로 | 역할 |
|---|---|---|
| 전역 베이스 | `~/.claude/agents/{name}.md` | 공통 지침 (권위 소스) |
| 프로젝트 특화 | `~/.claude/project-agents/{project_id}/{name}.md` | 프로젝트 특화 섹션 (프라이빗) |
| 출력 대상 | `.claude/agents/{name}.md` | 병합 결과 |

---

## 실행 순서

### Step 1 — project_id 도출

현재 작업 디렉토리 절대경로에서 `/`를 `-`로 치환하여 project_id를 만든다.

예) 현재 디렉토리가 `/Users/dc.kim/project/memoryBattle` → project_id = `-Users-dc-kim-project-memoryBattle`

### Step 2 — 대상 에이전트 목록 결정

`$ARGUMENTS`가 비어 있으면: `~/.claude/agents/`의 모든 `.md` 파일 이름(확장자 제거)을 목록으로 사용.
`$ARGUMENTS`에 이름이 있으면: 공백으로 구분한 각 이름을 목록으로 사용.

### Step 3 — 에이전트별 3-source 병합

각 에이전트 `{name}`에 대해:

#### 3-1. 전역 베이스 Read
`~/.claude/agents/{name}.md` 를 Read한다.
- 파일이 없으면: `⚠ {name}: 전역 파일 없음 — 스킵` 출력 후 다음 에이전트로.

#### 3-2. 공통 지침 추출
전역 파일에서 `## 프로젝트 특화`로 시작하는 첫 번째 줄 **직전**까지를 공통 지침 부분으로 추출한다.
(해당 줄 포함 이하는 모두 버린다. `## 프로젝트 특화 지침\n<!-- 프로젝트별 추가 지침 -->` 플레이스홀더 줄들도 포함해 버림.)
추출 결과 끝의 빈 줄은 하나만 남긴다.

#### 3-3. 프로젝트 특화 부분 결정
`~/.claude/project-agents/{project_id}/{name}.md` 존재 여부를 Glob으로 확인한다.

- **존재**: 해당 파일을 Read → 파일 전체를 프로젝트 특화 부분으로 사용.
- **없음**: 빈 플레이스홀더를 프로젝트 특화 부분으로 사용:
  ```
  ## 프로젝트 특화 지침
  
  <!-- 프로젝트별 추가 지침 -->
  ```

#### 3-4. 변경 없음 판단 (스킵 조건)
현재 `.claude/agents/{name}.md`가 이미 존재하는 경우:
- 해당 파일의 공통 지침 부분(첫 번째 `## 프로젝트 특화` 줄 직전까지)을 추출한다.
- 새 공통 지침 부분과 문자열이 동일하면 Write 스킵 → `변경 없음` 으로 기록.

#### 3-5. 병합 후 Write
병합 내용 = 공통 지침 부분 + 프로젝트 특화 부분

`.claude/agents/` 디렉토리가 없으면 먼저 Bash로 `mkdir -p .claude/agents`를 실행한다.
Write로 `.claude/agents/{name}.md` 에 병합 내용을 저장한다.

결과:
- 기존 파일 없음 → `신규 생성`
- 기존 파일 있고 공통 지침 변경됨 → `업데이트 (공통 지침 갱신)`
- 기존 파일 있고 동일 → `변경 없음`

### Step 4 — 완료 보고

```
[agent-downSync] 동기화 완료
project_id: {project_id}

| 에이전트 | 결과 |
|---|---|
| validator | 업데이트 (공통 지침 갱신) |
| architect | 신규 생성 |
| engineer | 변경 없음 |
```

경고가 있으면(전역 파일 없음 등) 표 아래에 이어서 출력한다.

---

## 주의사항

- `## 프로젝트 특화` 이하 내용은 절대 수정하지 않는다 (프로젝트 특화 파일이 권위 소스)
- 전역 frontmatter(`tools`, `model`, `description`)도 함께 업데이트된다 (전역이 권위 소스)
- `.claude/agents/`가 `.gitignore`에 없어도 강제 추가하지 않는다 (경고만 출력)
