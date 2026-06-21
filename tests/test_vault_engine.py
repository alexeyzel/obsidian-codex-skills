import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "scripts" / "vault_engine.py"
AGENTS = ROOT / "AGENTS.md"


class VaultEngineTests(unittest.TestCase):
    def run_engine(self, vault: Path, *args: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(ENGINE), *args, "--vault", str(vault), "--agents", str(AGENTS)],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return json.loads(result.stdout)

    def write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def apply_all_summaries(self, vault: Path) -> None:
        tasks = self.run_engine(vault, "summary-tasks", "--limit", "20")
        summaries = [
            {"path": task["path"], "summary": f"Summary for {task['title']}."}
            for task in tasks["tasks"]
            if task["kind"] == "summary"
        ]
        summary_file = vault / "summaries.json"
        self.write_json(summary_file, {"summaries": summaries})
        self.run_engine(vault, "apply-summaries", "--input", str(summary_file))

    def test_queue_source_can_update_multiple_targets_before_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            self.run_engine(vault, "init")
            source = vault / "Inbox" / "Queue" / "Composite source.md"
            source.write_text(
                "# Composite source\n\n"
                "- [[Alpha Project]] needs a delivery plan and owner.\n"
                "- [[Beta Topic]] is a reusable concept for future notes.\n",
                encoding="utf-8",
            )

            tasks = self.run_engine(vault, "queue-tasks", "--limit", "10")
            self.assertEqual(tasks["tasks"][0]["kind"], "source")
            self.assertEqual(tasks["tasks"][0]["source_policy"], "delete_after_success")
            self.assertEqual(
                next(item["value"] for item in tasks["language_policy"] if item["setting"] == "default_summary_language"),
                "Ukrainian",
            )
            self.assertEqual({item["topic"] for item in tasks["tasks"][0]["topic_candidates"]}, {"Composite source", "Alpha Project", "Beta Topic"})

            plan_file = vault / "plan.json"
            self.write_json(
                plan_file,
                {
                    "actions": [
                        {
                            "kind": "source",
                            "source": "Inbox/Queue/Composite source.md",
                            "source_policy": "delete_after_success",
                            "coverage": "complete",
                            "updates": [
                                {
                                    "topic": "Alpha Project",
                                    "decision": "create_new",
                                    "target_title": "Alpha Project",
                                    "type": "project",
                                    "notes_markdown": "- Needs a delivery plan and owner.",
                                },
                                {
                                    "topic": "Beta Topic",
                                    "decision": "create_new",
                                    "target_title": "Beta Topic",
                                    "type": "topic",
                                    "notes_markdown": "- Reusable concept for future notes.",
                                },
                            ],
                        }
                    ]
                },
            )
            self.run_engine(vault, "apply-plan", "--input", str(plan_file), "--today", "2026-06-21")

            self.assertTrue((vault / "Knowledge" / "Projects" / "Alpha Project.md").exists())
            self.assertTrue((vault / "Knowledge" / "Topics" / "Beta Topic.md").exists())
            self.assertTrue(source.exists())

            skipped = self.run_engine(vault, "finalize-queue")
            self.assertEqual(skipped["deleted"], [])
            self.assertTrue(source.exists())

            self.apply_all_summaries(vault)
            finalized = self.run_engine(vault, "finalize-queue")
            self.assertEqual(finalized["deleted"], ["Inbox/Queue/Composite source.md"])
            self.assertFalse(source.exists())

    def test_partial_queue_source_stays_with_agent_note(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            self.run_engine(vault, "init")
            source = vault / "Inbox" / "Queue" / "Partial.md"
            source.write_text("# Partial\n\n- Some ambiguous material.\n", encoding="utf-8")
            plan_file = vault / "plan.json"
            self.write_json(
                plan_file,
                {
                    "actions": [
                        {
                            "kind": "source",
                            "source": "Inbox/Queue/Partial.md",
                            "source_policy": "delete_after_success",
                            "coverage": "partial",
                            "reason": "not enough context to preserve all useful content",
                            "updates": [],
                        }
                    ]
                },
            )
            self.run_engine(vault, "apply-plan", "--input", str(plan_file))
            self.run_engine(vault, "finalize-queue")
            self.assertTrue(source.exists())
            self.assertIn("## Agent note", source.read_text(encoding="utf-8"))

    def test_meeting_source_fills_summary_and_marks_processed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            self.run_engine(vault, "init")
            source = vault / "Meetings" / "2026-06-21 - Sync.md"
            source.write_text(
                "---\n"
                "type: meeting\n"
                "date: 2026-06-21\n"
                "calendar_title: Sync\n"
                "agent_processed: false\n"
                "---\n"
                "# 2026-06-21 - Sync\n\n"
                "## Summary\n"
                "{agent_summary}\n\n"
                "## My notes\n"
                "- [[Alpha Project]] needs a delivery plan and owner.\n",
                encoding="utf-8",
            )

            tasks = self.run_engine(vault, "meeting-tasks", "--limit", "10")
            self.assertEqual(tasks["tasks"][0]["kind"], "source")
            self.assertEqual(tasks["tasks"][0]["source_policy"], "keep_and_mark_processed")
            self.assertTrue(tasks["tasks"][0]["has_summary_placeholder"])
            self.assertIn("language_policy", tasks)

            plan_file = vault / "meeting-plan.json"
            self.write_json(
                plan_file,
                {
                    "actions": [
                        {
                            "kind": "source",
                            "source": "Meetings/2026-06-21 - Sync.md",
                            "source_policy": "keep_and_mark_processed",
                            "source_summary": "Discussed Alpha Project ownership and the need for a delivery plan.",
                            "coverage": "complete",
                            "updates": [
                                {
                                    "topic": "Alpha Project",
                                    "decision": "create_new",
                                    "target_title": "Alpha Project",
                                    "type": "project",
                                    "notes_markdown": "- Needs a delivery plan and owner.",
                                }
                            ],
                        }
                    ]
                },
            )
            self.run_engine(vault, "apply-plan", "--input", str(plan_file))

            meeting_text = source.read_text(encoding="utf-8")
            self.assertIn("agent_processed: true", meeting_text)
            self.assertIn("Discussed Alpha Project ownership", meeting_text)
            self.assertNotIn("{agent_summary}", meeting_text)
            self.assertTrue((vault / "Knowledge" / "Projects" / "Alpha Project.md").exists())

    def test_language_policy_is_emitted_for_summary_and_meeting_prep(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            self.run_engine(vault, "init")
            note = vault / "Knowledge" / "Projects" / "Language Test.md"
            note.write_text(
                "---\n"
                "type: project\n"
                "---\n"
                "# Language Test\n\n"
                "## Summary\n"
                "{agent_summary}\n\n"
                "## My notes\n"
                "### 2026-06-21\n"
                "- English source text about DIA Support Project.\n",
                encoding="utf-8",
            )

            summary_tasks = self.run_engine(vault, "summary-tasks", "--limit", "10")
            self.assertEqual(
                next(item["value"] for item in summary_tasks["language_policy"] if item["setting"] == "default_summary_language"),
                "Ukrainian",
            )

            prep_task = self.run_engine(vault, "meeting-prep-task", "--calendar-title", "DIA Support", "--date", "2026-06-22")
            self.assertEqual(
                next(item["value"] for item in prep_task["language_policy"] if item["setting"] == "title_language_policy"),
                "natural_source_name",
            )


if __name__ == "__main__":
    unittest.main()
