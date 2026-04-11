# Harness Rule Index

활성 규칙 목록. 스크립트 구현 + 테스트 커버리지가 모두 있어야 규칙으로 등록한다.

`harness/tests/rule-audit.bats`가 이 파일을 파싱해 일관성을 자동 검증한다.

---

| ID | 규칙 설명 | 스크립트 grep | 스크립트 파일 | 커버 테스트 |
|----|-----------|--------------|--------------|------------|
| R01 | early commit — automated_checks PASS 직후 engineer 변경을 feature branch에 즉시 커밋 | early_commit= | impl_std.sh, impl_deep.sh | commit-strategy: early commit block exists after automated_checks PASS |
| R02 | pr-reviewer — simple/std/deep 전체 깊이에서 실행 | pr-reviewer.*simple/std/deep | impl_simple.sh, impl_std.sh, impl_deep.sh | commit-strategy: pr-reviewer runs on all depths (code analysis) |
| R03 | changed_files — early commit 이후 test-engineer에게 HEAD~1 diff 전달 | git diff HEAD~1 --name-only | impl_std.sh, impl_deep.sh | commit-strategy: changed_files uses git diff HEAD~1 after early commit |
| R04 | test-files commit — merge 직전 test-engineer가 추가한 파일을 별도 커밋 | test-files | impl_std.sh, impl_deep.sh | commit-strategy: test-files commit block exists before merge |
| R05 | ~~bugfix merge gate~~ — **폐기 (v6)**: bugfix/direct 경로 제거. QA는 impl 루프로 통합 | ~~depth.*==.*bugfix~~ | ~~utils.sh~~ | ~~commit-strategy: bugfix merge uses validator_b_passed gate~~ |
| R06 | security-reviewer — deep 깊이에서만 실행 (std/fast 스킵) | DEPTH.*==.*deep | impl_deep.sh | commit-strategy: security-reviewer is inside deep-only block |
| R07 | simple CHANGES_REQUESTED — pr-reviewer가 CHANGES_REQUESTED 시 engineer 추가커밋 (attempt++) | simple-pr-fix | impl_simple.sh | dryrun: simple CHANGES_REQUESTED — engineer fix retry |
| R08 | ~~SPEC_ISSUE MODULE_PLAN~~ — **폐기 (v6)**: bugfix.sh 제거 | ~~MODULE_PLAN~~ | ~~bugfix.sh~~ | ~~bugfix: SPEC_ISSUE MODULE_PLAN call~~ |
