---
description: 하네스 이벤트 로그를 깔끔하게 표시. 에이전트 시작/완료 이벤트를 텍스트로 출력.
argument-hint: ""
---

# /harness-monitor

하네스 이벤트 로그를 읽어서 텍스트 메시지로 출력한다.

## 실행

1. `.claude/harness-state/.{prefix}_events` 파일을 **Read 도구**로 읽는다 (prefix는 harness.config.json에서 확인).
2. 내용을 아래처럼 텍스트 메시지로 출력한다 (Bash 출력이 아님):

```
📡 하네스 이벤트 로그:

[10:23:15] architect 시작
[10:25:01] architect → LIGHT_PLAN_READY
[10:25:01] architect 완료 (97s, $0.30)
[10:25:02] Plan Validation → PASS
[10:25:03] engineer 시작
[10:26:20] engineer 완료 (77s, $0.36)
[10:26:20] pr-reviewer → LGTM
[10:26:21] HARNESS_DONE (attempt 1)
```

3. 파일이 없으면 "하네스 미실행" 메시지를 출력한다.
4. 파일이 비어있으면 "이벤트 없음 — 하네스 시작 대기" 메시지를 출력한다.

## 주의
- Bash 도구가 아니라 **Read 도구 + 텍스트 출력**으로 처리한다
- prefix 확인은 Bash로 하되, 이벤트 로그 자체는 Read로 읽어 텍스트로 표시
