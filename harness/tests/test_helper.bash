#!/bin/bash
# harness/tests/test_helper.bash
# BATS 테스트 공용 헬퍼 — mock 인프라 + 공통 setup/teardown

HARNESS_DIR="${BATS_TEST_DIRNAME}/.."
TEST_TMP=""

# ── setup: 각 테스트 전 격리 환경 생성 ─────────────────────────────────
common_setup() {
  TEST_TMP=$(mktemp -d)
  export PREFIX="test$$"
  export IMPL_FILE=""
  export ISSUE_NUM="999"
  export CONTEXT="test context"
  export DEPTH="auto"
  export CONSTRAINTS=""
  export BUG_DESC=""
  export BRANCH_TYPE="feat"
  export HARNESS_RESULT="unknown"
  export HARNESS_BRANCH=""
  export RUN_LOG=""
  export _HARNESS_RUN_START=0

  # /tmp 플래그 초기화
  rm -f /tmp/${PREFIX}_* 2>/dev/null

  # mock git repo
  export GIT_DIR="${TEST_TMP}/repo/.git"
  export GIT_WORK_TREE="${TEST_TMP}/repo"
  mkdir -p "${GIT_WORK_TREE}"
  git init "${GIT_WORK_TREE}" >/dev/null 2>&1
  cd "${GIT_WORK_TREE}"

  # .claude 디렉토리 (harness-memory 등)
  mkdir -p .claude
  printf "# Harness Memory\n\n## Known Failure Patterns\n\n## Success Patterns\n" > .claude/harness-memory.md
}

# ── teardown: 테스트 후 정리 ───────────────────────────────────────────
common_teardown() {
  rm -f /tmp/${PREFIX}_* 2>/dev/null
  rm -rf "$TEST_TMP" 2>/dev/null
  cd /
}

# ── _agent_call mock ──────────────────────────────────────────────────
# 테스트에서 _agent_call을 오버라이드해서 미리 정의된 출력을 반환
# 사용법: mock_agent_response <agent> <output_content>
MOCK_RESPONSES=()

mock_agent_response() {
  local agent="$1" content="$2"
  MOCK_RESPONSES+=("${agent}::${content}")
}

# _agent_call을 mock으로 대체 — source 후 호출
_agent_call() {
  local agent="$1" timeout="$2" prompt="$3" out_file="$4"
  local cost_file="${out_file%.txt}_cost.txt"
  echo "0" > "$cost_file"
  : > "$out_file"

  # MOCK_RESPONSES에서 agent에 맞는 응답 찾기
  for entry in "${MOCK_RESPONSES[@]}"; do
    local key="${entry%%::*}"
    local val="${entry#*::}"
    if [[ "$key" == "$agent" ]]; then
      echo "$val" > "$out_file"
      # 사용한 응답 제거 (FIFO)
      local new_arr=()
      local found=false
      for e in "${MOCK_RESPONSES[@]}"; do
        if [[ "$found" == "false" && "$e" == "$entry" ]]; then
          found=true
          continue
        fi
        new_arr+=("$e")
      done
      MOCK_RESPONSES=("${new_arr[@]}")
      return 0
    fi
  done

  # 매칭 없으면 빈 출력
  echo "[MOCK] no response for agent: $agent" > "$out_file"
  return 0
}

# ── git mock helpers ──────────────────────────────────────────────────
# 테스트 리포에 더미 파일 생성 + 커밋
create_test_commit() {
  local filename="${1:-test.txt}"
  echo "content $(date +%s)" > "${GIT_WORK_TREE}/${filename}"
  git -C "${GIT_WORK_TREE}" add "$filename" >/dev/null 2>&1
  git -C "${GIT_WORK_TREE}" commit -m "test commit" >/dev/null 2>&1
}

# 테스트 리포에 수정된 파일 생성 (커밋 안 함)
create_modified_file() {
  local filename="${1:-src/test.ts}"
  mkdir -p "${GIT_WORK_TREE}/$(dirname "$filename")"
  echo "modified $(date +%s)" > "${GIT_WORK_TREE}/${filename}"
}

# ── impl 파일 mock 생성 ──────────────────────────────────────────────
create_mock_impl() {
  local tags="${1:-(TEST)}"
  local impl_dir="${GIT_WORK_TREE}/docs/impl"
  mkdir -p "$impl_dir"
  local impl_path="${impl_dir}/01-test-module.md"
  cat > "$impl_path" <<IMPL
# 01-test-module

## 요구사항
- 테스트 기능 구현 ${tags}

## 수용 기준
- 기능이 정상 동작한다 ${tags}

## 결정 근거
- 테스트 목적
IMPL
  echo "$impl_path"
}
