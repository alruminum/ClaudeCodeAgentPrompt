---
name: product-plan
description: 기능 추가/변경 요청을 명확히 정의한 뒤 하네스 plan 루프(product-planner → architect → validator)를 시작하는 스킬. 유저가 "기획자야", "기획아", "기능 추가할 게 생겼어", "피쳐 추가할 게 생겼어", "feature 추가", "이런 기능이 필요할 것 같아", "이런 기능이 빠진 것 같은데", "피쳐 추가", "새 기능", "새 피쳐", "기획해줘", "프로덕트 플랜" 등의 표현을 쓸 때 반드시 이 스킬을 사용한다.
---

# Product Plan Loop Skill

유저의 기능 요청을 구조화된 기획 컨텍스트로 만들고, 부족한 정보는 역질문으로 채운 뒤 하네스 plan 루프를 시작한다.

## 정보 추출

유저 메시지에서 다음 3가지를 추출한다:

| 항목 | 설명 | 예시 |
|------|------|------|
| **무엇** (WHAT) | 어떤 기능인가 | "게임 일시정지 버튼" |
| **왜** (WHY) | 왜 필요한가 / 어떤 문제를 해결하는가 | "중간에 끊기면 재개가 안 돼서" |
| **범위** (SCOPE) | 신규 화면? 기존 수정? 백엔드 포함? | "게임 플레이 화면에 버튼 추가" |

## 역질문 규칙

**무엇(WHAT)이 없으면** 반드시 물어본다.
**왜(WHY)가 없으면** 물어본다 — product-planner가 PRD를 잘 쓰려면 목적이 필요하다.
범위(SCOPE)는 추론 가능하면 넘어간다.

질문은 **한 번에 최대 2개**. 이미 말한 건 다시 묻지 않는다.

## 기획 컨텍스트 구조화

정보가 충분하면 아래 형식으로 구성한다 (추론 항목에는 `(추론)` 표시):

```
[기능] <무엇>
[목적] <왜 필요한가>
[범위] <대략적인 범위>
```

## 실행 절차

### 1단계: 기획 컨텍스트 제시

```
---
**Product Plan Loop 실행 설정**

**기획 컨텍스트:**

[기능] ...
[목적] ...
[범위] ...

---
이대로 product plan 루프 시작할까요? (product-planner → architect → validator)
```

### 2단계: 유저 확인 대기

- 긍정 응답 ("응", "ㅇㅇ", "ok", "고", "실행", "그래", "ㅇ") → 3단계 진행
- 수정 요청 → 수정 후 1단계 재출력
- 취소 → 종료

### 3단계: 하네스 plan 루프 실행

Bash 도구로 실행한다:

```bash
# PREFIX: .claude/harness.config.json 있으면 읽고, 없으면 생략 (executor.sh 기본값 사용)
PREFIX=$(python3 -c "import json,sys; d=json.load(open('.claude/harness.config.json')); print(d.get('prefix',''))" 2>/dev/null || echo "")
PREFIX_FLAG=${PREFIX:+--prefix "$PREFIX"}
python3 ~/.claude/harness/executor.py plan \
  --context "[기능] <무엇> / [목적] <왜> / [범위] <범위>" \
  $PREFIX_FLAG
```

GitHub 이슈 번호를 유저가 언급했으면 `--issue <N>` 추가.
