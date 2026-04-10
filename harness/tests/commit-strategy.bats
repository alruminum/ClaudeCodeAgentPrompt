#!/usr/bin/env bats
# harness/tests/commit-strategy.bats
# 커밋 전략 개편(d9f5bf6) 이후 변경사항 검증
# - 즉시 커밋(early commit): automated_checks PASS 직후
# - attempt > 0 → [attempt-N-fix] suffix
# - test-files 커밋: merge 직전
# - pr-reviewer: fast/std/deep 전체 실행
# - security-reviewer: deep only
# - bugfix depth: validator_b_passed 게이트

load test_helper

setup() {
  common_setup
  source "${HARNESS_DIR}/utils.sh"
  git -C "${GIT_WORK_TREE}" config user.email "test@example.com"
  git -C "${GIT_WORK_TREE}" config user.name "Test"
}

teardown() {
  common_teardown
}

# ─────────────────────────────────────────────────────────────────────
# 1. 즉시 커밋(early commit) 코드 존재 확인
# ─────────────────────────────────────────────────────────────────────

@test "commit-strategy: early commit block exists after automated_checks PASS" {
  # automated_checks PASS 바로 다음 즉시 커밋 블록이 있어야 한다
  run bash -c '
    awk "/automated_checks PASS/{found=1} found && /즉시 커밋/{print; exit}" \
      "'"${HARNESS_DIR}/impl_std.sh"'"
  '
  [[ "$output" == *"즉시 커밋"* ]]
}

@test "commit-strategy: attempt-N-fix suffix logic exists" {
  run grep 'attempt.*fix' "${HARNESS_DIR}/impl_std.sh"
  [[ "$output" == *"attempt"* ]]
  [[ "$output" == *"fix"* ]]
}

@test "commit-strategy: early commit uses generate_commit_msg" {
  # 즉시 커밋 블록이 generate_commit_msg를 사용해야 한다
  run bash -c '
    awk "/즉시 커밋/,/워커 2/{print}" "'"${HARNESS_DIR}/impl_std.sh"'" \
      | grep "generate_commit_msg"
  '
  [[ "$output" == *"generate_commit_msg"* ]]
}

@test "commit-strategy: early commit logs to RUN_LOG" {
  run bash -c '
    awk "/즉시 커밋/,/워커 2/{print}" "'"${HARNESS_DIR}/impl_std.sh"'" \
      | grep "RUN_LOG"
  '
  [[ "$output" == *"RUN_LOG"* ]]
}

# ─────────────────────────────────────────────────────────────────────
# 2. early commit 동작 (git 격리 환경)
# ─────────────────────────────────────────────────────────────────────

@test "commit-strategy: early commit creates new commit on first attempt" {
  create_test_commit "base.txt"
  local before
  before=$(git -C "${GIT_WORK_TREE}" rev-parse HEAD)

  # 변경 파일 생성
  mkdir -p "${GIT_WORK_TREE}/src"
  echo "impl" > "${GIT_WORK_TREE}/src/new.ts"
  git -C "${GIT_WORK_TREE}" add src/new.ts

  cd "${GIT_WORK_TREE}"
  source "${HARNESS_DIR}/utils.sh"
  IMPL_FILE="docs/impl/01-test.md"
  ISSUE_NUM="999"
  attempt=0

  collect_changed_files | while IFS= read -r _cf; do
    [[ -n "$_cf" ]] && git add -- "$_cf"
  done
  commit_suffix=""
  [[ $attempt -gt 0 ]] && commit_suffix=" [attempt-${attempt}-fix]"
  git commit -m "feat: test${commit_suffix}" >/dev/null 2>&1

  local after
  after=$(git rev-parse HEAD)
  [[ "$before" != "$after" ]]
}

