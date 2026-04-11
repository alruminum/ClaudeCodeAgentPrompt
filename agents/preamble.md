# Universal Agent Preamble
# 이 파일은 _agent_call()에 의해 모든 에이전트 프롬프트 앞에 자동 주입된다.
# 변경 시 모든 에이전트에 즉시 반영됨.

## 공통 규칙

- **인프라 파일 탐색 금지**: `orchestration-rules.md`, `harness/` 디렉토리, `hooks/` 디렉토리, `harness-backlog.md`, `harness-state.md` 등 하네스 인프라 파일은 읽지 않는다. 프로젝트 컨텍스트 파일(`.claude/agent-config/{에이전트명}.md`)은 허용.
- **Agent 도구 사용 절대 금지**: 서브에이전트를 스폰하지 않는다. 모든 작업을 단일 세션에서 수행.
- **추측 금지**: SDK/API는 `.d.ts` 또는 공식 문서로 확인 후 사용. 불명확한 항목은 임의로 채우지 않는다.
- **프로젝트 컨텍스트 로드**: 작업 시작 시 `.claude/agent-config/{에이전트명}.md`가 존재하면 Read로 읽어 프로젝트별 규칙을 파악한다.

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
