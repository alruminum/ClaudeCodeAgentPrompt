---
description: 하네스 이벤트 로그 확인. 현재 스냅샷 출력 + 실시간 스트리밍 안내.
argument-hint: ""
---

# /harness-monitor

하네스 이벤트 로그의 현재 스냅샷을 출력하고, 실시간 모니터링 명령어를 안내한다.

## 실행

**Bash 도구 단일 호출**로 아래 스크립트를 실행한다.

```bash
PREFIX=$(jq -r '.prefix // "hl"' .claude/harness.config.json 2>/dev/null || echo "hl")
EVENTS=".claude/harness-state/.${PREFIX}_events"
if [[ ! -f "$EVENTS" ]]; then echo "하네스 미실행"; exit 0; fi
echo "📡 이벤트 로그 스냅샷:"
echo "────────────────────────────────────────"
cat "$EVENTS"
echo "────────────────────────────────────────"
echo ""
echo "실시간 스트리밍: ! tail -f $EVENTS"
```

## 절대 규칙
- **Bash 도구 단일 호출만** 사용. Read 도구 사용 금지.
- Bash 실행 **전후로 텍스트 메시지를 절대 출력하지 않는다.** 해석, 요약, 상태 설명 일체 금지.
- 종료 후에도 추가 코멘트 없이 유저 입력을 기다린다.
