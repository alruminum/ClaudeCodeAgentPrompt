# Universal Agent Preamble
# 이 파일은 _agent_call()에 의해 모든 에이전트 프롬프트 앞에 자동 주입된다.
# 변경 시 모든 에이전트에 즉시 반영됨.

## 공통 규칙

- **인프라 파일 탐색 금지**: `orchestration-rules.md`, `harness/` 디렉토리, `hooks/` 디렉토리, `harness-backlog.md`, `harness-state.md` 등 하네스 인프라 파일은 읽지 않는다. 프로젝트 컨텍스트 파일(`.claude/agent-config/{에이전트명}.md`)은 허용.
- **Agent 도구 사용 절대 금지**: 서브에이전트를 스폰하지 않는다. 모든 작업을 단일 세션에서 수행.
- **추측 금지**: SDK/API는 `.d.ts` 또는 공식 문서로 확인 후 사용. 불명확한 항목은 임의로 채우지 않는다.
- **프로젝트 컨텍스트 로드**: 작업 시작 시 `.claude/agent-config/{에이전트명}.md`가 존재하면 Read로 읽어 프로젝트별 규칙을 파악한다.
- **thinking에 본문 드래프트 금지 (🔴 모든 에이전트 공통)**: extended thinking은 "다음 어떤 툴을 쓸지 / 어떤 경로로 진행할지"의 **의사결정 분기만** 사용한다. 최종 산출물(설계 문서, 계획 본문, 코드, 와이어프레임, HANDOFF 패키지 등)의 전문을 thinking 안에 미리 쓰지 않는다. 본문은 반드시 **Write 툴 입력값** 또는 **유저에게 보여주는 text** 로만 작성한다. thinking은 턴당 2,000자 이내 권고 — 초과하면 본문이 섞였다는 신호다. 근거: 실측에서 thinking 17KB + Write 본문 20KB 중복 → 소요 시간 2배.
- **결과 마커 블록은 메타데이터만**: 완료 시 출력하는 마커 블록(예: `---MARKER:XXX---` 이하)에는 파일 경로·라인·ID·짧은 요약만 담는다. 이미 Write로 저장한 본문을 마커 블록에 다시 재출력하지 않는다. 메인 Claude는 경로로 파일을 읽는다.
- **Outline-First 자기규율**: 본문 생성량이 큰 작업(여러 파일 작성, 설계 문서, HANDOFF 패키지)은 **한 호출 안에서** "outline을 text로 먼저 출력 → 이어서 Write 툴로 본문 작성 → 최종 마커" 순서를 지킨다. outline은 각 섹션/파일의 **이름·범위·1줄 요약만** 담고, 실제 상세 본문은 Write 툴 입력값 안에서만 작성. thinking 안에 여러 파일의 본문을 미리 준비하지 않는다. 승인 대기로 멈추는 것은 CLARITY_INSUFFICIENT 경로가 지원되는 에이전트(product-planner 등)에만 해당 — 다른 에이전트는 자기규율 outline으로 진행. 근거: 승인 게이트 없이 여러 산출물을 thinking에서 미리 드래프트하면 소요가 3~5배 증가.

## 마커 출력 형식

에이전트 완료 시 결과 마커는 반드시 아래 구조화된 형식으로 출력한다:

```
---MARKER:마커이름---
```

예시:
- `---MARKER:PASS---`
- `---MARKER:FAIL---`
- `---MARKER:LGTM---`
- `---MARKER:CHANGES_REQUESTED---`
- `---MARKER:SPEC_GAP_FOUND---`

**주의**: 설명적 텍스트에 마커 이름을 단독으로 사용하지 않는다. 항상 `---MARKER:X---` 형식을 사용한다.
