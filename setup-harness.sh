#!/bin/bash
# ~/.claude/setup-harness.sh
# 신규 프로젝트 루트에서 실행: bash ~/.claude/setup-harness.sh
# .claude/settings.json 에 Harness Engineering PreToolUse/PostToolUse 훅 세트를 설치한다.
#
# UserPromptSubmit / SessionStart 는 ~/.claude/settings.json(전역)에서 관리.
# 이 스크립트는 프로젝트별 게이트 훅만 생성한다.
#
# 설치되는 훅:
#   PreToolUse(Edit/Write) — docs/* + src/** 에이전트 소유 파일 물리적 차단
#   PreToolUse(Bash)       — git commit 전 pr-reviewer LGTM 확인
#   PreToolUse(Agent)      — 이슈번호 필수 + 에이전트 실행 순서 6단계 게이트
#   PostToolUse(Bash)      — commit 성공 후 플래그 정리
#   PostToolUse(Agent)     — 플래그 생성/삭제 + 문서 신선도/PRD 대조 경고

set -e

# 선택적 인수
# --doc-name <name>  : 핵심 설계 문서 이름 (docs/<name>.md), Mode C 신선도 체크에 사용 (기본값: domain-logic)
# --repo <owner/repo>: GitHub repo — milestone 생성 시 setup-agents.sh에 전달용 (이 스크립트에서 직접 사용하지 않음)
DOC_NAME="domain-logic"
REPO=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --doc-name) DOC_NAME="$2"; shift 2 ;;
    --repo)     REPO="$2";     shift 2 ;;
    *) shift ;;
  esac
done

SETTINGS_FILE=".claude/settings.json"
CONFIG_FILE=".claude/harness.config.json"
mkdir -p .claude

