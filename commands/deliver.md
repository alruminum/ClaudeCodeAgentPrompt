---
description: B2B 납품 전 클라이언트에게 줘도 되는지 자동 체크한다. DELIVERY_READY / DELIVERY_BLOCKED 판정.
argument-hint: ""
---

# /deliver

납품 전 안전 체크를 실행한다.  
security-reviewer(OWASP 취약점)와 다른 기준 — 실수 방지용 체크리스트.

## 실행

아래 검사들을 순서대로 실행한다. `src/` 디렉토리가 없으면 프로젝트 루트 전체를 대상으로 한다.

### 1. .env 패턴 노출 스캔

```bash
TARGET=${1:-src}
[ -d "$TARGET" ] || TARGET="."
echo "=== .env 패턴 스캔 ==="
grep -rn --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" \
  -E '(process\.env\.[A-Z_]+\s*\|\|\s*["\x27][^"\x27]{8,}|API_KEY\s*=\s*["\x27][^"\x27]+|SECRET\s*=\s*["\x27][^"\x27]+)' \
  "$TARGET" 2>/dev/null | head -20 || echo "CLEAN"
```

### 2. console.log / debugger 잔존 스캔

```bash
TARGET=${1:-src}
[ -d "$TARGET" ] || TARGET="."
echo "=== console.log / debugger 스캔 ==="
grep -rn --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" \
  -E '(console\.(log|debug|warn|error|info)\s*\(|debugger\s*;)' \
  "$TARGET" 2>/dev/null | grep -v "// eslint-disable" | grep -v "__tests__" | head -20 || echo "CLEAN"
```

### 3. 하드코딩 URL / localhost 스캔

```bash
TARGET=${1:-src}
[ -d "$TARGET" ] || TARGET="."
echo "=== 하드코딩 URL 스캔 ==="
grep -rn --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" \
  -E '(localhost|127\.0\.0\.1|0\.0\.0\.0|https?://[a-z0-9.-]+\.(internal|local|dev|staging))' \
  "$TARGET" 2>/dev/null | grep -v "// eslint-disable" | grep -v "__tests__" | head -20 || echo "CLEAN"
```

### 4. TODO / FIXME 잔존 스캔

```bash
TARGET=${1:-src}
[ -d "$TARGET" ] || TARGET="."
echo "=== TODO/FIXME 스캔 ==="
grep -rn --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" \
  -E '(TODO|FIXME|HACK|XXX)\s*:' \
  "$TARGET" 2>/dev/null | head -20 || echo "CLEAN"
```

### 5. 빌드 성공 여부

```bash
echo "=== 빌드 검증 ==="
if [ -f "package.json" ]; then
  npm run build 2>&1 | tail -5
else
  echo "SKIP (package.json 없음)"
fi
```

### 6. .env 파일 커밋 여부 확인

```bash
echo "=== .env 커밋 여부 ==="
git ls-files | grep -E '^\.env' | grep -v ".example" | grep -v ".sample" && echo "WARN: .env 파일이 git에 포함됨" || echo "CLEAN"
```

## 결과 판정

각 항목을 표로 정리한다:

| 검사 | 결과 |
|---|---|
| .env 패턴 노출 | CLEAN / ⚠️ N건 |
| console.log/debugger | CLEAN / ⚠️ N건 |
| 하드코딩 URL | CLEAN / ⚠️ N건 |
| TODO/FIXME | CLEAN / ⚠️ N건 |
| 빌드 | PASS / FAIL |
| .env 커밋 | CLEAN / ⚠️ 위험 |

**DELIVERY_READY** — 빌드 PASS + 치명적 항목(.env 노출, .env 커밋) CLEAN  
**DELIVERY_BLOCKED** — 빌드 FAIL 또는 치명적 항목 존재 → 수정 필요 목록 출력  
**DELIVERY_WARN** — 빌드 PASS + console.log/TODO 잔존 (납품 가능하나 권장 정리)
