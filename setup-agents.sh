#!/bin/bash
# ~/.claude/setup-agents.sh
# 신규 프로젝트 루트에서 실행: bash ~/.claude/setup-agents.sh
# .claude/agents/ 아래 9개 에이전트 파일을 생성한다.

set -e

# 선택적 인수
# --repo <owner/repo> : GitHub repo — architect/qa 에이전트에 pre-fill, 마일스톤 자동 생성에 사용
REPO=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    *) shift ;;
  esac
done

REPO_DISPLAY="${REPO:-[채우기: owner/repo-name]}"

AGENTS_DIR=".claude/agents"
mkdir -p "$AGENTS_DIR"

echo "🔧 에이전트 파일 생성 중..."

# ── test-engineer ─────────────────────────────────────────
cat > "$AGENTS_DIR/test-engineer.md" << 'EOF'
---
name: test-engineer
model: sonnet
description: impl 파일과 구현 코드를 기반으로 테스트 코드를 작성하고 실행하는 에이전트. engineer 완료 후 validator 전에 호출한다.
tools: Read, Write, Bash, Glob, Grep
---

## 공통 지침

<!-- /agent-downSync 실행 시 이 섹션이 채워집니다 -->

---

## 프로젝트 특화 지침

<!--
채워야 할 내용:
- 테스트 실행 명령어 (예: npm test, npx vitest)
- mock 사용 금지 여부 (DB/외부 API mock 여부)
- 우선 테스트 대상 (핵심 비즈니스 로직, 상태 변화 등)
- 테스트 파일 위치 (예: src/__tests__/)
-->
EOF

# ── pr-reviewer ───────────────────────────────────────────
cat > "$AGENTS_DIR/pr-reviewer.md" << 'EOF'
---
name: pr-reviewer
model: opus
description: validator PASS 이후 코드 품질을 리뷰하는 에이전트. 패턴·컨벤션·가독성·기술부채 검토. LGTM / CHANGES_REQUESTED 판정. 파일을 수정하지 않는다.
tools: Read, Glob, Grep
---

## 공통 지침

<!-- /agent-downSync 실행 시 이 섹션이 채워집니다 -->

---

## 프로젝트 특화 지침

<!--
채워야 할 내용:
- 프로젝트 컨벤션 (예: 인라인 style 금지, CSS 변수 사용 필수)
- 금지 패턴 (예: any 타입 사용 금지, console.log 잔류 금지)
- 외부 라이브러리 직접 import 금지 목록 (래퍼 함수 사용 강제)
- 샌드박스/개발환경 분기 확인 항목
-->
EOF

# ── architect ─────────────────────────────────────────────
cat > "$AGENTS_DIR/architect.md" << EOF
---
name: architect
model: sonnet
description: 새 모듈 구현 계획 파일을 작성하는 설계 에이전트. 기존 설계 문서를 읽고 프로젝트 패턴에 맞는 impl 파일을 생성한다.
tools: Read, Glob, Grep, Write, Edit, mcp__github__create_issue, mcp__github__list_issues, mcp__github__get_issue, mcp__github__update_issue, Bash
---

## 공통 지침

<!-- /agent-downSync 실행 시 이 섹션이 채워집니다 -->

---

## 프로젝트 특화 지침

