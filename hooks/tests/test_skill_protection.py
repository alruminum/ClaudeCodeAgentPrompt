"""test_skill_protection.py — Phase 4 스킬 보호 레벨 매핑 테스트.

Run: python3 -m unittest discover -s ~/.claude/hooks/tests -p 'test_skill_protection.py' -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import skill_protection as sp  # noqa: E402


class GetSkillLevelTests(unittest.TestCase):
    def test_known_levels(self):
        self.assertEqual(sp.get_skill_level("ux"), "medium")
        self.assertEqual(sp.get_skill_level("qa"), "medium")
        self.assertEqual(sp.get_skill_level("product-plan"), "medium")
        self.assertEqual(sp.get_skill_level("init-project"), "medium")
        self.assertEqual(sp.get_skill_level("ralph"), "heavy")
        self.assertEqual(sp.get_skill_level("loop"), "heavy")
        self.assertEqual(sp.get_skill_level("ralph-loop:ralph-loop"), "heavy")
        self.assertEqual(sp.get_skill_level("update-config"), "light")
        self.assertEqual(sp.get_skill_level("harness-status"), "none")
        self.assertEqual(sp.get_skill_level("harness-kill"), "none")
        self.assertEqual(sp.get_skill_level("ralph-loop:cancel-ralph"), "none")

    def test_unknown_falls_back_to_default(self):
        self.assertEqual(sp.get_skill_level("nonexistent-skill-xyz"), sp.DEFAULT_LEVEL)

    def test_namespace_fallback(self):
        # plugin:skill 형태 → bare skill 단순명으로 fallback
        # 예: 가상의 `someplugin:ux` → 등록된 `ux` 매핑(medium)으로
        self.assertEqual(sp.get_skill_level("someplugin:ux"), "medium")
        # 단순명도 없으면 DEFAULT
        self.assertEqual(sp.get_skill_level("someplugin:nope"), sp.DEFAULT_LEVEL)

    def test_empty_name_is_none(self):
        self.assertEqual(sp.get_skill_level(""), "none")


class PolicyTests(unittest.TestCase):
    def test_policy_values(self):
        self.assertEqual(sp.get_policy("none"),   {"ttl_sec": 0,    "max_reinforcements": 0})
        self.assertEqual(sp.get_policy("light"),  {"ttl_sec": 300,  "max_reinforcements": 3})
        self.assertEqual(sp.get_policy("medium"), {"ttl_sec": 900,  "max_reinforcements": 5})
        self.assertEqual(sp.get_policy("heavy"),  {"ttl_sec": 1800, "max_reinforcements": 10})

    def test_unknown_level_uses_light(self):
        self.assertEqual(sp.get_policy("xxx"), sp.LEVEL_POLICIES["light"])


class IsProtectedTests(unittest.TestCase):
    def test_only_medium_heavy_protected(self):
        self.assertFalse(sp.is_protected("none"))
        self.assertFalse(sp.is_protected("light"))
        self.assertTrue(sp.is_protected("medium"))
        self.assertTrue(sp.is_protected("heavy"))


class ShouldBlockStopTests(unittest.TestCase):
    """SELF_MANAGED_LIFECYCLE 예외(ralph-loop 등) 검증."""

    def test_ralph_loop_not_blocked_even_heavy(self):
        # ralph-loop:ralph-loop는 자체 stop-hook이 lifecycle 관리 — Stop 차단 금지.
        self.assertFalse(sp.should_block_stop("ralph-loop:ralph-loop", "heavy"))
        self.assertFalse(sp.should_block_stop("ralph-loop", "heavy"))

    def test_other_heavy_blocked(self):
        # ralph(우리 wrapper)이나 loop 같은 heavy는 차단.
        self.assertTrue(sp.should_block_stop("ralph", "heavy"))
        self.assertTrue(sp.should_block_stop("loop", "heavy"))
        self.assertTrue(sp.should_block_stop("schedule", "heavy"))

    def test_medium_blocked(self):
        self.assertTrue(sp.should_block_stop("ux", "medium"))
        self.assertTrue(sp.should_block_stop("qa", "medium"))

    def test_light_and_none_not_blocked(self):
        self.assertFalse(sp.should_block_stop("update-config", "light"))
        self.assertFalse(sp.should_block_stop("harness-status", "none"))


class ClearsOnPostTests(unittest.TestCase):
    def test_heavy_does_not_clear(self):
        self.assertFalse(sp.clears_on_post("heavy"))

    def test_others_clear(self):
        for lvl in ("none", "light", "medium"):
            self.assertTrue(sp.clears_on_post(lvl), lvl)


if __name__ == "__main__":
    unittest.main()