# 프로젝트 prefix 유도: 디렉토리명 → 소문자 → 영숫자만 → 최대 6자
RAW=$(basename "$PWD")
PREFIX=$(echo "$RAW" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9' | cut -c1-6)
if [ -z "$PREFIX" ]; then
  PREFIX="proj"
fi

echo "📌 프로젝트 prefix: ${PREFIX}_"
echo "📄 설정 파일: $SETTINGS_FILE"
echo "📋 핵심 설계 문서: docs/${DOC_NAME}.md"

# harness.config.json 생성 (없으면)
if [ ! -f "$CONFIG_FILE" ]; then
  echo "{\"prefix\": \"${PREFIX}\"}" > "$CONFIG_FILE"
  echo "📄 $CONFIG_FILE 생성 완료"
else
  echo "ℹ️  $CONFIG_FILE 이미 존재 — 유지"
fi

# 기존 settings.json 에서 allowedTools 보존
EXISTING_ALLOWED="[]"
if [ -f "$SETTINGS_FILE" ]; then
  EXISTING_ALLOWED=$(python3 -c "
import json, sys
with open('$SETTINGS_FILE') as f:
    d = json.load(f)
print(json.dumps(d.get('allowedTools', [])))
" 2>/dev/null || echo "[]")
  echo "⚠️  기존 settings.json 감지 — allowedTools 보존, hooks 덮어씀"
fi

# Python으로 settings.json 생성
python3 << PYEOF
import json

prefix = "${PREFIX}"
p = prefix
doc_name = "${DOC_NAME}"

hooks = {
    "PreToolUse": [
        # ── Edit: 에이전트 소유 파일 보호 ──────────────────────────────────
        {
            "matcher": "Edit",
            "hooks": [
                # docs/* 설계 문서 차단 (architect/designer/product-planner 소유) — /tmp/{p}_architect_active 플래그 시 통과
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,re,os; d=json.load(sys.stdin); fp=d.get('tool_input',{{}}).get('file_path',''); pattern=r'(docs/(architecture|game-logic|db-schema|sdk|ui-spec|domain-logic|reference)[^/]*[.]md|(^|/)prd[.]md|(^|/)trd[.]md)'; print(json.dumps({{'hookSpecificOutput':{{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':f'❌ {{fp}} 는 에이전트 소유 파일. 직접 수정 금지 → architect/designer/product-planner 에이전트 호출.'}}}})) if re.search(pattern, fp) and not os.path.exists('/tmp/{p}_architect_active') else None\" 2>/dev/null || true"},
                # src/** 소스 차단 (engineer 소유), src/__tests__/ 제외, /tmp/{p}_harness_active 시 통과
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,re,os; d=json.load(sys.stdin); fp=d.get('tool_input',{{}}).get('file_path',''); is_src=bool(re.search(r'(^|/)src/',fp)); is_test=bool(re.search(r'(^|/)src/__tests__/',fp)); harness_active=os.path.exists('/tmp/{p}_harness_active'); print(json.dumps({{'hookSpecificOutput':{{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':'❌ src/** 는 engineer 에이전트 소유. 직접 수정 금지 → architect Mode B → validator Mode A PASS → engineer 순서로 진행.'}}}})) if is_src and not is_test and not harness_active else None\" 2>/dev/null || true"},
            ]
        },
        # ── Write: Edit와 동일 보호 ───────────────────────────────────────
        {
            "matcher": "Write",
            "hooks": [
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,re,os; d=json.load(sys.stdin); fp=d.get('tool_input',{{}}).get('file_path',''); pattern=r'(docs/(architecture|game-logic|db-schema|sdk|ui-spec|domain-logic|reference)[^/]*[.]md|(^|/)prd[.]md|(^|/)trd[.]md)'; print(json.dumps({{'hookSpecificOutput':{{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':f'❌ {{fp}} 는 에이전트 소유 파일. 직접 수정 금지 → architect/designer/product-planner 에이전트 호출.'}}}})) if re.search(pattern, fp) and not os.path.exists('/tmp/{p}_architect_active') else None\" 2>/dev/null || true"},
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,re,os; d=json.load(sys.stdin); fp=d.get('tool_input',{{}}).get('file_path',''); is_src=bool(re.search(r'(^|/)src/',fp)); is_test=bool(re.search(r'(^|/)src/__tests__/',fp)); print(json.dumps({{'hookSpecificOutput':{{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':'❌ src/** 는 engineer 에이전트 소유. 직접 수정 금지 → architect Mode B → validator Mode A PASS → engineer 순서로 진행.'}}}})) if is_src and not is_test else None\" 2>/dev/null || true"},
            ]
        },
        # ── Bash: git commit 전 LGTM 확인 ────────────────────────────────
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "timeout": 5,
                "command": f"python3 -c \"import sys,json,os,re,subprocess; d=json.load(sys.stdin); cmd=d.get('tool_input',{{}}).get('command',''); is_commit=bool(re.search(r'git commit',cmd)); staged=subprocess.run(['git','diff','--cached','--name-only'],capture_output=True,text=True).stdout if is_commit else ''; has_src=bool(re.search(r'^src/',staged,re.MULTILINE)); print(json.dumps({{'hookSpecificOutput':{{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':'❌ git commit 전 pr-reviewer LGTM 필요. /tmp/{p}_pr_reviewer_lgtm 없음.'}}}})) if is_commit and has_src and not os.path.exists('/tmp/{p}_pr_reviewer_lgtm') else None\" 2>/dev/null || true"
            }]
        },
        # ── Agent: 에이전트 실행 순서 게이트 (6단계) ──────────────────────
        {
            "matcher": "Agent",
            "hooks": [
                # 1. architect/engineer/designer 호출 전 GitHub 이슈 번호 필수
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,re; d=json.load(sys.stdin); t=d.get('tool_input',{{}}); a=t.get('subagent_type'); prompt=t.get('prompt',''); has_issue=bool(re.search('#[0-9]+',prompt)); print(json.dumps({{'hookSpecificOutput':{{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':f'❌ {{a}} 호출 전 GitHub 이슈 등록 필요. 프롬프트에 이슈 번호(#NNN)가 없습니다.'}}}})) if a in ['architect','engineer','designer'] and not has_issue else None\" 2>/dev/null || true"},
                # 2. architect 호출 시 Mode A/B/C/D/E 명시 필수
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,re; d=json.load(sys.stdin); t=d.get('tool_input',{{}}); a=t.get('subagent_type'); prompt=t.get('prompt',''); r=re.search(r'Mode [A-E]',prompt,re.IGNORECASE); print(json.dumps({{'hookSpecificOutput':{{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':'❌ architect 호출 시 Mode A/B/C/D/E를 프롬프트에 명시하세요.'}}}})) if a=='architect' and not r else None\" 2>/dev/null || true"},
                # 3. engineer 전 validator Mode A PASS 필요
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,os; d=json.load(sys.stdin); a=d.get('tool_input',{{}}).get('subagent_type'); print(json.dumps({{'hookSpecificOutput':{{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':'❌ engineer 전 validator Mode A PASS 필요. /tmp/{p}_validator_a_passed 없음.'}}}})) if a=='engineer' and not os.path.exists('/tmp/{p}_validator_a_passed') else None\" 2>/dev/null || true"},
                # 3b. engineer는 harness-executor 경유 필수 (직접 호출 차단)
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,os; d=json.load(sys.stdin); a=d.get('tool_input',{{}}).get('subagent_type'); ha=os.path.exists('/tmp/{p}_harness_active'); print(json.dumps({{'hookSpecificOutput':{{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':'❌ engineer는 harness-executor를 통해서만 호출 가능. /tmp/{p}_harness_active 없음. 메인 Claude에서 직접 engineer 호출 금지 — harness-executor에 impl 파일 경로 + 이슈 번호를 전달하라.'}}}})) if a=='engineer' and not ha else None\" 2>/dev/null || true"},
                # 4. designer 실행 후 design-critic PICK 전까지 engineer 차단
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,os; d=json.load(sys.stdin); a=d.get('tool_input',{{}}).get('subagent_type'); dr=os.path.exists('/tmp/{p}_designer_ran'); cp=os.path.exists('/tmp/{p}_design_critic_passed'); print(json.dumps({{'hookSpecificOutput':{{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':'❌ designer 실행 후 engineer 바로 불가. 올바른 순서: design-critic PICK → 유저 승인 → architect impl 계획 → validator Mode A PASS → engineer'}}}})) if a=='engineer' and dr and not cp else None\" 2>/dev/null || true"},
                # 5. validator Mode B 전 test-engineer PASS 필요
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,re,os; d=json.load(sys.stdin); t=d.get('tool_input',{{}}); a=t.get('subagent_type'); prompt=t.get('prompt',''); mode_b=bool(re.search(r'Mode B',prompt,re.IGNORECASE)); print(json.dumps({{'hookSpecificOutput':{{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':'❌ validator Mode B 전 test-engineer PASS 필요. /tmp/{p}_test_engineer_passed 없음.'}}}})) if a=='validator' and mode_b and not os.path.exists('/tmp/{p}_test_engineer_passed') else None\" 2>/dev/null || true"},
                # 6. pr-reviewer 전 validator Mode B PASS 필요
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,os; d=json.load(sys.stdin); a=d.get('tool_input',{{}}).get('subagent_type'); print(json.dumps({{'hookSpecificOutput':{{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':'❌ pr-reviewer 전 validator Mode B PASS 필요. /tmp/{p}_validator_b_passed 없음.'}}}})) if a=='pr-reviewer' and not os.path.exists('/tmp/{p}_validator_b_passed') else None\" 2>/dev/null || true"},
                # 7. 백그라운드 에이전트 금지 (포그라운드 전용)
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json; d=json.load(sys.stdin); t=d.get('tool_input',{{}}); bg=t.get('run_in_background',False); a=t.get('subagent_type','?'); print(json.dumps({{'hookSpecificOutput':{{'hookEventName':'PreToolUse','permissionDecision':'deny','permissionDecisionReason':f'❌ 백그라운드 에이전트 금지. {{a}} 호출 시 run_in_background=false 필수. 포그라운드에서만 실행해야 중단 가능.'}}}})) if bg else None\" 2>/dev/null || true"},
                # 8. 에이전트 호출 로그 (caller → subagent_type | prompt 앞 80자)
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,os; from datetime import datetime; d=json.load(sys.stdin); t=d.get('tool_input',{{}}); a=t.get('subagent_type','?'); pr=t.get('prompt','')[:80].replace('\\\\n',' '); caller='harness-executor' if os.path.exists('/tmp/{p}_harness_active') else 'main-claude'; ts=datetime.now().strftime('%H:%M:%S'); line=f'[{{ts}}] {{caller}} → {{a}} | {{pr}}\\\\n'; open('/tmp/{p}-agent-calls.log','a').write(line)\" 2>/dev/null || true"},
            ]
        }
    ],
    "PostToolUse": [
        # ── Bash: commit 성공 후 플래그 정리 ────────────────────────────
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "timeout": 5,
                "command": f"python3 -c \"import sys,json,re,os; d=json.load(sys.stdin); cmd=d.get('tool_input',{{}}).get('command',''); resp=str(d.get('tool_response','')); is_commit=bool(re.search(r'git commit',cmd)); success='error' not in resp.lower() and 'failed' not in resp.lower(); [os.remove(f) for f in ['/tmp/{p}_pr_reviewer_lgtm','/tmp/{p}_test_engineer_passed'] if os.path.exists(f)] if is_commit and success else None\" 2>/dev/null || true"
            }]
        },
        # ── Agent: 플래그 생성/삭제 + 경고 ──────────────────────────────
        {
            "matcher": "Agent",
            "hooks": [
                # validator PASS → Mode A/B 플래그 생성
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,re,os; d=json.load(sys.stdin); inp=d.get('tool_input',{{}}); resp=str(d.get('tool_response','')); prompt=inp.get('prompt',''); [open('/tmp/{p}_validator_a_passed','w').close() if re.search(r'Mode A',prompt,re.IGNORECASE) else None, open('/tmp/{p}_validator_b_passed','w').close() if re.search(r'Mode B',prompt,re.IGNORECASE) else None] if inp.get('subagent_type')=='validator' and 'PASS' in resp else None\" 2>/dev/null || true"},
                # test-engineer TESTS_PASS → 플래그 생성
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,os; d=json.load(sys.stdin); inp=d.get('tool_input',{{}}); resp=str(d.get('tool_response','')); open('/tmp/{p}_test_engineer_passed','w').close() if inp.get('subagent_type')=='test-engineer' and 'TESTS_PASS' in resp else None\" 2>/dev/null || true"},
                # pr-reviewer LGTM → 플래그 생성
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,os; d=json.load(sys.stdin); inp=d.get('tool_input',{{}}); resp=str(d.get('tool_response','')); open('/tmp/{p}_pr_reviewer_lgtm','w').close() if inp.get('subagent_type')=='pr-reviewer' and 'LGTM' in resp and 'CHANGES_REQUESTED' not in resp else None\" 2>/dev/null || true"},
                # architect Mode B 완료 → 전체 플래그 초기화 (새 구현 사이클 시작)
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,re,os; d=json.load(sys.stdin); inp=d.get('tool_input',{{}}); a=inp.get('subagent_type'); prompt=inp.get('prompt',''); mode_b=bool(re.search(r'Mode B',prompt,re.IGNORECASE)); [os.remove(f) for f in ['/tmp/{p}_validator_a_passed','/tmp/{p}_validator_b_passed','/tmp/{p}_test_engineer_passed','/tmp/{p}_pr_reviewer_lgtm','/tmp/{p}_designer_ran','/tmp/{p}_design_critic_passed'] if os.path.exists(f)] if a=='architect' and mode_b else None\" 2>/dev/null || true"},
                # engineer 완료 → test/validator_b/pr 플래그 삭제 (재검증 강제)
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,os; d=json.load(sys.stdin); a=d.get('tool_input',{{}}).get('subagent_type'); [os.remove(f) for f in ['/tmp/{p}_test_engineer_passed','/tmp/{p}_pr_reviewer_lgtm','/tmp/{p}_validator_b_passed'] if os.path.exists(f)] if a=='engineer' else None\" 2>/dev/null || true"},
                # harness-executor 완료 → harness_active 플래그 삭제
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,os; d=json.load(sys.stdin); a=d.get('tool_input',{{}}).get('subagent_type'); [os.remove('/tmp/{p}_harness_active') for _ in [1] if os.path.exists('/tmp/{p}_harness_active')] if a=='harness-executor' else None\" 2>/dev/null || true"},
                # architect 완료 → architect_active 플래그 삭제
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,os; d=json.load(sys.stdin); a=d.get('tool_input',{{}}).get('subagent_type'); [os.remove('/tmp/{p}_architect_active') for _ in [1] if os.path.exists('/tmp/{p}_architect_active')] if a=='architect' else None\" 2>/dev/null || true"},
                # architect 완료 후 문서 신선도 경고 (trd.md / docs/test-plan.md / docs/{doc_name}.md)
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,os,time,re; d=json.load(sys.stdin); inp=d.get('tool_input',{{}}); a=inp.get('subagent_type'); prompt=inp.get('prompt',''); base=os.getcwd(); mode_ac=bool(re.search(r'Mode [AC]',prompt,re.IGNORECASE)); mode_b=bool(re.search(r'Mode B',prompt,re.IGNORECASE)); mode_c=bool(re.search(r'Mode C',prompt,re.IGNORECASE)); warns=[]; trd=os.path.join(base,'trd.md'); tp=os.path.join(base,'docs','test-plan.md'); dd=os.path.join(base,'docs','{doc_name}.md'); trd_age=int(time.time()-os.path.getmtime(trd)) if os.path.exists(trd) else None; tp_age=int(time.time()-os.path.getmtime(tp)) if os.path.exists(tp) else None; dd_age=int(time.time()-os.path.getmtime(dd)) if os.path.exists(dd) else None; warns.append('trd.md 미업데이트('+str(trd_age)+'초 전)') if mode_ac and trd_age and trd_age>120 else None; warns.append('docs/test-plan.md 미업데이트('+str(tp_age)+'초 전)') if mode_b and tp_age and tp_age>120 else None; warns.append('docs/{doc_name}.md 미업데이트('+str(dd_age)+'초 전) — 설계 문서 동기화 필요') if mode_c and dd_age and dd_age>120 else None; print(json.dumps({{'hookSpecificOutput':{{'hookEventName':'PostToolUse','additionalContext':'⚠️ [HARNESS] architect 완료 후 문서 미업데이트: '+', '.join(warns)+'. 현행화 규칙 확인.'}}}})) if a=='architect' and warns else None\" 2>/dev/null || true"},
                # designer 완료 → designer_ran 설정 + 이전 검증 플래그 초기화
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,os; d=json.load(sys.stdin); a=d.get('tool_input',{{}}).get('subagent_type'); [open('/tmp/{p}_designer_ran','w').close(), [os.remove('/tmp/{p}_design_critic_passed') for _ in [1] if os.path.exists('/tmp/{p}_design_critic_passed')], [os.remove('/tmp/{p}_validator_a_passed') for _ in [1] if os.path.exists('/tmp/{p}_validator_a_passed')]] if a=='designer' else None\" 2>/dev/null || true"},
                # design-critic PICK → 플래그 생성
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json; d=json.load(sys.stdin); inp=d.get('tool_input',{{}}); resp=str(d.get('tool_response','')); open('/tmp/{p}_design_critic_passed','w').close() if inp.get('subagent_type')=='design-critic' and 'PICK' in resp and 'ITERATE' not in resp and 'ESCALATE' not in resp else None\" 2>/dev/null || true"},
                # designer 결과에 PRD 대조 없으면 경고
                {"type": "command", "timeout": 5,
                    "command": f"python3 -c \"import sys,json,re; d=json.load(sys.stdin); inp=d.get('tool_input',{{}}); resp=str(d.get('tool_response','')); print(json.dumps({{'hookSpecificOutput':{{'hookEventName':'PostToolUse','additionalContext':'⚠️ [HARNESS] designer 결과에 PRD 대조 없음. PRD 위반 여부 확인 필요 — product-planner 에스컬레이션 고려. (orchestration-rules.md Step 0)'}}}})) if inp.get('subagent_type')=='designer' and not re.search(r'PRD|prd.md|기획자|product.planner',resp,re.IGNORECASE) else None\" 2>/dev/null || true"},
            ]
        }
    ]
}

import os
settings_path = "$SETTINGS_FILE"
existing_allowed = ${EXISTING_ALLOWED}

output = {
    "allowedTools": existing_allowed,
    "hooks": hooks
}

with open(settings_path, "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"✅ {settings_path} 생성 완료 (prefix: {prefix}_)")
PYEOF

# harness-loop.sh 복사
LOOP_SRC="$HOME/.claude/harness-loop.sh"
if [ -f "$LOOP_SRC" ]; then
  cp "$LOOP_SRC" ".claude/harness-loop.sh"
  chmod +x ".claude/harness-loop.sh"
  echo "  harness-loop.sh 복사 완료"
else
  echo "⚠️  ~/.claude/harness-loop.sh 없음 — 복사 스킵 (수동으로 추가 필요)"
fi

# harness-executor 프로젝트 에이전트 생성 (base 읽는 1줄짜리)
HE_BASE="$HOME/.claude/agents/harness-executor.md"
HE_LOCAL=".claude/agents/harness-executor.md"
if [ -f "$HE_BASE" ] && [ ! -f "$HE_LOCAL" ]; then
  cat > "$HE_LOCAL" <<HEEOF
---
name: harness-executor
model: opus
description: >
  5가지 mode(impl/impl2/design/bugfix/plan)로 전체 워크플로우를 자율 실행하는 에이전트.
tools: Read, Write, Glob, Grep, Bash
---

## Base 지침 (항상 먼저 읽기)

작업 시작 전 \`~/.claude/agents/harness-executor.md\`를 Read 툴로 읽고 그 지침을 모두 따른다.
아래는 이 프로젝트에만 적용되는 추가 지침이다.

## 프로젝트 특화

- prefix: \`${PREFIX}\` (\`.claude/harness.config.json\` 기준)
- impl 경로 패턴: \`docs/milestones/*/epics/epic-NN-*/impl/NN-*.md\`
HEEOF
  echo "  harness-executor.md 생성 완료 (prefix: ${PREFIX})"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Harness 훅 설치 완료"
echo ""
echo "  플래그 prefix : /tmp/${PREFIX}_*"
echo "  설정 파일     : $SETTINGS_FILE"
echo "  config 파일   : $CONFIG_FILE"
echo ""
echo "설치된 훅:"
echo "  PreToolUse(Edit/Write)  — docs/* + src/** 에이전트 소유 파일 보호"
echo "  PreToolUse(Bash)        — git commit 전 pr-reviewer LGTM 확인"
echo "  PreToolUse(Agent)       — 이슈번호 필수 + 에이전트 실행 순서 6단계 게이트"
echo "  PostToolUse(Bash)       — commit 성공 후 플래그 정리"
echo "  PostToolUse(Agent)      — 플래그 관리 + architect 문서 신선도 경고 + designer PRD 대조 경고"
echo ""
echo "전역 훅(UserPromptSubmit/SessionStart)은 ~/.claude/settings.json에서 자동 적용됨."
echo ""
echo "다음 단계:"
echo "  1. /init-agents  — 에이전트 파일(.claude/agents/) 초기화"
echo "  2. 각 에이전트 '프로젝트 특화 지침' 섹션 채우기"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
