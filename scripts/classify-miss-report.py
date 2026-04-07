#!/usr/bin/env python3
"""
classify-miss-report.py — fast_classify 미스 분석

/tmp/harness-router.log에서 Haiku 폴백 케이스를 수집하고
fast_classify에 추가할 패턴 후보를 추출한다.

사용법:
  python3 ~/.claude/scripts/classify-miss-report.py
  python3 ~/.claude/scripts/classify-miss-report.py /path/to/harness-router.log
"""
import re
import sys
from collections import Counter, defaultdict

LOG_PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/harness-router.log"

try:
    lines = open(LOG_PATH).readlines()
except FileNotFoundError:
    print(f"로그 없음: {LOG_PATH}")
    sys.exit(0)

# 파싱: FAST_CLASSIFY / INTENT / classify_fail
fast_hits = 0
haiku_hits = 0
classify_fails = 0
haiku_prompts = defaultdict(list)  # category → [prompt, ...]
fail_prompts = []

for line in lines:
    if "FAST_CLASSIFY result=" in line:
        fast_hits += 1
    elif "INTENT result=" in line:
        haiku_hits += 1
        m = re.search(r'INTENT result=(\w+)', line)
        # 같은 줄에 prompt가 없으므로 이전 줄에서 추출
    elif "classify_fail" in line:
        classify_fails += 1
        m = re.search(r"prompt='([^']*)", line)
        if m:
            fail_prompts.append(m.group(1)[:80])

# Haiku가 분류한 프롬프트 추출 (HAIKU_CLI_OK/HAIKU_API_OK 직전의 프롬프트)
# 더 정확한 방법: INTENT 직전의 HAIKU 로그에서 프롬프트 추출
haiku_classified = []
for i, line in enumerate(lines):
    if "INTENT result=" in line:
        cat = re.search(r'INTENT result=(\w+)', line).group(1)
        # 위로 스캔해서 가장 가까운 prompt 찾기
        for j in range(i-1, max(i-5, 0), -1):
            pm = re.search(r"prompt='([^']*)", lines[j])
            if pm:
                haiku_classified.append((cat, pm.group(1)[:80]))
                break

# Haiku 폴백된 프롬프트를 카테고리별 그룹핑
by_cat = defaultdict(list)
for cat, prompt in haiku_classified:
    by_cat[cat].append(prompt)

total = fast_hits + haiku_hits + classify_fails
print("=" * 60)
print("fast_classify 커버리지 리포트")
print("=" * 60)
print(f"총 분류 시도:     {total}")
print(f"fast_classify 히트: {fast_hits} ({fast_hits*100//max(total,1)}%)")
print(f"Haiku 폴백:       {haiku_hits} ({haiku_hits*100//max(total,1)}%)")
print(f"분류 실패:        {classify_fails} ({classify_fails*100//max(total,1)}%)")
print()

if haiku_classified:
    print("--- Haiku가 잡은 프롬프트 (fast_classify 승격 후보) ---")
    for cat in sorted(by_cat.keys()):
        prompts = by_cat[cat]
        print(f"\n  [{cat}] ({len(prompts)}건)")
        for p in prompts[-5:]:  # 최근 5개
            print(f"    \"{p}\"")

if fail_prompts:
    print(f"\n--- 분류 실패 ({len(fail_prompts)}건, 최근 5개) ---")
    for p in fail_prompts[-5:]:
        print(f"    \"{p}\"")

# 패턴 후보 제안
print("\n--- 승격 후보 패턴 ---")
if not haiku_classified:
    print("  (Haiku 폴백 데이터 없음)")
else:
    # 짧은 프롬프트 (≤20자) 중 반복 카테고리
    short = [(c, p) for c, p in haiku_classified if len(p) <= 20]
    if short:
        cat_counts = Counter(c for c, _ in short)
        for cat, count in cat_counts.most_common(3):
            examples = [p for c, p in short if c == cat][:3]
            print(f"  {cat} (짧은 프롬프트 {count}건): {examples}")

print()
