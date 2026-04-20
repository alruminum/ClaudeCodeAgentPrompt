---
name: ux-sync
description: ux-flow.md 와 실제 src/ 코드 사이의 드리프트를 현행화하는 스킬. post-commit 훅이 UX 영향 파일(Screen.tsx, Page.tsx, routes/**, screens/**) 변경을 감지하면 SessionStart 에서 알림이 뜨고, 이 스킬을 실행하면 ux-architect 의 INCREMENTAL 모드로 변경 화면 섹션만 부분 패치한다. 유저가 "/ux-sync", "ux 현행화", "ux-flow 동기화", "플로우 문서 업데이트", "ux 드리프트" 등을 말할 때 이 스킬을 사용한다.
---

# UX Sync Skill

`ux-flow.md` 와 실제 구현 사이의 drift 를 부분 패치로 맞춘다. 전체 재작성이 아니라 **변경된 화면 섹션만** 교체 — 기존 PRD 맥락·결정 로그·[추정] 태그 보존.

## 언제 사용하는가

- SessionStart 알림에 "📝 ux-flow.md 드리프트 감지" 가 뜬 경우
- 유저가 명시적으로 "현행화해줘" / "동기화해줘" 요청
- 큰 기능 merge 후 주기적으로

## 사전 조건

- `docs/ux-flow.md` 가 존재해야 함. 없으면 안내: "먼저 `ux-architect` UX_SYNC 모드로 전체 생성 후 사용하세요".
- `.claude/harness-state/.flags/{prefix}_ux_flow_drift` 플래그 존재 권장 (없어도 수동 변경 파일 목록으로 실행 가능).

## 절차

### Step 1 — 드리프트 플래그 읽기

```bash
PREFIX=$(python3 -c "import json; d=json.load(open('.claude/harness.config.json')); print(d.get('prefix',''))" 2>/dev/null || echo "")
FLAG=".claude/harness-state/.flags/${PREFIX}_ux_flow_drift"
if [[ -f "$FLAG" ]]; then
  # 주석 제외한 변경 파일 목록 출력
  grep -v '^#' "$FLAG" | grep -v '^$'
fi
```

출력이 비어 있으면 플래그 없음 → 유저에게 "변경 파일 목록을 직접 입력해주세요" 안내.

### Step 2 — 유저 확인 게이트

```
---
**UX Sync 실행 설정**

[ux-flow.md] docs/ux-flow.md
[변경 파일 N개]
  - src/screens/LoginScreen.tsx
  - src/routes/index.tsx
  - src/screens/HomePage.tsx
[모드] UX_SYNC_INCREMENTAL (변경 섹션만 패치, 나머지 보존)

진행할까요?
---
```

확인 없이 진행 금지. 유저가 "전체 재생성" 을 원하면 UX_SYNC (INCREMENTAL 아님) 모드로 대체 실행.

### Step 3 — ux-architect 호출 (Agent 도구)

```
@MODE:UX_ARCHITECT:UX_SYNC_INCREMENTAL
@PARAMS: {
  "ux_flow_path": "/absolute/path/docs/ux-flow.md",
  "changed_files": ["src/screens/LoginScreen.tsx", "src/routes/index.tsx", ...],
  "src_dir": "/absolute/path/src"
}
```

ux-architect 가 `UX_FLOW_PATCHED` 마커와 함께 갱신된 화면 ID 목록을 반환.

### Step 4 — 플래그 소비

성공 시 (`UX_FLOW_PATCHED` 수신) 드리프트 플래그 삭제:

```bash
rm -f "$FLAG"
```

ESCALATE 수신 시 플래그 유지 (다음 세션에서 다시 알림 유지).

### Step 5 — 유저 보고

```
---
**UX Sync 완료**

ux_flow_doc: /absolute/path/docs/ux-flow.md
patched_screens: [S03, S05]
added_screens: [S07]
removed_screens: []
untouched_screens_count: 6
---
```

ESCALATE 의 경우:

```
---
**UX Sync 에스컬레이트 — 유저 판단 필요**

reason: 변경 범위가 전체 50% 이상 / 훅 오감지 / 문서 파싱 실패

추천:
- 변경이 광범위하면 `/ux-sync` 말고 ux-architect UX_SYNC 전체 모드로 재생성
- 훅 오감지면 플래그 수동 삭제
---
```

## 루프 불변식 준수

- 이 스킬은 `src/**` 를 **읽기만** 한다. 수정은 없음.
- `docs/ux-flow.md` 수정은 ux-architect 가 Edit 툴로 섹션 단위로만 수행. Write 전체 덮어쓰기 금지.
- commit-gate·pr-reviewer 관여 없음 (문서 수정이라 harness 구현 루프 진입 안 함).
- 다만 이 스킬 실행 후 유저가 변경을 커밋하면 `post-commit-scan.sh` 가 재실행되고, `docs/ux-flow.md` 는 UX 영향 파일이 아니므로 플래그 재생성 안 됨 (무한 루프 방지).