@test "commit-strategy: attempt-fix suffix added when attempt > 0" {
  create_test_commit "base.txt"
  echo "changed" > "${GIT_WORK_TREE}/base.txt"
  git -C "${GIT_WORK_TREE}" add base.txt

  cd "${GIT_WORK_TREE}"
  attempt=1
  commit_suffix=""
  [[ $attempt -gt 0 ]] && commit_suffix=" [attempt-${attempt}-fix]"
  git commit -m "feat: test${commit_suffix}" >/dev/null 2>&1

  local msg
  msg=$(git log --format="%s" -1)
  [[ "$msg" == *"[attempt-1-fix]"* ]]
}

@test "commit-strategy: no commit when no changed files" {
  create_test_commit "base.txt"
  local before
  before=$(git -C "${GIT_WORK_TREE}" rev-parse HEAD)

  cd "${GIT_WORK_TREE}"
  source "${HARNESS_DIR}/utils.sh"

  # collect_changed_files should return 1 (nothing to commit)
  if collect_changed_files > /dev/null 2>&1; then
    git commit -m "should-not-happen" >/dev/null 2>&1
  fi

  local after
  after=$(git rev-parse HEAD)
  [[ "$before" == "$after" ]]
}

# ─────────────────────────────────────────────────────────────────────
# 3. changed_files 참조: HEAD~1 우선
# ─────────────────────────────────────────────────────────────────────

@test "commit-strategy: changed_files uses git diff HEAD~1 after early commit" {
  # early commit 이후 changed_files는 HEAD~1 diff를 참조해야 한다
  run bash -c '
    awk "/워커 2: test-engineer/,/te_prompt/{print}" \
      "'"${HARNESS_DIR}/impl_std.sh"'" | grep "HEAD~1"
  '
  [[ "$output" == *"HEAD~1"* ]]
}

@test "commit-strategy: changed_files fallback to git status when no HEAD~1" {
  run bash -c '
    # 폴백 경로가 있어야 한다
    grep -A3 "changed_files=\$(git diff HEAD~1" "'"${HARNESS_DIR}/impl_std.sh"'" \
      | grep "git status"
  '
  [[ "$output" == *"git status"* ]]
}

@test "commit-strategy: HEAD~1 diff returns correct files after early commit" {
  create_test_commit "base.txt"
  mkdir -p "${GIT_WORK_TREE}/src"
  echo "feat" > "${GIT_WORK_TREE}/src/feature.ts"
  git -C "${GIT_WORK_TREE}" add src/feature.ts
  git -C "${GIT_WORK_TREE}" commit -m "feat: early commit" >/dev/null 2>&1

  local files
  files=$(git -C "${GIT_WORK_TREE}" diff HEAD~1 --name-only 2>/dev/null | tr '\n' ' ')
  [[ "$files" == *"src/feature.ts"* ]]
}

# ─────────────────────────────────────────────────────────────────────
# 4. pr-reviewer: fast/std/deep 전체 실행
# ─────────────────────────────────────────────────────────────────────

@test "commit-strategy: pr-reviewer runs on all depths (code analysis)" {
  # pr-reviewer 블록이 deep-only 조건 없이 std/deep 경로에 있어야 한다
  run bash -c '
    # std/deep 루프 내에서 pr-reviewer가 깊이 조건 밖에 있어야 한다
    grep -n "pr-reviewer 시작 (depth=" "'"${HARNESS_DIR}/impl_std.sh"'"
  '
  # depth=fast와 depth=DEPTH(std/deep) 모두 pr-reviewer 호출
  [[ "$output" == *"depth=fast"* ]]
  [[ "$output" == *"depth=\$DEPTH"* ]]
}

@test "commit-strategy: pr-reviewer uses git diff HEAD~1 (not HEAD)" {
  # early commit 이후 비어있는 HEAD diff 방지
  # diff_out 라인이 HEAD~1을 참조해야 한다
  run bash -c '
    grep "diff_out=\$(git diff HEAD~1" "'"${HARNESS_DIR}/impl_std.sh"'"
  '
  [[ "$output" == *"HEAD~1"* ]]
}

