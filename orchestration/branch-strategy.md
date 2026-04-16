# 브랜치 전략 (Feature Branch)

구현/버그픽스 루프의 브랜치 네이밍·머지·정리 규칙. harness/impl_*.sh가 참조.

---

## 브랜치 네이밍
구현 루프 / 버그픽스 루프 실행은 feature branch에서 수행한다.
네이밍: `{type}/{milestone}-{issue}-{slug}` (# 없이 숫자만)

- `type`: `feat` (구현 루프) / `fix` (QA/DESIGN_HANDOFF 경유 구현)
- `milestone`: GitHub 이슈의 milestone 제목 (gh issue view로 조회, 소문자 변환. 없으면 생략)
- `issue`: GitHub issue 번호 (숫자만)
- `slug`: issue title에서 영문/숫자만 추출, 30자 캡. 한국어만이면 생략

예시: `feat/mvp-42-add-login` / `fix/57` (한국어 제목)

## 브랜치 생성 시점
- harness/impl_{simple,std,deep}.sh 진입 직후 (engineer 호출 전)

## 커밋 규칙
- feature branch: commit-gate의 pr_reviewer_lgtm 면제, engineer 자유 커밋
- 실패 시: git stash 대신 변경 유지 + 다음 attempt에서 추가 커밋

## main 머지 조건
| depth | 머지 전 필수 |
|---|---|
| simple | pr_reviewer_lgtm |
| std | pr_reviewer_lgtm |
| deep | pr_reviewer_lgtm + security_review_passed |

## 머지 흐름 (GitHub PR 경유)
1. engineer가 커밋할 때마다 `push_and_ensure_pr()` 호출
   - `git push origin {branch}`
   - 최초 push 시 `gh pr create` (이후에는 push만)
2. pr-reviewer LGTM 후 `merge_to_main()` 호출
   - `gh pr merge {branch} --squash` (커밋 1개로 합쳐서 main에)
   - `git checkout main && git pull` (로컬 동기화)

충돌 시: `gh pr merge` 실패 → `MERGE_CONFLICT_ESCALATE` → 메인 Claude 보고

## 브랜치 정리
| 결과 | 처리 |
|---|---|
| HARNESS_DONE | 브랜치 보존 (remote + 로컬 모두). 주기적 수동 정리. |
| IMPLEMENTATION_ESCALATE | 브랜치 보존 |
| MERGE_CONFLICT_ESCALATE | 브랜치 보존 |

merge 후에도 브랜치를 삭제하지 않는다. GitHub에서 브랜치 이력 확인용.
