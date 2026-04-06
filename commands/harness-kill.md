# 하네스 중단

현재 실행 중인 하네스 루프를 즉시 중단합니다.

Bash 도구로 실행:
```bash
touch /tmp/$(cat .claude/harness.config.json | jq -r '.prefix')_harness_kill
echo "킬 스위치 활성화. 다음 에이전트 호출 전에 루프가 중단됩니다."
```
