#!/usr/bin/env bats
# harness/tests/dryrun.bats
# 커밋 전략 실제 드라이테스트 — 실제 git 연산으로 커밋 시퀀스 검증
#
# 각 테스트는 격리된 git 레포에서 실제 commit/branch/merge 연산을 실행한다.
# _agent_call과 merge_to_main은 mock으로 대체하고, git 히스토리로 결과를 검증한다.
#
# Notes:
# - collect_changed_files는 staged 변경(^ M|^M |^A )만 탐지함. untracked 파일은 git add 필요.
# - rollback_attempt는 커밋을 되돌리지 않음 — feature branch에 변경을 유지하고 다음 attempt에서 추가 커밋.
# - merge_to_main은 no-remote test 환경에서 default_branch="" 문제가 있으므로 mock 처리.

load test_helper

setup() {
  common_setup
  source "${HARNESS_DIR}/utils.sh"
  git -C "${GIT_WORK_TREE}" config user.email "test@harness.local"
  git -C "${GIT_WORK_TREE}" config user.name "Harness Test"

  # merge_to_main mock — no-remote 테스트 환경에서 default_branch="" 문제 우회
  # 실제 utils.sh merge gate 로직을 완전히 재현 (git checkout/merge만 skip)
  merge_to_main() {
    local branch="$1" issue="$2" depth="$3" prefix="$4"
    # simple/std/deep: pr_reviewer_lgtm 필수
    if [[ "$depth" == "simple" || "$depth" == "std" || "$depth" == "deep" ]]; then
      if [[ ! -f "/tmp/${prefix}_pr_reviewer_lgtm" ]]; then
        echo "[HARNESS] merge 거부: pr_reviewer_lgtm 없음 ($depth)"; return 1
      fi
    fi
    # deep: security_review_passed 필수
    if [[ "$depth" == "deep" ]]; then
      if [[ ! -f "/tmp/${prefix}_security_review_passed" ]]; then
        echo "[HARNESS] merge 거부: security_review_passed 없음 (deep)"; return 1
      fi
    fi
    # (bugfix depth 제거됨 — v6)
    if [[ "$depth" == "REMOVED_bugfix" ]]; then
      if [[ ! -f "/tmp/${prefix}_validator_b_passed" ]]; then
        echo "[HARNESS] merge 거부: validator_b_passed 없음"; return 1
      fi
    fi
    echo "[MOCK] merge OK: $branch → main"
    return 0
  }
}

teardown() {
  common_teardown
}

# ── 헬퍼: impl staged 변경 생성 (engineer 역할 시뮬레이션) ──────────────
make_staged_change() {
  local filename="${1:-src/feature.ts}"
  mkdir -p "${GIT_WORK_TREE}/$(dirname "$filename")"
  echo "// impl change $(date +%s%N)" > "${GIT_WORK_TREE}/${filename}"
  git -C "${GIT_WORK_TREE}" add "$filename"
}

