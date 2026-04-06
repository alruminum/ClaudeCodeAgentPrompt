---
description: 현재 프로젝트의 하네스 루프 실행 로그를 실시간 모니터링한다. /harness-monitor 실행 시 PREFIX를 자동 감지해 tail -f로 디버그 로그를 스트리밍한다.
argument-hint: ""
---

# /harness-monitor

하네스 루프 디버그 로그를 실시간으로 모니터링한다.

## PREFIX 자동 감지

아래 순서로 현재 활성 PREFIX를 감지한다:

```bash
# 1순위: 활성 harness lock 파일
PREFIX=$(ls /tmp/*_harness_active 2>/dev/null | head -1 | xargs basename 2>/dev/null | sed 's/_harness_active//')

# 2순위: 최신 debug log 파일
if [ -z "$PREFIX" ]; then
  PREFIX=$(ls -t /tmp/*-harness-debug.log 2>/dev/null | head -1 | xargs basename 2>/dev/null | sed 's/-harness-debug\.log//')
fi

# 3순위: 기본값
if [ -z "$PREFIX" ]; then
  PREFIX="mb"
fi

echo "PREFIX: $PREFIX"
```

## 실행

감지된 PREFIX로 로그 파일 상태를 확인하고 모니터링을 시작한다:

```bash
LOG="/tmp/${PREFIX}-harness-debug.log"

if [ ! -f "$LOG" ]; then
  echo "⚠️  하네스가 아직 실행되지 않았습니다."
  echo "   로그 파일 없음: $LOG"
  echo ""
  echo "하네스가 시작되면 아래 명령어로 모니터링하세요:"
  echo "   tail -f $LOG"
else
  echo "📡 하네스 로그 모니터링 시작 (PREFIX=$PREFIX)"
  echo "   파일: $LOG"
  echo "   종료: Ctrl+C"
  echo ""
  tail -f "$LOG"
fi
```

## 유저에게 안내

위 스크립트를 실행한 결과를 유저에게 보여준다.

로그 파일이 없으면:
- PREFIX와 예상 로그 경로를 알려준다
- 하네스가 시작된 후 아래 명령어를 직접 실행하도록 안내한다:
  ```bash
  tail -f /tmp/${PREFIX}-harness-debug.log
  ```

로그 파일이 있으면:
- `tail -f`를 실행해 실시간 스트리밍을 시작한다
- 유저가 Ctrl+C로 종료할 수 있음을 안내한다