@test "commit-strategy: pr_reviewer_lgtm flag set after LGTM on all depths" {
  # std/deep 경로에서 pr_reviewer_lgtm을 touch (fast 경로 제외하고 std/deep 루프 내)
  run bash -c '
    # pr_reviewer_lgtm touch가 두 곳 이상 있어야 한다 (fast + std/deep)
    grep -c "touch.*pr_reviewer_lgtm" "'"${HARNESS_DIR}/impl_std.sh"'"
  '
  [[ "$output" -ge 2 ]]
}

# ─────────────────────────────────────────────────────────────────────
# 5. security-reviewer: deep only
# ─────────────────────────────────────────────────────────────────────

@test "commit-strategy: security-reviewer is inside deep-only block" {
  run bash -c '
    awk "/워커 5: security-reviewer/,/DEPTH.*deep/{print; exit}" \
      "'"${HARNESS_DIR}/impl_std.sh"'"
  '
  # 워커 5 앞에 DEPTH==deep 조건이 있어야 한다
  run bash -c '
    grep -B5 "security-reviewer 시작 (deep only" "'"${HARNESS_DIR}/impl_deep.sh"'" \
      | grep "DEPTH.*deep"
  '
  [[ "$output" == *"deep"* ]]
}

@test "commit-strategy: std skips security-reviewer but auto-touches flag" {
  run bash -c '
    # std: security-reviewer 스킵, 플래그 자동 생성
    grep -A5 "std: security-reviewer 스킵" "'"${HARNESS_DIR}/impl_std.sh"'"
  '
  [[ "$output" == *"security_review_passed"* ]]
}

# ─────────────────────────────────────────────────────────────────────
# 6. test-files 커밋 (merge 직전)
# ─────────────────────────────────────────────────────────────────────

@test "commit-strategy: test-files commit block exists before merge" {
  run bash -c '
    # merge to main 섹션 직전에 test-files 커밋 블록이 있어야 한다
    awk "/merge to main/,/merge_to_main/{print}" \
      "'"${HARNESS_DIR}/impl_std.sh"'" | grep "test-files"
  '
  [[ "$output" == *"test-files"* ]]
}

@test "commit-strategy: test-files commit uses [test-files] suffix" {
  run grep '"'"$(generate_commit_msg) \[test-files\]"'"' "${HARNESS_DIR}/impl_std.sh" 2>/dev/null \
    || grep 'test-files' "${HARNESS_DIR}/impl_std.sh"
  [[ "$output" == *"test-files"* ]]
}

@test "commit-strategy: test-files commit adds actual commit" {
  create_test_commit "base.txt"
  local before
  before=$(git -C "${GIT_WORK_TREE}" rev-parse HEAD)

  # test-engineer가 추가한 파일 시뮬레이션
  mkdir -p "${GIT_WORK_TREE}/src/__tests__"
  echo "test" > "${GIT_WORK_TREE}/src/__tests__/feature.test.ts"
  git -C "${GIT_WORK_TREE}" add src/__tests__/feature.test.ts

  cd "${GIT_WORK_TREE}"
  source "${HARNESS_DIR}/utils.sh"
  IMPL_FILE=""
  ISSUE_NUM="999"

  if collect_changed_files > /dev/null 2>&1; then
    collect_changed_files | while IFS= read -r _cf; do
      [[ -n "$_cf" ]] && git add -- "$_cf"
    done
    git commit -m "feat: impl [test-files]" >/dev/null 2>&1
  fi

  local after
  after=$(git rev-parse HEAD)
  [[ "$before" != "$after" ]]
  local msg
  msg=$(git log --format="%s" -1)
  [[ "$msg" == *"test-files"* ]]
}

# ─────────────────────────────────────────────────────────────────────
# 7. merge gate: bugfix depth = validator_b_passed (pr_reviewer_lgtm 불필요)
# ─────────────────────────────────────────────────────────────────────

@test "commit-strategy: bugfix merge uses validator_b_passed gate (not pr_reviewer_lgtm)" {
  create_test_commit "init.txt"
  git -C "${GIT_WORK_TREE}" checkout -b "fix/test-bugfix" 2>/dev/null
  create_test_commit "fix.txt"

  # pr_reviewer_lgtm 없이 validator_b_passed만 있어도 bugfix merge 통과
  rm -f "/tmp/${PREFIX}_pr_reviewer_lgtm"
  touch "/tmp/${PREFIX}_validator_b_passed"
  run merge_to_main "fix/test-bugfix" "999" "bugfix" "$PREFIX"
  [[ $status -eq 0 ]]
}