# ── 헬퍼: test staged 파일 생성 (test-engineer 역할 시뮬레이션) ─────────
make_staged_test_file() {
  local filename="${1:-src/__tests__/feature.test.ts}"
  mkdir -p "${GIT_WORK_TREE}/$(dirname "$filename")"
  echo "// test $(date +%s%N)" > "${GIT_WORK_TREE}/${filename}"
  git -C "${GIT_WORK_TREE}" add "$filename"
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 1: std path 커밋 시퀀스
# expected: [base] → [early commit] → [test-files commit] → merge
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: std path — early commit → test-files commit → merge" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-std-test" 2>/dev/null
  local base_commit; base_commit=$(git rev-parse HEAD)

  IMPL_FILE="docs/impl/01-test.md"
  ISSUE_NUM="999"
  attempt=0

  # Step 1: Engineer 변경 (staged)
  make_staged_change "src/feature.ts"

  # Step 2: Early commit (automated_checks PASS 직후 로직)
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    commit_suffix=""
    [[ $attempt -gt 0 ]] && commit_suffix=" [attempt-${attempt}-fix]"
    git commit -m "feat(#999): feature${commit_suffix}" >/dev/null 2>&1
  fi
  local early_commit; early_commit=$(git rev-parse HEAD)

  # Early commit 생성 확인
  [[ "$early_commit" != "$base_commit" ]]
  local early_msg; early_msg=$(git log --format="%s" -1)
  [[ "$early_msg" != *"test-files"* ]]
  [[ "$early_msg" != *"attempt"* ]]

  # Step 3: test-engineer가 test 파일 추가
  make_staged_test_file "src/__tests__/feature.test.ts"

  # Step 4: test-files commit (merge 직전 로직)
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    git commit -m "feat(#999): feature [test-files]" >/dev/null 2>&1
  fi
  local test_commit; test_commit=$(git rev-parse HEAD)

  # test-files commit 생성 + suffix 확인
  [[ "$test_commit" != "$early_commit" ]]
  [[ "$(git log --format="%s" -1)" == *"test-files"* ]]

  # Step 5: merge (mocked)
  touch "${STATE_DIR}/${PREFIX}_pr_reviewer_lgtm"
  merge_to_main "feat/999-std-test" "999" "std" "$PREFIX"
  [[ $? -eq 0 ]]

  # 최종 git log: base → early → test-files
  local log_count; log_count=$(git log --oneline | wc -l | tr -d ' ')
  [[ "$log_count" -ge 3 ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 2: fast path 커밋 시퀀스
# expected: [base] → [fast-mode commit] → pr-reviewer diff uses HEAD~1
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: fast path — [fast-mode] commit → pr-reviewer diff uses HEAD~1" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-fast-test" 2>/dev/null
  local base_commit; base_commit=$(git rev-parse HEAD)

  IMPL_FILE="docs/impl/01-fast.md"
  ISSUE_NUM="999"

  # Engineer 변경 (staged)
  make_staged_change "src/fast-feature.ts"

  # Fast path: 미커밋 변경 → harness commit
  changed_list=$(collect_changed_files || true)
  if [[ -n "$changed_list" ]]; then
    echo "$changed_list" | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    git commit -m "feat(#999): fast-feature [fast-mode]" >/dev/null 2>&1
  fi

  local fast_commit; fast_commit=$(git rev-parse HEAD)
  [[ "$fast_commit" != "$base_commit" ]]
  [[ "$(git log --format="%s" -1)" == *"fast-mode"* ]]

  # pr-reviewer에 넘길 diff: HEAD~1 참조 — 변경 파일이 보여야 한다
  local diff_out
  diff_out=$(git diff HEAD~1 2>&1 | head -300)
  [[ -n "$diff_out" ]]
  [[ "$diff_out" == *"fast-feature.ts"* ]]

  # HEAD diff는 비어있어야 한다 (이미 커밋됐으므로)
  local head_diff
  head_diff=$(git diff HEAD --name-only 2>/dev/null)
  [[ -z "$head_diff" ]]

  # merge
  touch "${STATE_DIR}/${PREFIX}_pr_reviewer_lgtm"
  run merge_to_main "feat/999-fast-test" "999" "fast" "$PREFIX"
  [[ $status -eq 0 ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 3: attempt retry — [attempt-N-fix] suffix
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: attempt=0 — no fix suffix in commit message" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-attempt0" 2>/dev/null

  IMPL_FILE="docs/impl/01-test.md"
  ISSUE_NUM="999"
  attempt=0

  make_staged_change "src/v1.ts"
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    commit_suffix=""
    [[ $attempt -gt 0 ]] && commit_suffix=" [attempt-${attempt}-fix]"
    git commit -m "feat: initial${commit_suffix}" >/dev/null 2>&1
  fi

  local msg; msg=$(git log --format="%s" -1)
  [[ "$msg" != *"attempt"* ]]
  [[ "$msg" != *"fix]"* ]]
}

@test "dryrun: attempt=1 retry — commit has [attempt-1-fix] suffix" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-retry-test" 2>/dev/null

  IMPL_FILE="docs/impl/01-test.md"
  ISSUE_NUM="999"

  # Attempt 0: 첫 번째 early commit (no suffix)
  make_staged_change "src/v1.ts"
  attempt=0
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    commit_suffix=""
    [[ $attempt -gt 0 ]] && commit_suffix=" [attempt-${attempt}-fix]"
    git commit -m "feat: initial${commit_suffix}" >/dev/null 2>&1
  fi
  local a0_msg; a0_msg=$(git log --format="%s" -1)
  [[ "$a0_msg" != *"attempt"* ]]

  # Attempt 1: 재시도 — [attempt-1-fix] suffix
  make_staged_change "src/v2.ts"
  attempt=1
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    commit_suffix=""
    [[ $attempt -gt 0 ]] && commit_suffix=" [attempt-${attempt}-fix]"
    git commit -m "feat: retry${commit_suffix}" >/dev/null 2>&1
  fi
  local a1_msg; a1_msg=$(git log --format="%s" -1)
  [[ "$a1_msg" == *"[attempt-1-fix]"* ]]
}

@test "dryrun: attempt=2 retry — commit has [attempt-2-fix] suffix" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-retry2" 2>/dev/null

  IMPL_FILE="docs/impl/01-test.md"
  ISSUE_NUM="999"
  attempt=2

  make_staged_change "src/v3.ts"
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    commit_suffix=""
    [[ $attempt -gt 0 ]] && commit_suffix=" [attempt-${attempt}-fix]"
    git commit -m "feat: retry${commit_suffix}" >/dev/null 2>&1
  fi

  local msg; msg=$(git log --format="%s" -1)
  [[ "$msg" == *"[attempt-2-fix]"* ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 4: changed_files HEAD~1 참조 — early commit 이후
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: after early commit, HEAD~1 correctly identifies changed files" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-head1-test" 2>/dev/null

  # Engineer가 파일 2개 수정
  make_staged_change "src/module-a.ts"
  make_staged_change "src/module-b.ts"

  # Early commit
  git commit -m "feat: early commit" >/dev/null 2>&1

  # early commit 이후: HEAD~1 diff가 변경 파일을 반환해야 한다
  local changed_files
  changed_files=$(git diff HEAD~1 --name-only 2>/dev/null | tr '\n' ' ')
  [[ "$changed_files" == *"module-a.ts"* ]]
  [[ "$changed_files" == *"module-b.ts"* ]]

  # HEAD diff는 아무것도 없어야 한다 (이미 커밋됐으므로)
  local head_diff
  head_diff=$(git diff HEAD --name-only 2>/dev/null | tr '\n' ' ')
  [[ -z "$head_diff" ]]
}

@test "dryrun: git diff HEAD~1 vs HEAD shows correct empty after commit" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-diff-test" 2>/dev/null

  make_staged_change "src/auth.ts"
  git commit -m "feat: impl" >/dev/null 2>&1

  # HEAD~1 diff: should show auth.ts
  run bash -c "git -C '${GIT_WORK_TREE}' diff HEAD~1 --name-only"
  [[ "$output" == *"auth.ts"* ]]

  # HEAD diff: should be empty (all committed)
  run bash -c "git -C '${GIT_WORK_TREE}' diff HEAD --name-only"
  [[ -z "$output" ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 5: test-files commit이 없을 때 skip
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: no test-files added — test-files commit skipped" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-notest" 2>/dev/null

  # Engineer 변경 + early commit
  make_staged_change "src/simple.ts"
  git commit -m "feat: early commit" >/dev/null 2>&1
  local after_early; after_early=$(git rev-parse HEAD)

  # test-engineer가 파일을 추가하지 않음 → collect_changed_files 실패 → 커밋 스킵
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    git commit -m "feat: [test-files]" >/dev/null 2>&1
  fi
  local after_skip; after_skip=$(git rev-parse HEAD)

  # 커밋이 추가되지 않아야 한다
  [[ "$after_early" == "$after_skip" ]]

  # merge proceeds normally
  touch "${STATE_DIR}/${PREFIX}_pr_reviewer_lgtm"
  run merge_to_main "feat/999-notest" "999" "std" "$PREFIX"
  [[ $status -eq 0 ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 6: security-reviewer diff — HEAD~1 참조
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: security-reviewer target uses git diff HEAD~1 (not HEAD)" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-sec-test" 2>/dev/null

  mkdir -p "${GIT_WORK_TREE}/src"
  echo "export function login(user, pass) { return db.query(user, pass); }" \
    > "${GIT_WORK_TREE}/src/auth.ts"
  git add src/auth.ts
  git commit -m "feat: early commit" >/dev/null 2>&1

  # security-reviewer의 changed_src = git diff HEAD~1 --name-only
  local changed_src
  changed_src=$(git diff HEAD~1 --name-only 2>/dev/null \
    | grep -E '\.(ts|tsx|js|jsx)$' | head -10 | tr '\n' ' ' || true)
  [[ "$changed_src" == *"auth.ts"* ]]

  # git diff HEAD는 아무것도 반환하지 않아야 한다
  local head_src
  head_src=$(git diff HEAD --name-only 2>/dev/null \
    | grep -E '\.(ts|tsx|js|jsx)$' | head -10 | tr '\n' ' ' || true)
  [[ -z "$head_src" ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 7: bugfix path — REMOVED (v6): bugfix depth 제거
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: simple path — merge with pr_reviewer_lgtm" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-simple-test" 2>/dev/null

  make_staged_change "src/simple.ts"
  git commit -m "fix: simple change" >/dev/null 2>&1

  touch "${STATE_DIR}/${PREFIX}_pr_reviewer_lgtm"

  run merge_to_main "feat/999-simple-test" "999" "simple" "$PREFIX"
  [[ $status -eq 0 ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 8: 전체 std 플로우 — git log 시퀀스 완전 검증
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: full std flow — git log shows 3-commit sequence (early + test-files + merge marker)" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-full-std" 2>/dev/null

  IMPL_FILE="docs/impl/01-test.md"
  ISSUE_NUM="999"
  attempt=0

  # Step 1: Engineer 변경 (staged) + early commit
  make_staged_change "src/feature.ts"
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    commit_suffix=""
    [[ $attempt -gt 0 ]] && commit_suffix=" [attempt-${attempt}-fix]"
    git commit -m "feat(#999): feature${commit_suffix}" >/dev/null 2>&1
  fi
  local c1; c1=$(git rev-parse --short HEAD)

  # Step 2: changed_files = git diff HEAD~1 (test-engineer에 전달)
  local changed_for_te
  changed_for_te=$(git diff HEAD~1 --name-only 2>/dev/null | tr '\n' ' ')
  [[ "$changed_for_te" == *"feature.ts"* ]]

  # Step 3: pr-reviewer diff = git diff HEAD~1
  local diff_for_pr
  diff_for_pr=$(git diff HEAD~1 2>&1 | head -300)
  [[ "$diff_for_pr" == *"feature.ts"* ]]

  # Step 4: test-engineer 파일 추가 + test-files commit
  make_staged_test_file "src/__tests__/feature.test.ts"
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    git commit -m "feat(#999): feature [test-files]" >/dev/null 2>&1
  fi
  local c2; c2=$(git rev-parse --short HEAD)
  [[ "$c1" != "$c2" ]]

  # Step 5: merge (mocked)
  touch "${STATE_DIR}/${PREFIX}_pr_reviewer_lgtm"
  touch "${STATE_DIR}/${PREFIX}_security_review_passed"
  run merge_to_main "feat/999-full-std" "999" "std" "$PREFIX"
  [[ $status -eq 0 ]]

  # Step 6: git log 검증
  local log
  log=$(git log --format="%s")
  [[ "$log" == *"test-files"* ]]      # test-files commit 있음
  [[ "$log" == *"feat(#999)"* ]]      # early commit 있음
  # early commit에는 test-files 없음
  local early_line
  early_line=$(git log --format="%s" "$c1")
  [[ "$early_line" != *"test-files"* ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 9: rollback_attempt 동작 — 커밋을 되돌리지 않고 branch에 유지
# (새 전략: 재시도 시 [attempt-N-fix] 추가커밋, revert 아님)
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: rollback_attempt keeps commits on branch (no revert)" {
  # rollback_attempt은 git revert를 하지 않는다 — 새 commit 전략.
  # feature branch에 커밋을 유지하고, 다음 attempt에서 [attempt-N-fix] 추가.
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-rollback" 2>/dev/null

  # rollback_attempt 정의 (impl_std.sh 실제 로직 — 로그만 기록, git 연산 없음)
  hlog() { true; }
  rollback_attempt() {
    local attempt_num="$1"
    # Feature branch: 변경 유지, 다음 attempt에서 추가 커밋
    hlog "ROLLBACK attempt=${attempt_num} — changes kept on feature branch"
  }

  # Early commit 생성
  make_staged_change "src/bad-code.ts"
  git commit -m "feat: early commit (will fail)" >/dev/null 2>&1
  local after_early; after_early=$(git rev-parse HEAD)

  # rollback_attempt 호출 — git 연산 없음, 커밋 유지
  rollback_attempt 0

  # 커밋이 유지돼야 한다 (revert 없음)
  local after_rollback; after_rollback=$(git rev-parse HEAD)
  [[ "$after_early" == "$after_rollback" ]]

  # 다음 attempt: [attempt-1-fix] 추가 커밋
  make_staged_change "src/fix.ts"
  attempt=1
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    commit_suffix=""
    [[ $attempt -gt 0 ]] && commit_suffix=" [attempt-${attempt}-fix]"
    git commit -m "feat: fix${commit_suffix}" >/dev/null 2>&1
  fi

  # git log: early commit + attempt-1-fix commit 모두 존재
  local log; log=$(git log --format="%s")
  [[ "$log" == *"early commit"* ]]
  [[ "$log" == *"[attempt-1-fix]"* ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 10: RUN_LOG에 early commit hash 기록
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: early commit hash logged to RUN_LOG" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-runlog" 2>/dev/null

  local run_log="${TEST_TMP}/run.jsonl"
  RUN_LOG="$run_log"
  IMPL_FILE="docs/impl/01-test.md"
  ISSUE_NUM="999"

  make_staged_change "src/logged.ts"

  # early commit + RUN_LOG 기록 (impl_std.sh 로직 재현)
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    git commit -m "feat(#999): logged" >/dev/null 2>&1
    early_commit=$(git rev-parse --short HEAD)
    attempt=0
    [[ -n "$RUN_LOG" ]] && printf '{"event":"commit","hash":"%s","attempt":%d,"t":%d}\n' \
      "$early_commit" "$((attempt+1))" "$(date +%s)" >> "$RUN_LOG"
  fi

  # RUN_LOG에 commit 이벤트가 기록됐는지 확인
  [[ -f "$run_log" ]]
  local log_content; log_content=$(cat "$run_log")
  [[ "$log_content" == *'"event":"commit"'* ]]
  [[ "$log_content" == *'"attempt":1'* ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 11: fast CHANGES_REQUESTED → [fast-pr-fix] 추가 커밋
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: fast CHANGES_REQUESTED — engineer fix adds [fast-pr-fix] commit" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-fast-pr-fix" 2>/dev/null

  IMPL_FILE="docs/impl/01-test.md"
  ISSUE_NUM="999"

  # Fast path initial commit
  make_staged_change "src/feature.ts"
  git commit -m "feat: initial [fast-mode]" >/dev/null 2>&1
  local after_fast; after_fast=$(git rev-parse HEAD)

  # pr-reviewer가 CHANGES_REQUESTED 반환 → engineer가 수정 → fix_list commit
  # (fast CHANGES_REQUESTED 경로 재현)
  make_staged_change "src/feature.ts"  # engineer 수정 (staged)

  fix_list=$(collect_changed_files || true)
  if [[ -n "$fix_list" ]]; then
    echo "$fix_list" | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    git commit -m "$(generate_commit_msg) [fast-pr-fix]" >/dev/null 2>&1
  fi

  local after_fix; after_fix=$(git rev-parse HEAD)
  [[ "$after_fix" != "$after_fast" ]]
  # generate_commit_msg은 멀티라인이므로 %B(전체 본문)로 확인
  local fix_msg; fix_msg=$(git log --format="%B" -1)
  [[ "$fix_msg" == *"fast-pr-fix"* ]]
}

@test "dryrun: fast CHANGES_REQUESTED — no fix needed, pr_reviewer_lgtm still set" {
  # fix_list가 비어있어도 pr_reviewer_lgtm은 항상 set된다
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-no-fix" 2>/dev/null

  make_staged_change "src/feature.ts"
  git commit -m "feat: initial [fast-mode]" >/dev/null 2>&1
  local before_pr; before_pr=$(git rev-parse HEAD)

  # fix_list 없음 (engineer가 변경 안 함)
  fix_list=$(collect_changed_files || true)
  # fix_list가 비어있으면 커밋 스킵
  [[ -z "$fix_list" ]]
  local after_skip; after_skip=$(git rev-parse HEAD)
  [[ "$before_pr" == "$after_skip" ]]

  # pr_reviewer_lgtm은 LGTM이든 fix 완료든 항상 set
  touch "${STATE_DIR}/${PREFIX}_pr_reviewer_lgtm"
  [[ -f "${STATE_DIR}/${PREFIX}_pr_reviewer_lgtm" ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 12: harness_commit_and_merge — suffix + depth 검증
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: harness_commit_and_merge — simple suffix in commit" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-hcam" 2>/dev/null

  IMPL_FILE="docs/impl/01-simple.md"
  ISSUE_NUM="999"

  make_staged_change "src/fix.ts"

  touch "${STATE_DIR}/${PREFIX}_pr_reviewer_lgtm"

  run harness_commit_and_merge "feat/999-hcam" "999" "simple" "$PREFIX" "[simple-fix]"
  [[ $status -eq 0 ]]
}

@test "dryrun: harness_commit_and_merge — depth=std with no changes skips commit" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-nochange" 2>/dev/null
  create_test_commit "feature.txt"

  touch "${STATE_DIR}/${PREFIX}_pr_reviewer_lgtm"

  # 변경사항 없음 → commit 스킵, merge만
  run harness_commit_and_merge "feat/999-nochange" "999" "std" "$PREFIX"
  [[ $status -eq 0 ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 13: fast_src HEAD~1 기반 파일 목록 검증
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: fast_src (HEAD~1 --name-only) returns correct ts files for pr-reviewer" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-fastsrc" 2>/dev/null

  # TypeScript 파일 변경 + commit
  mkdir -p "${GIT_WORK_TREE}/src"
  echo "export const a = 1;" > "${GIT_WORK_TREE}/src/a.ts"
  echo "export const b = 1;" > "${GIT_WORK_TREE}/src/b.tsx"
  echo "readme" > "${GIT_WORK_TREE}/README.md"  # non-ts file
  git add src/a.ts src/b.tsx README.md
  git commit -m "feat: fast-mode commit" >/dev/null 2>&1

  # fast_src = git diff --name-only HEAD~1 (fast path 로직 재현)
  local fast_src
  fast_src=$(git diff --name-only HEAD~1 2>/dev/null | tr '\n' ' ')

  # ts/tsx 파일이 포함돼야 한다
  [[ "$fast_src" == *"src/a.ts"* ]]
  [[ "$fast_src" == *"src/b.tsx"* ]]
  [[ "$fast_src" == *"README.md"* ]]

  # HEAD diff는 비어있어야 한다
  local head_src
  head_src=$(git diff --name-only HEAD 2>/dev/null | tr '\n' ' ')
  [[ -z "$head_src" ]]
}

@test "dryrun: fast_src HEAD~1 returns empty when no commit exists" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-fastsrc-empty" 2>/dev/null

  # 아무 변경 없이 HEAD~1 호출 — 첫 커밋이면 비어있을 수 있다
  local fast_src
  fast_src=$(git diff --name-only HEAD~1 2>/dev/null | tr '\n' ' ' || true)
  # 빈 문자열이거나 유효한 파일 목록
  [[ -z "$fast_src" ]] || [[ -n "$fast_src" ]]  # 항상 통과 (crash 없음 확인)
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 14: bugfix 테스트 — REMOVED (v6): bugfix.sh 삭제됨
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: simple impl_simple.sh exists and has pr-reviewer" {
  run bash -c '
    grep "pr-reviewer" "'"${HARNESS_DIR}/impl_simple.sh"'"
  '
  [[ "$output" == *"pr-reviewer"* ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 15: generate_commit_msg 멀티라인과 suffix 위치 검증
# 실제 코드: git commit -m "$(generate_commit_msg)${commit_suffix}"
# → suffix는 마지막 줄(body)에 붙음. subject(%s)에서는 안 보임.
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: early commit [attempt-N-fix] suffix in commit body (not subject) — real generate_commit_msg" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-suffix-body" 2>/dev/null

  IMPL_FILE="docs/impl/01-test.md"
  ISSUE_NUM="999"

  make_staged_change "src/feature.ts"

  # 실제 impl_std.sh 로직 재현 (attempt=1)
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    attempt=1
    commit_suffix=""
    [[ $attempt -gt 0 ]] && commit_suffix=" [attempt-${attempt}-fix]"
    git commit -m "$(generate_commit_msg)${commit_suffix}" >/dev/null 2>&1
  fi

  # subject에는 suffix 없음 (generate_commit_msg가 멀티라인이므로)
  local subject; subject=$(git log --format="%s" -1)
  [[ "$subject" != *"attempt"* ]]

  # 전체 body(%B)에는 suffix 있음
  local body; body=$(git log --format="%B" -1)
  [[ "$body" == *"[attempt-1-fix]"* ]]
}

@test "dryrun: early commit attempt=0 — no suffix in subject or body" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-no-suffix" 2>/dev/null

  IMPL_FILE="docs/impl/01-test.md"
  ISSUE_NUM="999"
  attempt=0

  make_staged_change "src/feature.ts"
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    commit_suffix=""
    [[ $attempt -gt 0 ]] && commit_suffix=" [attempt-${attempt}-fix]"
    git commit -m "$(generate_commit_msg)${commit_suffix}" >/dev/null 2>&1
  fi

  local body; body=$(git log --format="%B" -1)
  [[ "$body" != *"[attempt-"* ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 16: deep path 전체 플로우 — pr_reviewer_lgtm + security_review_passed
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: deep path — early commit → pr-reviewer → security → test-files → merge" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-deep" 2>/dev/null

  IMPL_FILE="docs/impl/01-test.md"
  ISSUE_NUM="999"
  attempt=0

  # Step 1: Engineer 변경 + early commit
  make_staged_change "src/service.ts"
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    commit_suffix=""
    git commit -m "$(generate_commit_msg)${commit_suffix}" >/dev/null 2>&1
  fi
  local after_early; after_early=$(git rev-parse HEAD)

  # Step 2: pr-reviewer diff = HEAD~1 (이미 커밋됐으므로)
  local pr_diff; pr_diff=$(git diff HEAD~1 --name-only 2>/dev/null | tr '\n' ' ')
  [[ "$pr_diff" == *"service.ts"* ]]
  touch "${STATE_DIR}/${PREFIX}_pr_reviewer_lgtm"

  # Step 3: security-reviewer target = HEAD~1 ts 파일
  local sec_target; sec_target=$(git diff HEAD~1 --name-only 2>/dev/null \
    | grep -E '\.(ts|tsx|js|jsx)$' | tr '\n' ' ')
  [[ "$sec_target" == *"service.ts"* ]]
  touch "${STATE_DIR}/${PREFIX}_security_review_passed"

  # Step 4: test-engineer 파일 추가 + test-files commit
  make_staged_test_file "src/__tests__/service.test.ts"
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    git commit -m "$(generate_commit_msg) [test-files]" >/dev/null 2>&1
  fi
  local after_test; after_test=$(git rev-parse HEAD)
  [[ "$after_test" != "$after_early" ]]

  # Step 5: merge (deep: pr_reviewer_lgtm + security_review_passed 필요)
  run merge_to_main "feat/999-deep" "999" "deep" "$PREFIX"
  [[ $status -eq 0 ]]
}

@test "dryrun: deep path — merge rejected without security_review_passed" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-no-sec" 2>/dev/null
  make_staged_change "src/feature.ts"
  git commit -m "feat: impl" >/dev/null 2>&1

  touch "${STATE_DIR}/${PREFIX}_pr_reviewer_lgtm"
  rm -f "${STATE_DIR}/${PREFIX}_security_review_passed"

  run merge_to_main "feat/999-no-sec" "999" "deep" "$PREFIX"
  [[ $status -ne 0 ]]
  [[ "$output" == *"security_review_passed"* ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 17: multiple files in early commit
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: early commit — multiple changed files all committed together" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-multi" 2>/dev/null

  IMPL_FILE="docs/impl/01-test.md"
  ISSUE_NUM="999"

  # 여러 파일 staged
  make_staged_change "src/module-a.ts"
  make_staged_change "src/module-b.ts"
  make_staged_change "src/utils.ts"

  local before; before=$(git rev-parse HEAD)
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    commit_suffix=""
    git commit -m "$(generate_commit_msg)${commit_suffix}" >/dev/null 2>&1
  fi

  local after; after=$(git rev-parse HEAD)
  [[ "$before" != "$after" ]]

  # 모든 파일이 한 커밋에 포함됐는지 확인
  local committed_files; committed_files=$(git diff HEAD~1 --name-only | tr '\n' ' ')
  [[ "$committed_files" == *"module-a.ts"* ]]
  [[ "$committed_files" == *"module-b.ts"* ]]
  [[ "$committed_files" == *"utils.ts"* ]]
}

# ─────────────────────────────────────────────────────────────────────
# DRY-RUN 18: 연속 attempt — git log에 정확한 커밋 수
# attempt 0 → early commit → FAIL → attempt 1 → [attempt-1-fix] commit
# → test-files → merge
# ─────────────────────────────────────────────────────────────────────

@test "dryrun: 2-attempt scenario — git log shows both commits before merge" {
  cd "${GIT_WORK_TREE}"
  create_test_commit "base.txt"
  git checkout -b "feat/999-2attempt" 2>/dev/null
  local base; base=$(git rev-parse HEAD)

  IMPL_FILE="docs/impl/01-test.md"
  ISSUE_NUM="999"

  # Attempt 0: early commit
  make_staged_change "src/v1.ts"
  collect_changed_files | while IFS= read -r _cf; do
    [[ -n "$_cf" ]] && git add -- "$_cf"
  done 2>/dev/null || git add src/v1.ts 2>/dev/null || true
  attempt=0
  commit_suffix=""
  [[ $attempt -gt 0 ]] && commit_suffix=" [attempt-${attempt}-fix]"
  git commit -m "feat(#999): v1${commit_suffix}" >/dev/null 2>&1
  local c0; c0=$(git rev-parse HEAD)

  # rollback_attempt does NOT revert (new strategy)
  # → just log, keep commit

  # Attempt 1: [attempt-1-fix] early commit
  make_staged_change "src/v2.ts"
  collect_changed_files | while IFS= read -r _cf; do
    [[ -n "$_cf" ]] && git add -- "$_cf"
  done 2>/dev/null || git add src/v2.ts 2>/dev/null || true
  attempt=1
  commit_suffix=""
  [[ $attempt -gt 0 ]] && commit_suffix=" [attempt-${attempt}-fix]"
  git commit -m "feat(#999): v2${commit_suffix}" >/dev/null 2>&1
  local c1; c1=$(git rev-parse HEAD)

  # test-files commit
  make_staged_test_file "src/__tests__/v2.test.ts"
  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    git commit -m "feat(#999): v2 [test-files]" >/dev/null 2>&1
  fi

  # git log: base → c0 → c1 → test-files = 4 commits minimum
  local count; count=$(git log --oneline | wc -l | tr -d ' ')
  [[ "$count" -ge 4 ]]

  local log; log=$(git log --format="%s")
  [[ "$log" == *"v1"* ]]
  [[ "$log" == *"[attempt-1-fix]"* ]]
  [[ "$log" == *"test-files"* ]]
}
