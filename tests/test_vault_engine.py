import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "scripts" / "vault_engine.py"
CONFIG = ROOT / "Config.md"


class VaultEngineTests(unittest.TestCase):
    def run_engine(self, vault: Path, *args: str) -> dict:
        command = [sys.executable, str(ENGINE), *args, "--vault", str(vault)]
        if "--config" not in args:
            command.extend(["--config", str(CONFIG)])
        result = subprocess.run(
            command,
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
                "English",
            )
            self.assertEqual(
                {item["topic"] for item in tasks["tasks"][0]["topic_candidates"]},
                {"Composite source", "Alpha Project", "Beta Topic"},
            )

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

    def test_source_task_payload_is_compact_and_prunes_weak_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            self.run_engine(vault, "init")
            exact = vault / "Knowledge" / "Projects" / "Alpha.md"
            exact.write_text(
                "---\n"
                "type: project\n"
                "---\n"
                "# Alpha\n\n"
                "## Summary\n"
                "{agent_summary}\n\n"
                "## My notes\n"
                "- Exact target.\n",
                encoding="utf-8",
            )
            weak = vault / "Knowledge" / "Projects" / "Weak Candidate.md"
            weak.write_text(
                "---\n"
                "type: project\n"
                "---\n"
                "# Weak Candidate\n\n"
                "## Summary\n"
                "{agent_summary}\n\n"
                "## My notes\n"
                "- Mentions Alpha only once in the body.\n",
                encoding="utf-8",
            )
            source = vault / "Inbox" / "Queue" / "Alpha.md"
            source.write_text("- Update [[Alpha]].\n", encoding="utf-8")

            tasks = self.run_engine(vault, "queue-tasks", "--limit", "10")
            task = tasks["tasks"][0]
            self.assertIn("allowed_types", tasks)
            self.assertIn("fallback_folder", tasks)
            self.assertNotIn("allowed_types", task)
            self.assertNotIn("fallback_folder", task)
            self.assertNotIn("candidate_targets", task)

            candidates = task["topic_candidates"][0]["candidate_targets"]
            self.assertEqual([candidate["title"] for candidate in candidates], ["Alpha"])
            self.assertEqual(candidates[0]["match"], "exact")
            self.assertEqual(set(candidates[0]), {"path", "title", "type", "score", "match"})

    def test_source_wikilinks_are_preserved_when_llm_returns_plain_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            self.run_engine(vault, "init")
            source = vault / "Inbox" / "Queue" / "DIA Support Project.md"
            source.write_text(
                "---\n"
                "type: project\n"
                "---\n"
                "# DIA Support Project\n\n"
                "## My notes\n"
                "- Donor: [[Alpha Org]]\n"
                "- Team: [[Jane Doe]]\n",
                encoding="utf-8",
            )

            tasks = self.run_engine(vault, "queue-tasks", "--limit", "10")
            self.assertIn("Preserve existing source wikilinks", tasks["instruction"])

            plan_file = vault / "plan.json"
            self.write_json(
                plan_file,
                {
                    "actions": [
                        {
                            "kind": "source",
                            "source": "Inbox/Queue/DIA Support Project.md",
                            "source_policy": "delete_after_success",
                            "coverage": "complete",
                            "updates": [
                                {
                                    "topic": "DIA Support Project",
                                    "decision": "create_new",
                                    "target_title": "DIA Support Project",
                                    "type": "project",
                                    "notes_markdown": "## My notes\n- Donor: Alpha Org\n- Team: Jane Doe",
                                }
                            ],
                        }
                    ]
                },
            )
            self.run_engine(vault, "apply-plan", "--input", str(plan_file), "--today", "2026-06-21")

            target_text = (vault / "Knowledge" / "Projects" / "DIA Support Project.md").read_text(encoding="utf-8")
            self.assertIn("- Donor: [[Alpha Org]]", target_text)
            self.assertIn("- Team: [[Jane Doe]]", target_text)
            self.assertEqual(target_text.count("## My notes"), 1)

    def test_restored_source_wikilinks_do_not_create_self_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            self.run_engine(vault, "init")
            source = vault / "Inbox" / "Queue" / "People.md"
            source.write_text("- [[Jane Doe]] is the project manager.\n", encoding="utf-8")

            plan_file = vault / "plan.json"
            self.write_json(
                plan_file,
                {
                    "actions": [
                        {
                            "kind": "source",
                            "source": "Inbox/Queue/People.md",
                            "source_policy": "delete_after_success",
                            "coverage": "complete",
                            "updates": [
                                {
                                    "topic": "Jane Doe",
                                    "decision": "create_new",
                                    "target_title": "Jane Doe",
                                    "type": "person",
                                    "notes_markdown": "- Jane Doe is the project manager.",
                                }
                            ],
                        }
                    ]
                },
            )
            self.run_engine(vault, "apply-plan", "--input", str(plan_file), "--today", "2026-06-21")

            target_text = (vault / "Knowledge" / "People" / "Jane Doe.md").read_text(encoding="utf-8")
            self.assertIn("- Jane Doe is the project manager.", target_text)
            self.assertNotIn("[[Jane Doe]]", target_text)

    def test_filename_topic_keeps_all_source_wikilinks_when_text_is_paraphrased(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            self.run_engine(vault, "init")
            source = vault / "Inbox" / "Queue" / "Softlist.md"
            source.write_text(
                "- Software developer.\n"
                "- Director [[Dmytro Prokopenko]] knows [[Oleksii Vyskub]] and [[Oleksandr Ryzhenko]].\n"
                "- The company is ok.\n",
                encoding="utf-8",
            )

            plan_file = vault / "plan.json"
            self.write_json(
                plan_file,
                {
                    "actions": [
                        {
                            "kind": "source",
                            "source": "Inbox/Queue/Softlist.md",
                            "source_policy": "delete_after_success",
                            "coverage": "complete",
                            "updates": [
                                {
                                    "topic": "Softlist",
                                    "decision": "create_new",
                                    "target_title": "Softlist",
                                    "type": "organization",
                                    "notes_markdown": "- Software developer with an acceptable reputation.",
                                }
                            ],
                        }
                    ]
                },
            )
            self.run_engine(vault, "apply-plan", "--input", str(plan_file), "--today", "2026-06-21")

            target_text = (vault / "Knowledge" / "Organizations" / "Softlist.md").read_text(encoding="utf-8")
            self.assertIn("[[Dmytro Prokopenko]]", target_text)
            self.assertIn("[[Oleksii Vyskub]]", target_text)
            self.assertIn("[[Oleksandr Ryzhenko]]", target_text)

    def test_linked_topic_keeps_wikilinks_from_same_source_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            self.run_engine(vault, "init")
            source = vault / "Inbox" / "Queue" / "Softlist.md"
            source.write_text(
                "- Director [[Dmytro Prokopenko]] knows [[Oleksii Vyskub]] and [[Oleksandr Ryzhenko]].\n",
                encoding="utf-8",
            )

            plan_file = vault / "plan.json"
            self.write_json(
                plan_file,
                {
                    "actions": [
                        {
                            "kind": "source",
                            "source": "Inbox/Queue/Softlist.md",
                            "source_policy": "delete_after_success",
                            "coverage": "complete",
                            "updates": [
                                {
                                    "topic": "Dmytro Prokopenko",
                                    "decision": "create_new",
                                    "target_title": "Dmytro Prokopenko",
                                    "type": "person",
                                    "notes_markdown": "- Director of Softlist.",
                                }
                            ],
                        }
                    ]
                },
            )
            self.run_engine(vault, "apply-plan", "--input", str(plan_file), "--today", "2026-06-21")

            target_text = (vault / "Knowledge" / "People" / "Dmytro Prokopenko.md").read_text(encoding="utf-8")
            self.assertIn("- Director of Softlist.", target_text)
            self.assertIn("Dmytro Prokopenko knows [[Oleksii Vyskub]] and [[Oleksandr Ryzhenko]]", target_text)
            self.assertNotIn("[[Dmytro Prokopenko]]", target_text)

    def test_preserve_links_can_keep_source_wikilinks_after_paraphrase(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            self.run_engine(vault, "init")
            source = vault / "Inbox" / "Queue" / "Composite.md"
            source.write_text("- Ask [[Jane Doe]] about [[Alpha Org]].\n", encoding="utf-8")

            plan_file = vault / "plan.json"
            self.write_json(
                plan_file,
                {
                    "actions": [
                        {
                            "kind": "source",
                            "source": "Inbox/Queue/Composite.md",
                            "source_policy": "delete_after_success",
                            "coverage": "complete",
                            "updates": [
                                {
                                    "topic": "Alpha Org",
                                    "decision": "create_new",
                                    "target_title": "Alpha Org",
                                    "type": "organization",
                                    "notes_markdown": "- Ask Jane about the organization.",
                                    "preserve_links": ["[[Jane Doe]]"],
                                }
                            ],
                        }
                    ]
                },
            )
            self.run_engine(vault, "apply-plan", "--input", str(plan_file), "--today", "2026-06-21")

            target_text = (vault / "Knowledge" / "Organizations" / "Alpha Org.md").read_text(encoding="utf-8")
            self.assertIn("[[Jane Doe]]", target_text)

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
                "English",
            )

            prep_task = self.run_engine(vault, "meeting-prep-task", "--calendar-title", "DIA Support", "--date", "2026-06-22")
            self.assertFalse(any(item["setting"].startswith("title") for item in prep_task["language_policy"]))
            self.assertTrue(any("natural/common name" in rule for rule in prep_task["operating_rules"]))

    def test_relative_config_paths_are_resolved_from_role_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            config_text = CONFIG.read_text(encoding="utf-8")
            config_text = config_text.replace("| inbox | Inbox |", "| inbox | _Inbox |")
            config_text = config_text.replace("| queue | Queue |", "| queue | QueueCustom |")
            config_text = config_text.replace("| knowledge | Knowledge |", "| knowledge | KnowledgeCustom |")
            config_text = config_text.replace("| fallback | Other |", "| fallback | OtherCustom |")
            config_text = config_text.replace("| service | Service |", "| service | ServiceCustom |")
            config_text = config_text.replace("| person | People |", "| person | PeopleCustom |")
            local_config = vault / "Config.md"
            local_config.write_text(config_text, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(ENGINE), "init", "--vault", str(vault)],
                cwd=ROOT,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            payload = json.loads(result.stdout)

            self.assertIn("_Inbox/QueueCustom", payload["created_or_checked"])
            self.assertIn("KnowledgeCustom/OtherCustom", payload["created_or_checked"])
            self.assertIn("KnowledgeCustom/PeopleCustom", payload["created_or_checked"])
            self.assertTrue((vault / "ServiceCustom" / "Templates" / "person.md").exists())
            self.assertFalse((vault / "ServiceCustom" / "Templates" / "Service").exists())

    def test_vault_config_is_default_config_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            config_text = CONFIG.read_text(encoding="utf-8")
            config_text = config_text.replace("| inbox | Inbox |", "| inbox | VaultInbox |")
            (vault / "Config.md").write_text(config_text, encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(ENGINE), "init", "--vault", str(vault)],
                cwd=vault,
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            payload = json.loads(result.stdout)

            self.assertEqual(Path(payload["config"]), (vault / "Config.md").resolve())
            self.assertTrue((vault / "VaultInbox").exists())
            self.assertFalse((vault / "Inbox").exists())

    def test_type_templates_follow_configured_template_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            config_text = CONFIG.read_text(encoding="utf-8")
            config_text = config_text.replace("| service | Service |", "| service | _Service |")
            config_text = config_text.replace("| knowledge_default | Templates/knowledge.md |", "| knowledge_default | Tmpl/knowledge.md |")
            config_text = config_text.replace("| meeting | Templates/meeting.md |", "| meeting | Tmpl/meeting.md |")
            local_config = vault / "Config.md"
            local_config.write_text(config_text, encoding="utf-8")

            self.run_engine(vault, "init", "--config", str(local_config))

            self.assertTrue((vault / "_Service" / "Tmpl" / "knowledge.md").exists())
            self.assertTrue((vault / "_Service" / "Tmpl" / "meeting.md").exists())
            self.assertTrue((vault / "_Service" / "Tmpl" / "person.md").exists())
            self.assertFalse((vault / "_Service" / "Templates" / "person.md").exists())

    def test_init_configures_obsidian_graph_search_for_knowledge_and_meetings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            self.run_engine(vault, "init")

            graph = json.loads((vault / ".obsidian" / "graph.json").read_text(encoding="utf-8"))
            self.assertEqual(graph["search"], '(path:"Knowledge" OR path:"Meetings")')
            self.assertFalse(graph["showTags"])

    def test_graph_search_uses_configured_folder_paths_and_preserves_existing_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            local_config = vault / "Config.md"
            config_text = CONFIG.read_text(encoding="utf-8")
            config_text = config_text.replace("| knowledge | Knowledge |", "| knowledge | Знання |")
            config_text = config_text.replace("| meetings | Meetings |", "| meetings | Зустрічі |")
            local_config.write_text(config_text, encoding="utf-8")
            graph_path = vault / ".obsidian" / "graph.json"
            graph_path.parent.mkdir(parents=True, exist_ok=True)
            graph_path.write_text(
                json.dumps({"search": "old", "showTags": True, "scale": 2}, ensure_ascii=False),
                encoding="utf-8",
            )

            self.run_engine(vault, "init", "--config", str(local_config))

            graph = json.loads(graph_path.read_text(encoding="utf-8"))
            self.assertEqual(graph["search"], '(path:"Знання" OR path:"Зустрічі")')
            self.assertTrue(graph["showTags"])
            self.assertEqual(graph["scale"], 2)

    def test_graph_search_management_can_be_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            local_config = vault / "Config.md"
            config_text = CONFIG.read_text(encoding="utf-8")
            config_text = config_text.replace("| manage_graph_search | yes |", "| manage_graph_search | no |")
            local_config.write_text(config_text, encoding="utf-8")

            self.run_engine(vault, "init", "--config", str(local_config))

            self.assertFalse((vault / ".obsidian" / "graph.json").exists())

    def test_meeting_template_uses_configured_meeting_section_headings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            config_text = CONFIG.read_text(encoding="utf-8")
            config_text = config_text.replace("| summary | Summary | {agent_summary} |", "| summary | Brief | {agent_summary} |")
            config_text = config_text.replace("| user_notes | My notes | {user_notes} |", "| user_notes | Notes | {user_notes} |")
            config_text = config_text.replace("| related | Related |  |", "| related | Context |  |")
            config_text = config_text.replace("| before | Before |", "| before | Before Call |")
            config_text = config_text.replace("| after | After |", "| after | Follow Up |")
            local_config = vault / "Config.md"
            local_config.write_text(config_text, encoding="utf-8")

            self.run_engine(vault, "init", "--config", str(local_config))

            meeting_template = (vault / "Service" / "Templates" / "meeting.md").read_text(encoding="utf-8")
            self.assertIn('date: "{{date}}"', meeting_template)
            self.assertIn('calendar_title: "{calendar_title}"', meeting_template)
            self.assertIn("# {{date}} - {title}", meeting_template)
            self.assertIn("## Brief\n{agent_summary}", meeting_template)
            self.assertIn("## Before Call\n-", meeting_template)
            self.assertIn("## Notes\n-", meeting_template)
            self.assertIn("## Follow Up\n-", meeting_template)
            self.assertIn("## Context\n-", meeting_template)
            self.assertNotIn("## My notes\n-", meeting_template)

            knowledge_template = (vault / "Service" / "Templates" / "person.md").read_text(encoding="utf-8")
            self.assertIn("## Context\n-", knowledge_template)

    def test_meeting_prep_renders_obsidian_date_template_and_valid_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            self.run_engine(vault, "init")
            payload_path = vault / "meeting-prep.json"
            self.write_json(
                payload_path,
                {
                    "target_path": "Meetings/2026-06-22 - DIA Support.md",
                    "summary": "Remember the current DIA Support project status before the meeting.",
                    "calendar_title": "DIA: Support",
                    "date": "2026-06-22",
                },
            )

            self.run_engine(vault, "apply-meeting-prep", "--input", str(payload_path))

            meeting_text = (vault / "Meetings" / "2026-06-22 - DIA Support.md").read_text(encoding="utf-8")
            self.assertIn("date: 2026-06-22", meeting_text)
            self.assertIn('calendar_title: "DIA: Support"', meeting_text)
            self.assertIn("# 2026-06-22 - DIA Support", meeting_text)
            self.assertNotIn("{{date}}", meeting_text)
            self.assertNotIn("{date}", meeting_text)
            self.assertNotIn("{title}", meeting_text)

    def test_reinit_adds_new_type_without_removing_old_type_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            local_config = vault / "Config.md"
            local_config.write_text(CONFIG.read_text(encoding="utf-8"), encoding="utf-8")

            self.run_engine(vault, "init", "--config", str(local_config))
            old_folder = vault / "Knowledge" / "Reference"
            self.assertTrue(old_folder.exists())

            config_text = local_config.read_text(encoding="utf-8")
            config_text = config_text.replace(
                "| reference | Reference | reference.md | Reference material, guidance, reusable instructions, and informational notes. |\n",
                "",
            )
            config_text = config_text.replace(
                "| topic | Topics | topic.md | General concepts, themes, policy areas, technologies, and reusable ideas. |",
                "| topic | Topics | topic.md | General concepts, themes, policy areas, technologies, and reusable ideas. |\n"
                "| decision | Decisions | decision.md | Durable decisions and rationale. |",
            )
            local_config.write_text(config_text, encoding="utf-8")

            self.run_engine(vault, "init", "--config", str(local_config))

            self.assertTrue((vault / "Knowledge" / "Decisions").exists())
            self.assertTrue((vault / "Service" / "Templates" / "decision.md").exists())
            self.assertTrue(old_folder.exists())


if __name__ == "__main__":
    unittest.main()