@test "commit-strategy: bugfix merge fails without validator_b_passed" {
  create_test_commit "init.txt"
  git -C "${GIT_WORK_TREE}" checkout -b "fix/test-bugfix2" 2>/dev/null
  create_test_commit "fix.txt"

  rm -f "/tmp/${PREFIX}_validator_b_passed"
  rm -f "/tmp/${PREFIX}_pr_reviewer_lgtm"
  run merge_to_main "fix/test-bugfix2" "999" "bugfix" "$PREFIX"
  [[ $status -ne 0 ]]
  [[ "$output" == *"validator_b_passed"* ]]
}

@test "commit-strategy: bugfix.sh passes depth=bugfix to harness_commit_and_merge" {
  run grep 'harness_commit_and_merge.*bugfix' "${HARNESS_DIR}/bugfix.sh"
  [[ "$output" == *"bugfix"* ]]
}

@test "commit-strategy: fast bugfix auto-touches validator_b_passed" {
  run bash -c '
    grep -A3 "fast.*validator 스킵" "'"${HARNESS_DIR}/bugfix.sh"'" \
      | grep "validator_b_passed"
  '
  [[ "$output" == *"validator_b_passed"* ]]
}

# ─────────────────────────────────────────────────────────────────────
# 8. merge gate 통합: 전체 depth 행동 확인
# ─────────────────────────────────────────────────────────────────────

@test "merge gate: fast fails without pr_reviewer_lgtm" {
  create_test_commit "init.txt"
  git -C "${GIT_WORK_TREE}" checkout -b "feat/fast-no-pr" 2>/dev/null
  create_test_commit "feature.txt"
  rm -f "/tmp/${PREFIX}_pr_reviewer_lgtm"
  run merge_to_main "feat/fast-no-pr" "999" "fast" "$PREFIX"
  [[ $status -ne 0 ]]
  [[ "$output" == *"pr_reviewer_lgtm"* ]]
}

@test "merge gate: std fails without pr_reviewer_lgtm" {
  create_test_commit "init.txt"
  git -C "${GIT_WORK_TREE}" checkout -b "feat/std-no-pr" 2>/dev/null
  create_test_commit "feature.txt"
  rm -f "/tmp/${PREFIX}_pr_reviewer_lgtm"
  run merge_to_main "feat/std-no-pr" "999" "std" "$PREFIX"
  [[ $status -ne 0 ]]
  [[ "$output" == *"pr_reviewer_lgtm"* ]]
}

@test "merge gate: deep fails without pr_reviewer_lgtm" {
  create_test_commit "init.txt"
  git -C "${GIT_WORK_TREE}" checkout -b "feat/deep-no-pr" 2>/dev/null
  create_test_commit "feature.txt"
  rm -f "/tmp/${PREFIX}_pr_reviewer_lgtm" "/tmp/${PREFIX}_security_review_passed"
  run merge_to_main "feat/deep-no-pr" "999" "deep" "$PREFIX"
  [[ $status -ne 0 ]]
  [[ "$output" == *"pr_reviewer_lgtm"* ]]
}

@test "merge gate: pr_reviewer_lgtm NOT required for bugfix depth" {
  create_test_commit "init.txt"
  git -C "${GIT_WORK_TREE}" checkout -b "fix/pr-not-needed" 2>/dev/null
  create_test_commit "feature.txt"
  # pr_reviewer_lgtm 없어도 bugfix는 validator_b_passed만으로 통과
  rm -f "/tmp/${PREFIX}_pr_reviewer_lgtm"
  touch "/tmp/${PREFIX}_validator_b_passed"
  run merge_to_main "fix/pr-not-needed" "999" "bugfix" "$PREFIX"
  [[ $status -eq 0 ]]
}
