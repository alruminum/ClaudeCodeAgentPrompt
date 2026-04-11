---
description: 하네스 플래그 흐름과 핵심 파일을 dry-run으로 검증한다. 에이전트 호출 없음.
argument-hint: "[prefix]"
---

# /harness-test

하네스 인프라가 정상인지 smoke test를 실행한다.  
실제 에이전트는 호출하지 않으며 플래그 흐름과 파일 존재만 검사한다.

## 실행

아래 bash 명령들을 순서대로 실행하고 결과를 수집한다.

### 1. 핵심 파일 존재 확인

```bash
for f in \
  ~/.claude/harness/executor.sh \
  ~/.claude/harness/impl.sh \
  ~/.claude/harness/impl_simple.sh \
  ~/.claude/harness/impl_std.sh \
  ~/.claude/harness/impl_deep.sh \
  ~/.claude/harness/impl_helpers.sh \
  ~/.claude/harness/design.sh \
  ~/.claude/harness/plan.sh \
  ~/.claude/hooks/harness-router.py \
  ~/.claude/hooks/harness-session-start.py \
  ~/.claude/hooks/agent-boundary.py \
  ~/.claude/hooks/orch-rules-first.py; do
  [ -f "$f" ] && echo "OK $f" || echo "MISSING $f"
done
```

### 2. 프로젝트 설정 확인

```bash
[ -f ".claude/harness.config.json" ] && echo "OK harness.config.json" || echo "MISSING harness.config.json"
[ -f ".claude/settings.json" ] && echo "OK settings.json" || echo "MISSING settings.json"
PREFIX=$(python3 -c "import json,os; print(json.load(open('.claude/harness.config.json')).get('prefix','proj'))" 2>/dev/null || echo "proj")
echo "PREFIX: $PREFIX"
```

### 3. 스크립트 문법 검증

```bash
bash -n ~/.claude/harness/executor.sh && echo "OK executor syntax" || echo "FAIL executor syntax"
bash -n ~/.claude/harness/impl.sh && echo "OK impl syntax" || echo "FAIL impl syntax"
bash -n ~/.claude/harness/impl_simple.sh && echo "OK impl_simple syntax" || echo "FAIL impl_simple syntax"
bash -n ~/.claude/harness/impl_std.sh && echo "OK impl_std syntax" || echo "FAIL impl_std syntax"
bash -n ~/.claude/harness/impl_deep.sh && echo "OK impl_deep syntax" || echo "FAIL impl_deep syntax"
bash -n ~/.claude/harness/impl_helpers.sh && echo "OK impl_helpers syntax" || echo "FAIL impl_helpers syntax"
bash -n ~/.claude/harness/design.sh && echo "OK design syntax" || echo "FAIL design syntax"
bash -n ~/.claude/harness/plan.sh && echo "OK plan syntax" || echo "FAIL plan syntax"
python3 -m py_compile ~/.claude/hooks/harness-router.py && echo "OK router syntax" || echo "FAIL router syntax"
python3 -m py_compile ~/.claude/hooks/harness-session-start.py && echo "OK session-start syntax" || echo "FAIL session-start syntax"
python3 -m py_compile ~/.claude/hooks/agent-boundary.py && echo "OK agent-boundary syntax" || echo "FAIL agent-boundary syntax"
```

### 4. 플래그 읽기/쓰기 dry-run

```bash
PREFIX=$(python3 -c "import json,os; print(json.load(open('.claude/harness.config.json')).get('prefix','proj'))" 2>/dev/null || echo "proj")
touch /tmp/${PREFIX}_smoke_test && echo "OK flag write" || echo "FAIL flag write"
[ -f /tmp/${PREFIX}_smoke_test ] && echo "OK flag read" || echo "FAIL flag read"
rm -f /tmp/${PREFIX}_smoke_test && echo "OK flag cleanup"
```

### 5. hooks 설정 확인

```bash
python3 -c "
import json
s = json.load(open('.claude/settings.json'))
hooks = s.get('hooks', {})
triggers = list(hooks.keys())
print('hooks triggers:', triggers)
has_pre = any('PreToolUse' in t for t in triggers)
has_post = any('PostToolUse' in t for t in triggers)
print('PreToolUse:', 'OK' if has_pre else 'MISSING')
print('PostToolUse:', 'OK' if has_post else 'MISSING')
" 2>/dev/null || echo "FAIL settings.json 파싱 실패"
```

## 결과 판정

모든 항목을 표로 정리하고 최종 판정을 출력한다:

- **SMOKE_PASS** — 모든 항목 OK
- **SMOKE_FAIL** — 하나라도 MISSING / FAIL 존재 → 해당 항목과 수정 방법 안내