- GitHub repo: \`${REPO_DISPLAY}\`
- 현재 버전 레이블: \`v01\`
- 컨텍스트 파악 순서: CLAUDE.md → backlog.md → stories.md → impl/
- impl 파일 경로 패턴: \`docs/milestones/vNN/epics/epic-NN-*/impl/NN-*.md\`

<!--
추가로 채워야 할 내용:
- 외부 SDK MCP 확인 강제 여부 (.d.ts 우선 확인 여부)
- 프로젝트 특화 설계 문서 이름 (예: game-logic, domain-logic, api-spec)
-->
EOF

# ── engineer ──────────────────────────────────────────────
cat > "$AGENTS_DIR/engineer.md" << 'EOF'
---
name: engineer
model: sonnet
description: 지정된 모듈의 impl 계획 파일을 읽고 실제 코드를 구현하는 에이전트.
tools: Read, Write, Edit, Bash, Glob, Grep
---

## 공통 지침

<!-- /agent-downSync 실행 시 이 섹션이 채워집니다 -->

---

## 프로젝트 특화 지침

<!--
채워야 할 내용:
- GitHub Issues 조회 명령어 (예: gh issue view #NN --repo owner/repo)
- 외부 SDK 래퍼 강제 패턴 (예: SDK 직접 import 금지, src/lib/sdk.ts 래퍼 사용)
- 샌드박스 분기 방법 (예: IS_SANDBOX=import.meta.env.DEV)
- 의존성 규칙 (예: src/store → src/engine 직접 import 금지, store 경유 강제)
- 커밋 전 테스트 명령어 (예: npm run typecheck && npm test)
-->
EOF

# ── validator ─────────────────────────────────────────────
cat > "$AGENTS_DIR/validator.md" << 'EOF'
---
name: validator
model: sonnet
description: 구현된 코드가 impl 설계 의도에 맞게 구현되었는지 검증하는 에이전트. PASS/FAIL을 판정한다. 파일을 수정하지 않는다.
tools: Read, Glob, Grep
---

## 공통 지침

<!-- /agent-downSync 실행 시 이 섹션이 채워집니다 -->

---

## 프로젝트 특화 지침

<!--
채워야 할 내용:
- 의존성 규칙 (예: src/components → src/store 직접 import 금지)
- 금지 패턴 (예: any 타입, barrel import 사이클, 전역 변수)
- impl 파일 경로 패턴 (예: docs/milestones/vNN/epics/epic-NN-*/impl/)
- 특수 체크 항목 (예: IS_SANDBOX 분기 누락 여부, SDK 직접 import 여부)
-->
EOF

# ── designer ──────────────────────────────────────────────
cat > "$AGENTS_DIR/designer.md" << 'EOF'
---
name: designer
model: sonnet
description: UI 디자인 에이전트. Pencil MCP 캔버스 위에 서로 다른 미적 방향의 3가지 variant를 생성한다. 사용자 확정 후 Phase 4에서 코드를 별도 생성한다.
tools: Read, Glob, Grep, Write
---

## 공통 지침

<!-- /agent-downSync 실행 시 이 섹션이 채워집니다 -->

---

## 프로젝트 특화 지침

<!--
채워야 할 내용:
- 브랜드 컬러/폰트 제약 (예: 토스 색상 팔레트, TDS 면제 여부)
- 플랫폼 제약 (예: 모바일 WebView 전용 — 데스크톱 레이아웃 불필요)
- PRD에서 지정된 UI 키워드 (예: "4개 색깔 버튼", "시퀀스 표시 영역")
- 코드 출력 경로 (기본값: design-variants/)
-->
EOF

# ── design-critic ─────────────────────────────────────────
cat > "$AGENTS_DIR/design-critic.md" << 'EOF'
---
name: design-critic
model: opus
description: 디자인 심사 에이전트. designer가 Pencil MCP로 생성한 3개 variant 스크린샷을 4개 기준으로 점수화하고 PICK/ITERATE/ESCALATE를 판정한다. 파일을 수정하지 않는다.
tools: Read, Glob, Grep
---

## 공통 지침

<!-- /agent-downSync 실행 시 이 섹션이 채워집니다 -->

---

## 프로젝트 특화 지침

<!--
채워야 할 내용:
- 심사 기준 (예: PRD 원칙 준수 여부, 접근성 점수 기준 ≥ 70)
- PICK 판정 시 architect Mode B 자동 트리거 여부
- ITERATE vs ESCALATE 기준 (예: 3회 이상 ITERATE → ESCALATE)
-->
EOF

# ── qa ────────────────────────────────────────────────────
cat > "$AGENTS_DIR/qa.md" << EOF
---
name: qa
model: sonnet
description: 이슈를 접수해 원인을 분석하고 메인 Claude에게 라우팅 추천을 전달하는 QA 에이전트. 코드를 직접 수정하지 않는다.
tools: Read, Glob, Grep, Agent, mcp__github__create_issue
---

## 공통 지침

<!-- /agent-downSync 실행 시 이 섹션이 채워집니다 -->

---

## 프로젝트 특화 지침

- GitHub repo: \`${REPO_DISPLAY}\`
- 마일스톤 구조: Story / Bugs / Epics / Feature + 버전 레이블 v01
- 버그 이슈 등록: 레이블 \`bug\` + 버전 레이블, 마일스톤 \`Bugs\`

<!--
추가로 채워야 할 내용:
- CRITICAL 버그 기준 (예: 게임 진행 불가, 데이터 소실, 인증 실패)
- 라우팅 결정 기준 (예: 재현 불가 → 추가 정보 요청, 설계 문제 → architect)
-->
EOF

# ── security-reviewer ────────────────────────────────────
SR_SRC="$HOME/.claude/agents/security-reviewer.md"
SR_LOCAL="$AGENTS_DIR/security-reviewer.md"
if [ -f "$SR_SRC" ] && [ ! -f "$SR_LOCAL" ]; then
  cp "$SR_SRC" "$SR_LOCAL"
  echo "📄 security-reviewer.md 복사 완료"
fi

# ── harness/executor.sh (셸 스크립트 복사) ───────────────
HE_SRC="$HOME/.claude/harness/executor.sh"
HE_LOCAL="$AGENTS_DIR/../harness/executor.sh"
if [ -f "$HE_SRC" ]; then
  cp "$HE_SRC" "$HE_LOCAL"
  chmod +x "$HE_LOCAL"
  echo "📄 harness/executor.sh 복사 완료"
else
  echo "⚠️  ~/.claude/harness/executor.sh 없음 — 복사 스킵"
fi

# ── CLAUDE.md 베이스 복사 ────────────────────────────────
if [ ! -f "CLAUDE.md" ]; then
  cp ~/.claude/templates/CLAUDE-base.md CLAUDE.md
  # repo가 제공된 경우 CLAUDE.md의 git remote 섹션 pre-fill
  if [ -n "$REPO" ]; then
    sed -i '' "s|\[채우기: owner/repo\]|${REPO}|g" CLAUDE.md 2>/dev/null || true
  fi
  echo "📄 CLAUDE.md 생성 (베이스 템플릿에서 복사)"
else
  echo "📄 CLAUDE.md 이미 존재 — 건너뜀"
fi

# ── GitHub 마일스톤 자동 생성 ─────────────────────────────
if [ -n "$REPO" ]; then
  echo ""
  echo "🏷️  GitHub 마일스톤 생성 중 (${REPO})..."
  MILESTONE_CREATED=0
  MILESTONE_SKIPPED=0
  for M in "Story" "Bugs" "Epics" "Feature"; do
    RESULT=$(gh api "repos/${REPO}/milestones" -f title="$M" -f state="open" 2>&1)
    if echo "$RESULT" | grep -q '"number"'; then
      echo "  ✅ $M"
      MILESTONE_CREATED=$((MILESTONE_CREATED + 1))
    elif echo "$RESULT" | grep -q 'already_exists\|Validation Failed'; then
      echo "  ⚠️  $M (이미 존재)"
      MILESTONE_SKIPPED=$((MILESTONE_SKIPPED + 1))
    else
      echo "  ❌ $M 실패 — gh auth login 확인 필요"
    fi
  done

  echo ""
  echo "🏷️  GitHub 레이블 생성 중..."
  for LABEL_INFO in "v01:0075ca" "bug:d73a4a" "feat:a2eeef"; do
    LABEL_NAME="${LABEL_INFO%%:*}"
    LABEL_COLOR="${LABEL_INFO##*:}"
    RESULT=$(gh api "repos/${REPO}/labels" -f name="$LABEL_NAME" -f color="$LABEL_COLOR" 2>&1)
    if echo "$RESULT" | grep -q '"name"'; then
      echo "  ✅ $LABEL_NAME"
    elif echo "$RESULT" | grep -q 'already_exists\|Validation Failed'; then
      echo "  ⚠️  $LABEL_NAME (이미 존재)"
    else
      echo "  ❌ $LABEL_NAME 실패"
    fi
  done
fi

echo ""
echo "✅ 생성 완료: $AGENTS_DIR/"
ls "$AGENTS_DIR/"
echo ""
echo "다음 단계:"
echo "  1. CLAUDE.md 에서 [채우기] 항목을 프로젝트에 맞게 채우세요."
echo "  2. 각 에이전트 파일의 '프로젝트 특화 지침' 섹션에 프로젝트별 내용을 추가하세요."
echo "     - test-engineer.md: 테스트 명령어, mock 패턴, 우선 테스트 대상"
echo "     - pr-reviewer.md: 프로젝트 컨벤션, 금지 패턴"
echo "     - engineer.md: SDK 래퍼 패턴, 샌드박스 분기, 의존성 규칙"
echo "     - validator.md: 금지 패턴, impl 경로 패턴"
echo "     - designer.md: 브랜드/플랫폼 제약, PRD UI 키워드, 코드 출력 경로"
echo "     - design-critic.md: 심사 기준, ITERATE vs ESCALATE 판단 기준"
echo "  3. product-planner 에이전트와 대화해서 PRD/TRD를 작성하세요."
