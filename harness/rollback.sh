#!/bin/bash
# rollback.sh — Python 마이그레이션 롤백: .sh.bak → .sh 복원
cd "$(dirname "$0")"
for f in *.sh.bak; do
  [[ -f "$f" ]] && mv "$f" "${f%.bak}" && echo "복원: ${f%.bak}"
done
echo "롤백 완료: Bash 버전 복원"
