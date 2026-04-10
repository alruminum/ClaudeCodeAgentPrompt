# Harness Rule Index

활성 규칙 목록. 스크립트 구현 + 테스트 커버리지가 모두 있어야 규칙으로 등록한다.

`harness/tests/rule-audit.bats`가 이 파일을 파싱해 일관성을 자동 검증한다.

---

| ID | 규칙 설명 | 스크립트 grep | 스크립트 파일 | 커버 테스트 |
|----|-----------|--------------|--------------|------------|
| R01 | early commit — automated_checks PASS 직후 engineer 변경을 feature branch에 즉시 커밋 | early_commit= | impl-process.sh | commit-strategy: early commit block exists after automated_checks PASS |
| R02 | pr-reviewer — fast/std/deep 전체 깊이에서 실행 | pr-reviewer.*fast/std/deep | impl-process.sh | commit-strategy: pr-reviewer runs on all depths (code analysis) |
| R03 | changed_files — early commit 이후 test-engineer에게 HEAD~1 diff 전달 | git diff HEAD~1 --name-only | impl-process.sh | commit-strategy: changed_files uses git diff HEAD~1 after early commit |
| R04 | test-files commit — merge 직전 test-engineer가 추가한 파일을 별도 커밋 | test-files | impl-process.sh | commit-strategy: test-files commit block exists before merge |
| R05 | bugfix merge gate — depth=bugfix 경로는 validator_b_passed 플래그 필수 | depth.*==.*bugfix | utils.sh | commit-strategy: bugfix merge uses validator_b_passed gate (not pr_reviewer_lgtm) |
| R06 | security-reviewer — deep 깊이에서만 실행 (std/fast 스킵) | DEPTH.*==.*deep | impl-process.sh | commit-strategy: security-reviewer is inside deep-only block |
| R07 | fast CHANGES_REQUESTED — pr-reviewer가 CHANGES_REQUESTED 시 engineer 추가커밋 1회 | fast-pr-fix | impl-process.sh | dryrun: fast CHANGES_REQUESTED — engineer fix adds [fast-pr-fix] commit |
| R08 | SPEC_ISSUE MODULE_PLAN — "버그픽스" 프리픽스 없이 표준 MODULE_PLAN 호출 (bugfix 분기 오염 방지) | MODULE_PLAN | bugfix.sh | bugfix: SPEC_ISSUE MODULE_PLAN call has no bugfix prefix |
