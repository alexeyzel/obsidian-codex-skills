#!/usr/bin/env python3
"""Host-side runner for the n8n "Obsidian - Process Queue" workflow.

The runner exposes one fixed operation only:
- process configured Inbox/Queue notes;
- process unprocessed Meetings notes;
- refresh summaries;
- finalize queue deletion after summaries are current.

It prints one JSON document to stdout for n8n.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import fcntl
import json
import os
import re
import shutil
import shlex
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any


DEFAULT_VAULT = Path(os.environ.get("OBSIDIAN_VAULT", str(Path.home() / "obsidian/vault")))
DEFAULT_ENGINE = Path.home() / ".codex/obsidian-knowledge-skills/scripts/vault_engine.py"
DEFAULT_STATE_DIR = Path.home() / ".local/state/obsidian-process-queue"
DEFAULT_CODEX_BIN = str(Path.home() / ".local/bin/codex")
DEFAULT_CODEX_ARGS = "exec --skip-git-repo-check --sandbox read-only"
DEFAULT_MAX_CODEX_PROMPT_CHARS = 120000


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_id() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def count_tasks(payload: dict[str, Any]) -> int:
    tasks = payload.get("tasks", [])
    return len(tasks) if isinstance(tasks, list) else 0


def json_stdout(payload: dict[str, Any], code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


def resolve_codex_bin() -> str:
    configured = os.environ.get("CODEX_BIN", "").strip()
    if configured:
        return configured
    if Path(DEFAULT_CODEX_BIN).exists():
        return DEFAULT_CODEX_BIN
    return shutil.which("codex") or "codex"


class Runner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.vault = Path(args.vault).expanduser().resolve()
        self.engine = Path(args.engine).expanduser().resolve()
        self.state_dir = Path(args.state_dir).expanduser().resolve()
        self.queue_limit = args.queue_limit
        self.meeting_limit = args.meeting_limit
        self.summary_limit = args.summary_limit
        self.timeout = args.timeout
        self.max_codex_prompt_chars = args.max_codex_prompt_chars
        self.run_id = run_id()
        self.run_dir = self.state_dir / "runs" / self.run_id
        self.log_path = self.run_dir / "runner.log"
        self.started_at = utc_now()
        self.errors: list[dict[str, str]] = []

    def log(self, message: str) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        line = f"{utc_now()} {message}\n"
        self.log_path.open("a", encoding="utf-8").write(line)

    def preflight(self) -> None:
        if not self.vault.is_dir():
            raise RuntimeError(f"vault does not exist: {self.vault}")
        if not (self.vault / "Config.md").is_file():
            raise RuntimeError(f"vault Config.md is missing: {self.vault / 'Config.md'}")
        if not self.engine.is_file():
            raise RuntimeError(f"vault engine does not exist: {self.engine}")
        codex_bin = resolve_codex_bin()
        if Path(codex_bin).is_absolute() or "/" in codex_bin:
            if not Path(codex_bin).is_file():
                raise RuntimeError(f"codex binary does not exist: {codex_bin}")
        elif shutil.which(codex_bin) is None:
            raise RuntimeError(f"codex binary is not available on PATH: {codex_bin}")
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def run_command(
        self,
        name: str,
        command: list[str],
        stdout_path: Path | None = None,
        input_text: str | None = None,
    ) -> str:
        stdin_note = f" stdin_chars={len(input_text)}" if input_text is not None else ""
        self.log(f"START {name}: {shlex.join(command)}{stdin_note}")
        completed = subprocess.run(
            command,
            cwd=str(self.vault),
            text=True,
            encoding="utf-8",
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=self.timeout,
            check=False,
        )
        if stdout_path:
            stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path = self.run_dir / f"{name}.stderr.txt"
        if completed.stderr:
            stderr_path.write_text(completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError(
                f"{name} failed with code {completed.returncode}; stderr saved to {stderr_path}"
            )
        self.log(f"OK {name}")
        return completed.stdout

    def engine_cmd(self, name: str, *parts: str, stdout_path: Path | None = None) -> str:
        return self.run_command(
            name,
            ["python3", str(self.engine), *parts, "--vault", str(self.vault)],
            stdout_path=stdout_path,
        )

    def codex_cmd(self, name: str, prompt: str, output_path: Path, expected_key: str) -> dict[str, Any]:
        if len(prompt) > self.max_codex_prompt_chars:
            prompt_path = self.run_dir / f"{name}.prompt-too-large.txt"
            prompt_path.write_text(prompt, encoding="utf-8")
            raise RuntimeError(
                f"{name} prompt is too large: {len(prompt)} chars; "
                f"limit is {self.max_codex_prompt_chars}; saved to {prompt_path}"
            )
        codex_bin = resolve_codex_bin()
        codex_args = shlex.split(os.environ.get("CODEX_ARGS", DEFAULT_CODEX_ARGS))
        raw_path = self.run_dir / f"{name}.raw.txt"
        prompt_path = self.run_dir / f"{name}.prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        command = [codex_bin, *codex_args]
        raw = self.run_command(name, command, stdout_path=raw_path, input_text=prompt)
        payload = extract_json(raw)
        validate_codex_payload(payload, expected_key)
        write_json(output_path, payload)
        return payload

    def make_plan_prompt(self, queue_payload: dict[str, Any], meeting_payload: dict[str, Any]) -> str:
        return (
            "Use $vault-ingest and $vault-rules. "
            "Return ONLY valid JSON, with no Markdown fences and no commentary. "
            "Create one object with this exact top-level shape: {\"actions\":[...]}. "
            "Each action must follow the action_schema from the task payloads. "
            "Process queue sources with source_policy delete_after_success. "
            "Process meeting sources with source_policy keep_and_mark_processed. "
            "Do not do internet research. Preserve existing source wikilinks in notes_markdown. "
            "If you paraphrase source text, keep source wikilinks on the corresponding names and "
            "set preserve_links for source wikilinks that must remain connected to each update. "
            "Do not invent relationship links that were not present in the source. "
            "Follow language_policy and operating_rules from the payloads. "
            "\n\nQUEUE_TASK_PAYLOAD:\n"
            + json.dumps(queue_payload, ensure_ascii=False)
            + "\n\nMEETING_TASK_PAYLOAD:\n"
            + json.dumps(meeting_payload, ensure_ascii=False)
        )

    def make_summary_prompt(self, summary_payload: dict[str, Any]) -> str:
        return (
            "Use $vault-ingest for the summary step. "
            "Return ONLY valid JSON, with no Markdown fences and no commentary. "
            "Create one object with this exact top-level shape: {\"summaries\":[...]}. "
            "Each summary item must contain path and summary. "
            "Follow the instruction and language_policy from the payload. "
            "\n\nSUMMARY_TASK_PAYLOAD:\n"
            + json.dumps(summary_payload, ensure_ascii=False)
        )

    def fit_plan_payloads(
        self,
        queue_payload: dict[str, Any],
        meeting_payload: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, int]]:
        queue_fit = copy.deepcopy(queue_payload)
        meeting_fit = copy.deepcopy(meeting_payload)
        queue_tasks = queue_fit.get("tasks", [])
        meeting_tasks = meeting_fit.get("tasks", [])
        if not isinstance(queue_tasks, list):
            queue_fit["tasks"] = queue_tasks = []
        if not isinstance(meeting_tasks, list):
            meeting_fit["tasks"] = meeting_tasks = []

        original_queue = len(queue_tasks)
        original_meeting = len(meeting_tasks)
        while len(self.make_plan_prompt(queue_fit, meeting_fit)) > self.max_codex_prompt_chars:
            if queue_tasks:
                queue_tasks.pop()
            elif meeting_tasks:
                meeting_tasks.pop()
            else:
                break

        fitted_chars = len(self.make_plan_prompt(queue_fit, meeting_fit))
        if fitted_chars > self.max_codex_prompt_chars:
            raise RuntimeError(
                f"codex-ingest-plan prompt is too large even with an empty batch: "
                f"{fitted_chars} chars; limit is {self.max_codex_prompt_chars}"
            )
        if (not queue_tasks and not meeting_tasks) and (original_queue or original_meeting):
            raise RuntimeError(
                f"codex-ingest-plan prompt is too large for even one source task; "
                f"limit is {self.max_codex_prompt_chars}. Reduce max_llm_input_chars, "
                "split the largest source note, or increase MAX_CODEX_PROMPT_CHARS."
            )

        stats = {
            "original_queue_tasks": original_queue,
            "original_meeting_tasks": original_meeting,
            "used_queue_tasks": len(queue_tasks),
            "used_meeting_tasks": len(meeting_tasks),
            "deferred_queue_tasks": original_queue - len(queue_tasks),
            "deferred_meeting_tasks": original_meeting - len(meeting_tasks),
            "prompt_chars": fitted_chars,
        }
        if stats["deferred_queue_tasks"] or stats["deferred_meeting_tasks"]:
            self.log(
                "FIT codex-ingest-plan "
                f"prompt_chars={stats['prompt_chars']} "
                f"queue={stats['used_queue_tasks']}/{stats['original_queue_tasks']} "
                f"meeting={stats['used_meeting_tasks']}/{stats['original_meeting_tasks']} "
                f"limit={self.max_codex_prompt_chars}"
            )
        return queue_fit, meeting_fit, stats

    def run(self) -> dict[str, Any]:
        self.preflight()

        before_files = knowledge_files(self.vault)

        self.engine_cmd("index", "index")

        queue_tasks_path = self.run_dir / "queue-tasks.json"
        meeting_tasks_path = self.run_dir / "meeting-tasks.json"
        self.engine_cmd("queue-tasks", "queue-tasks", "--limit", str(self.queue_limit), stdout_path=queue_tasks_path)
        self.engine_cmd(
            "meeting-tasks",
            "meeting-tasks",
            "--limit",
            str(self.meeting_limit),
            stdout_path=meeting_tasks_path,
        )

        queue_payload = read_json(queue_tasks_path)
        meeting_payload = read_json(meeting_tasks_path)
        queue_payload, meeting_payload, fit_stats = self.fit_plan_payloads(queue_payload, meeting_payload)
        if fit_stats["deferred_queue_tasks"] or fit_stats["deferred_meeting_tasks"]:
            write_json(self.run_dir / "queue-tasks-used.json", queue_payload)
            write_json(self.run_dir / "meeting-tasks-used.json", meeting_payload)
            write_json(self.run_dir / "fit-plan-payloads.json", fit_stats)
        queue_count = count_tasks(queue_payload)
        meeting_count = count_tasks(meeting_payload)

        apply_result: dict[str, Any] = {"applied": [], "skipped": []}
        if queue_count or meeting_count:
            plan_path = self.run_dir / "ingest-plan.json"
            self.codex_cmd(
                "codex-ingest-plan",
                self.make_plan_prompt(queue_payload, meeting_payload),
                plan_path,
                "actions",
            )
            apply_raw = self.engine_cmd("apply-plan", "apply-plan", "--input", str(plan_path))
            apply_result = json.loads(apply_raw)
            write_json(self.run_dir / "apply-plan-result.json", apply_result)

        summary_tasks_path = self.run_dir / "summary-tasks.json"
        summary_paths = sorted(collect_targets(apply_result) | pending_queue_targets(self.vault))
        summary_payload: dict[str, Any] = {"tasks": []}
        if summary_paths:
            summary_args = ["summary-tasks", "--limit", str(self.summary_limit)]
            for path in summary_paths:
                summary_args.extend(["--path", path])
            self.engine_cmd("summary-tasks", *summary_args, stdout_path=summary_tasks_path)
            summary_payload = read_json(summary_tasks_path)
        else:
            write_json(summary_tasks_path, summary_payload)
        summary_count = count_tasks(summary_payload)
        summary_result: dict[str, Any] = {"updated": [], "skipped": []}
        if summary_count:
            summaries_path = self.run_dir / "summaries.json"
            self.codex_cmd(
                "codex-summaries",
                self.make_summary_prompt(summary_payload),
                summaries_path,
                "summaries",
            )
            summary_raw = self.engine_cmd("apply-summaries", "apply-summaries", "--input", str(summaries_path))
            summary_result = json.loads(summary_raw)
            write_json(self.run_dir / "apply-summaries-result.json", summary_result)

        finalize_raw = self.engine_cmd("finalize-queue", "finalize-queue")
        finalize_result = json.loads(finalize_raw)
        write_json(self.run_dir / "finalize-queue-result.json", finalize_result)

        after_files = knowledge_files(self.vault)
        created_notes = sorted(after_files - before_files)
        target_notes = collect_targets(apply_result)
        summary_updated = set(summary_result.get("updated", []))
        updated_notes = sorted((target_notes | summary_updated) - set(created_notes))
        skipped = collect_skipped(apply_result, summary_result, finalize_result, summary_payload)
        review_required = skipped[:]

        result = {
            "status": "success",
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": utc_now(),
            "vault": str(self.vault),
            "log_path": str(self.log_path),
            "counts": {
                "queue_tasks": queue_count,
                "meeting_tasks": meeting_count,
                "available_queue_tasks": fit_stats["original_queue_tasks"],
                "available_meeting_tasks": fit_stats["original_meeting_tasks"],
                "deferred_queue_tasks": fit_stats["deferred_queue_tasks"],
                "deferred_meeting_tasks": fit_stats["deferred_meeting_tasks"],
                "ingest_plan_prompt_chars": fit_stats["prompt_chars"],
                "summary_tasks": summary_count,
                "processed_files": len(collect_sources(apply_result)),
                "created_notes": len(created_notes),
                "updated_notes": len(updated_notes),
                "deleted_queue_notes": len(finalize_result.get("deleted", [])),
                "skipped_items": len(skipped),
                "review_required": len(review_required),
                "errors": 0,
            },
            "processed_files": sorted(collect_sources(apply_result)),
            "created_notes": created_notes,
            "updated_notes": updated_notes,
            "deleted_queue_notes": finalize_result.get("deleted", []),
            "skipped_items": skipped,
            "review_required": review_required,
            "errors": [],
        }
        result["summary_uk"] = ukrainian_summary(result)
        write_json(self.run_dir / "result.json", result)
        return result


def extract_json(raw: str) -> dict[str, Any]:
    stripped = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    if not stripped.startswith("{"):
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("Codex output is not a JSON object")
    return payload


def validate_codex_payload(payload: dict[str, Any], expected_key: str) -> None:
    value = payload.get(expected_key)
    if not isinstance(value, list):
        raise ValueError(f"Codex JSON must contain a list field: {expected_key}")
    if expected_key == "actions":
        for idx, action in enumerate(value):
            if not isinstance(action, dict):
                raise ValueError(f"actions[{idx}] is not an object")
            if action.get("kind") != "source":
                raise ValueError(f"actions[{idx}] has unsupported kind: {action.get('kind')!r}")
            if not action.get("source"):
                raise ValueError(f"actions[{idx}] is missing source")
            if action.get("source_policy") not in {"delete_after_success", "keep_and_mark_processed"}:
                raise ValueError(f"actions[{idx}] has invalid source_policy")
            if action.get("coverage") not in {"complete", "partial", "none"}:
                raise ValueError(f"actions[{idx}] has invalid coverage")
            if not isinstance(action.get("updates", []), list):
                raise ValueError(f"actions[{idx}].updates is not a list")
    if expected_key == "summaries":
        for idx, item in enumerate(value):
            if not isinstance(item, dict):
                raise ValueError(f"summaries[{idx}] is not an object")
            if not item.get("path") or not item.get("summary"):
                raise ValueError(f"summaries[{idx}] must contain path and summary")


def knowledge_files(vault: Path) -> set[str]:
    knowledge = vault / config_role_path(vault, "knowledge", "Knowledge")
    if not knowledge.exists():
        return set()
    return {path.relative_to(vault).as_posix() for path in knowledge.rglob("*.md")}


def pending_queue_targets(vault: Path) -> set[str]:
    state_file = vault / config_role_path(vault, "service", "Service") / "state" / "queue.json"
    if not state_file.exists():
        return set()
    try:
        state = read_json(state_file)
    except Exception:
        return set()
    targets: set[str] = set()
    if not isinstance(state, dict):
        return targets
    for record in state.values():
        if not isinstance(record, dict):
            continue
        for target in record.get("targets", []):
            if target:
                targets.add(str(target))
    return targets


def config_role_path(vault: Path, role: str, default: str) -> Path:
    config = vault / "Config.md"
    if not config.exists():
        return Path(default)
    text = config.read_text(encoding="utf-8-sig")
    in_folders = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("### Folders"):
            in_folders = True
            continue
        if in_folders and stripped.startswith("### "):
            break
        if not in_folders or not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] == role:
            return Path(cells[1].strip("/"))
    return Path(default)


def collect_sources(apply_result: dict[str, Any]) -> set[str]:
    sources: set[str] = set()
    for item in apply_result.get("applied", []):
        source = item.get("source")
        if source:
            sources.add(str(source))
    return sources


def collect_targets(apply_result: dict[str, Any]) -> set[str]:
    targets: set[str] = set()
    for item in apply_result.get("applied", []):
        for target in item.get("targets", []):
            if target:
                targets.add(str(target))
    return targets


def collect_skipped(*payloads: dict[str, Any]) -> list[dict[str, Any]]:
    skipped: list[dict[str, Any]] = []
    for payload in payloads:
        for item in payload.get("skipped", []):
            if isinstance(item, dict):
                skipped.append(item)
    summary_payload = payloads[-1] if payloads else {}
    for task in summary_payload.get("tasks", []):
        if isinstance(task, dict) and task.get("kind") == "summary_error":
            skipped.append({"path": task.get("path", ""), "reason": task.get("error", "summary error")})
    return skipped


def ukrainian_summary(result: dict[str, Any]) -> str:
    counts = result["counts"]
    parts = [
        f"Оброблено джерел: {counts['processed_files']}.",
        f"Створено нотаток: {counts['created_notes']}.",
        f"Оновлено нотаток: {counts['updated_notes']}.",
        f"Видалено нотаток з черги: {counts['deleted_queue_notes']}.",
        f"Пропущено елементів: {counts['skipped_items']}.",
        f"Потребують перевірки: {counts['review_required']}.",
        "Помилок немає." if counts["errors"] == 0 else f"Помилок: {counts['errors']}.",
    ]
    return " ".join(parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process Obsidian queue and meeting notes via Codex CLI")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT))
    parser.add_argument("--engine", default=str(DEFAULT_ENGINE))
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--queue-limit", type=int, default=int(os.environ.get("QUEUE_LIMIT", "10")))
    parser.add_argument("--meeting-limit", type=int, default=int(os.environ.get("MEETING_LIMIT", "10")))
    parser.add_argument("--summary-limit", type=int, default=int(os.environ.get("SUMMARY_LIMIT", "50")))
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("RUNNER_STEP_TIMEOUT", "1800")))
    parser.add_argument(
        "--max-codex-prompt-chars",
        type=int,
        default=int(os.environ.get("MAX_CODEX_PROMPT_CHARS", str(DEFAULT_MAX_CODEX_PROMPT_CHARS))),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_dir = Path(args.state_dir).expanduser().resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / "runner.lock"
    with lock_path.open("w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return json_stdout(
                {
                    "status": "busy",
                    "summary_uk": "Обробка Obsidian вже виконується. Новий запуск пропущено.",
                    "errors": [],
                }
            )

        runner = Runner(args)
        try:
            return json_stdout(runner.run())
        except Exception as exc:  # noqa: BLE001 - runner must always return JSON to n8n
            error = {
                "type": exc.__class__.__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
            try:
                runner.log(f"ERROR {error['type']}: {error['message']}")
                write_json(runner.run_dir / "error.json", error)
            except Exception:
                pass
            return json_stdout(
                {
                    "status": "error",
                    "run_id": runner.run_id,
                    "started_at": runner.started_at,
                    "finished_at": utc_now(),
                    "log_path": str(runner.log_path),
                    "summary_uk": f"Обробка Obsidian завершилась помилкою: {error['message']}",
                    "errors": [error],
                },
                code=1,
            )


if __name__ == "__main__":
    raise SystemExit(main())
