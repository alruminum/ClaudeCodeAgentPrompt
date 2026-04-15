"""
providers.py — 외부 AI 프로바이더 어댑터.
Second Reviewer v3: 파일별 분할 리뷰 + 2단계 프롬프트.
Python 3.9+ stdlib only.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# ═══════════════════════════════════════════════════════════════════════
# 프롬프트 템플릿
# ═══════════════════════════════════════════════════════════════════════

REVIEW_PROMPT_TEMPLATE = """파일: {filename}

변경 내용 (diff만):
{patch}

[지시]
위 diff만 보고 코드 품질 이슈를 리뷰하라.
- diff에 보이는 변경 줄만 분석
- 불필요한 주석, console.log, 미사용 import, 과도한 추상화, AI 생성 패턴에 집중
- 전체 파일 맥락이 반드시 필요한 경우에만 "NEED_FULL_FILE" 표시
- 이슈를 bullet list로. 없으면 "CLEAN"
"""

FULL_FILE_PROMPT_TEMPLATE = """파일: {filename}

전체 파일:
{content}

변경 내용 (diff):
{patch}

[지시] 전체 맥락 포함하여 코드 품질 이슈 리뷰. bullet list. 없으면 CLEAN.
"""


# ═══════════════════════════════════════════════════════════════════════
# 결과 데이터
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ReviewResult:
    provider: str
    filename: str
    findings: str  # 빈 문자열이면 CLEAN
    elapsed: float
    error: str = ""


# ═══════════════════════════════════════════════════════════════════════
# BaseProvider
# ═══════════════════════════════════════════════════════════════════════

class BaseProvider:
    """외부 AI 프로바이더 인터페이스."""
    name: str = ""
    cli_name: str = ""

    def is_available(self) -> bool:
        return bool(self.cli_name and shutil.which(self.cli_name))

    def _call_cli(self, prompt: str, model: str, timeout: int = 60) -> str:
        """CLI를 stdin pipe로 호출. 검증된 유일한 방식."""
        raise NotImplementedError

    def review_file(
        self, filename: str, patch: str, model: str = "", timeout: int = 60,
    ) -> ReviewResult:
        """단일 파일 리뷰. 2단계 프롬프트."""
        t0 = time.time()

        # 1차: diff만
        prompt = REVIEW_PROMPT_TEMPLATE.format(
            filename=filename, patch=patch[:5000],
        )
        try:
            result = self._call_cli(prompt, model, timeout)
        except Exception as e:
            return ReviewResult(self.name, filename, "", time.time() - t0, str(e))

        # NEED_FULL_FILE → 2차
        if "NEED_FULL_FILE" in result:
            try:
                full = Path(filename).read_text(encoding="utf-8", errors="replace")[:8000]
            except OSError:
                full = ""
            if full:
                prompt2 = FULL_FILE_PROMPT_TEMPLATE.format(
                    filename=filename, content=full, patch=patch[:3000],
                )
                try:
                    result = self._call_cli(prompt2, model, timeout)
                except Exception as e:
                    return ReviewResult(self.name, filename, "", time.time() - t0, str(e))

        # CLEAN 판정
        if not result or "CLEAN" in result.upper():
            return ReviewResult(self.name, filename, "", time.time() - t0)

        return ReviewResult(self.name, filename, result.strip(), time.time() - t0)


# ═══════════════════════════════════════════════════════════════════════
# GeminiProvider
# ═══════════════════════════════════════════════════════════════════════

class GeminiProvider(BaseProvider):
    name = "gemini"
    cli_name = "gemini"

    def _call_cli(self, prompt: str, model: str, timeout: int = 60) -> str:
        """gemini CLI: stdin pipe → stdout. 검증된 유일한 방식."""
        proc = subprocess.Popen(
            ["gemini", "--model", model or "gemini-2.5-flash"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise TimeoutError(f"gemini timeout ({timeout}s)")

        if proc.returncode != 0:
            if stderr and any(kw in stderr.lower() for kw in ("auth", "unauthorized", "api key")):
                raise PermissionError(f"gemini auth error: {stderr[:200]}")
            raise RuntimeError(f"gemini exit {proc.returncode}: {stderr[:200]}")

        return stdout.strip()


# ═══════════════════════════════════════════════════════════════════════
# CodexProvider (OpenAI Codex CLI)
# ═══════════════════════════════════════════════════════════════════════

class CodexProvider(BaseProvider):
    """OpenAI Codex CLI: `codex exec` 명령. OMC 참고."""
    name = "codex"
    cli_name = "codex"

    def _call_cli(self, prompt: str, model: str, timeout: int = 60) -> str:
        """codex exec: stdin pipe로 프롬프트 전달."""
        cmd = ["codex", "exec"]
        if model:
            cmd.extend(["--model", model])
        # OMC 방식: 500자 초과 시 stdin pipe
        if len(prompt) > 500 or "\n" in prompt:
            proc = subprocess.Popen(
                cmd + ["-"],  # "-" = stdin에서 읽기
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        else:
            proc = subprocess.Popen(
                cmd + [prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            prompt = None  # positional arg로 전달했으므로 stdin 불필요

        try:
            stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise TimeoutError(f"codex timeout ({timeout}s)")

        if proc.returncode != 0:
            raise RuntimeError(f"codex exit {proc.returncode}: {stderr[:200]}")

        return stdout.strip()


# ═══════════════════════════════════════════════════════════════════════
# 프로바이더 레지스트리 + 배치 실행
# ═══════════════════════════════════════════════════════════════════════

PROVIDERS = {
    "gemini": GeminiProvider,
    "codex": CodexProvider,
}


def get_provider(name: str) -> Optional[BaseProvider]:
    """프로바이더 인스턴스 반환. CLI 없으면 None."""
    cls = PROVIDERS.get(name)
    if cls is None:
        return None
    provider = cls()
    if not provider.is_available():
        print(f"[HARNESS] second_reviewer '{name}' CLI 없음 — 스킵")
        return None
    return provider


def run_review_batch(
    changed_files: List[str],
    reviewer_name: str,
    reviewer_model: str = "",
    timeout_per_file: int = 60,
) -> str:
    """파일별 리뷰 배치 실행. 발견 사항 합산 문자열 반환. 빈 문자열이면 CLEAN."""
    provider = get_provider(reviewer_name)
    if provider is None:
        return ""

    findings: List[str] = []
    for filename in changed_files:
        # 파일별 diff 추출
        r = subprocess.run(
            ["git", "diff", "HEAD~1", "--", filename],
            capture_output=True, text=True, timeout=10,
        )
        patch = r.stdout if r.returncode == 0 else ""
        if not patch or len(patch.splitlines()) < 3:
            continue

        result = provider.review_file(filename, patch, reviewer_model, timeout_per_file)
        if result.findings:
            findings.append(f"**{filename}**:\n{result.findings}")
        if result.error:
            print(f"[HARNESS] second_reviewer {filename}: {result.error}")

    return "\n\n".join(findings)
