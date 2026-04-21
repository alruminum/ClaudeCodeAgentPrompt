---
name: quick
description: 작은 버그픽스·마이너 수정을 한 줄로 받아 하네스 루프 전체를 자동 진입시키는 스킬. 유저가 "간단히 해줘", "작은 수정이야", "한 줄 버그", "/quick", "퀵", "바로 고쳐줘" 등을 말할 때 반드시 이 스킬을 사용한다. 내부적으로 qa → architect LIGHT_PLAN → executor.py impl (simple) 을 체이닝한다. 루프 불변식(plan validation, LGTM, src 경계)은 그대로 유지.
---

# Quick Skill

"간단히 해줘" 류 요청을 루프 불변식 유지한 채로 한 번의 확인만 받고 하네스에 투입한다.
/qa 와 차이점: 증상/기대/위치 ping-pong을 최소화하고, 거의 항상 `depth=simple` 로 떨어뜨린다.

## 언제 사용하는가

- 유저 표현이 "간단히", "작은 수정", "퀵"이 명시됨
- 또는 수정 범위가 한 줄/한 함수 내부로 명백히 보이는 경우

**자동 SKIP 조건 (이 스킬을 쓰지 말 것):**
- 유저가 "새 기능", "피쳐", "기획" 을 말함 → `/product-plan`
- 유저가 "리디자인", "레이아웃", "시안" → `/ux`
- 코드 변경 범위가 여러 모듈에 걸침 → `/qa` (정석 분류)

---

## 절차

### Step 1 — 한 줄 정규화

유저 원문을 그대로 보존하되, 이슈 제목용 한 줄을 뽑는다.

```
---
**Quick 실행 설정**

[요청] <유저 원문 그대로>
[이슈 제목] <한 줄 요약, 최대 70자>
[depth] simple

진행할까요?
---
```

확인 못 받으면 **대기**. 절대 자동 진행 금지 (feedback_confirm_before_act.md).

### Step 2 — QA 에이전트 호출 (이슈 생성용)

Agent 도구로 qa 에이전트를 호출. `quick_mode: true` 를 넘겨 분석은 최소화, 이슈 생성만 수행하도록 지시.

```
@MODE:QA:ANALYZE
@PARAMS: {
  "issue": "[유저 원문] <원문 그대로>\n[Quick 모드] depth=simple 고정, architect LIGHT_PLAN 진입 예정",
  "quick_mode": true
}
```

QA 출력에서 이슈 번호(`#NNN`)를 추출. 실패 시 유저에게 에스컬레이션.

### Step 3 — executor.py impl 기동

Bash 도구로 직접 실행. `timeout: 1800000` (30분) 필수.

```bash
PREFIX=$(python3 -c "import json; d=json.load(open('.claude/harness.config.json')); print(d.get('prefix',''))" 2>/dev/null || echo "")
PREFIX_ARGS=()
[ -n "$PREFIX" ] && PREFIX_ARGS=(--prefix "$PREFIX")
python3 ~/.claude/harness/executor.py impl \
  --issue <QA가 생성한 이슈 번호> \
  --depth simple \
  "${PREFIX_ARGS[@]}"
```

executor.py 가 내부적으로:
- plan 루프 → architect LIGHT_PLAN — 이슈 번호 전달
- validator (Plan Validation)
- test-engineer / engineer / validator B / pr-reviewer
- commit-gate LGTM 체크

모든 기존 게이트는 그대로 작동한다.

### Step 4 — 결과 보고

executor.py 완료 후:

```
---
**Quick 완료**

이슈: #<N>
impl: docs/bugfix/#<N>-<slug>.md
커밋: <hash>
변경 파일: <목록>
---
```

HARNESS_ESCALATE 로 돌아오면 유저에게 정상 보고 — 자동 재시도 금지.

---

## 루프 불변식 준수 체크

이 스킬이 건드리지 않는 것:
- engineer 는 여전히 executor.py 경유 (HARNESS_ACTIVE 플래그는 executor.py 가 세팅)
- plan validation 게이트 통과 강제
- test-engineer → validator B → pr-reviewer LGTM 순서
- src/** 수정은 engineer 만
- commit 전 LGTM 필수

**이 스킬은 기존 bugfix 루프의 진입 UX만 단축한다. 게이트는 하나도 건너뛰지 않는다.**
