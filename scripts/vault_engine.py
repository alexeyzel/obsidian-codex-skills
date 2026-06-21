#!/usr/bin/env python3
"""Generic Obsidian vault engine for Codex skills.

The engine is intentionally deterministic and domain-agnostic. It reads vault
roles, knowledge types, sections, templates, and limits from AGENTS.md Markdown
tables, then performs file mechanics around LLM decisions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


REQUIRED_FOLDER_ROLES = {"inbox", "queue", "meetings", "knowledge", "fallback", "service"}
AGENT_NOTE_HEADING = "Agent note"


@dataclass(frozen=True)
class FolderSpec:
    role: str
    path: str
    rules: str = ""


@dataclass(frozen=True)
class TypeSpec:
    type: str
    folder: str
    template: str
    description: str = ""


@dataclass(frozen=True)
class SectionSpec:
    role: str
    heading: str
    placeholder: str
    applies_to: tuple[str, ...]


@dataclass(frozen=True)
class TemplateSpec:
    role: str
    path: str
    rules: str = ""


@dataclass
class VaultSpec:
    agents_path: Path
    folders: dict[str, FolderSpec]
    types: dict[str, TypeSpec]
    sections: dict[str, SectionSpec]
    language_policy: list[dict[str, str]]
    templates: dict[str, TemplateSpec]
    limits: dict[str, int]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(read_text(path))


def write_json(path: Path, data: Any) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slash(path: Path) -> str:
    return path.as_posix()


def rel_to(root: Path, path: Path) -> str:
    return slash(path.resolve().relative_to(root.resolve()))


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def normalize_config_path(value: str) -> str:
    cleaned = str(value).replace("\\", "/").strip().strip("/")
    return re.sub(r"/+", "/", cleaned)


def config_path_is_within(path: str, parent: str) -> bool:
    path_norm = normalize_config_path(path)
    parent_norm = normalize_config_path(parent)
    return path_norm == parent_norm or path_norm.startswith(parent_norm + "/")


DEFAULT_ROLE_PATHS = {"inbox": "Inbox", "knowledge": "Knowledge", "service": "Service"}


def strip_config_prefix(path: str, prefix: str) -> str | None:
    path_norm = normalize_config_path(path)
    prefix_norm = normalize_config_path(prefix)
    if path_norm == prefix_norm:
        return ""
    if path_norm.startswith(prefix_norm + "/"):
        return path_norm[len(prefix_norm) + 1 :]
    return None


def config_join(parent: str, child: str, legacy_parent: str | None = None) -> str:
    parent_norm = normalize_config_path(parent)
    child_norm = normalize_config_path(child)
    if not parent_norm:
        return child_norm
    if not child_norm:
        return parent_norm
    if config_path_is_within(child_norm, parent_norm):
        return child_norm
    if legacy_parent:
        legacy_suffix = strip_config_prefix(child_norm, legacy_parent)
        if legacy_suffix is not None:
            return config_join(parent_norm, legacy_suffix)
    return f"{parent_norm}/{child_norm}"


def split_table_row(line: str) -> list[str]:
    raw = line.strip()
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        raw = raw[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in raw:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    cells.append("".join(current).strip())
    return cells


def extract_markdown_section(markdown: str, heading: str) -> str:
    pattern = re.compile(rf"(?ms)^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s+|\Z)")
    match = pattern.search(markdown)
    return match.group(1).strip() if match else ""


def parse_markdown_table(markdown: str, heading: str) -> list[dict[str, str]]:
    section = extract_markdown_section(markdown, heading)
    lines = [line for line in section.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return []
    headers = [normalize_key(cell) for cell in split_table_row(lines[0])]
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        cells = split_table_row(line)
        if len(cells) < len(headers):
            cells.extend([""] * (len(headers) - len(cells)))
        rows.append({headers[idx]: cells[idx].strip() for idx in range(len(headers))})
    return rows


def resolve_agents_path(vault: Path, supplied: str | None) -> Path:
    candidates: list[Path] = []
    if supplied:
        candidates.append(Path(supplied))
    candidates.append(vault / "AGENTS.md")
    candidates.append(Path.cwd() / "AGENTS.md")
    candidates.append(Path(__file__).resolve().parent.parent / "AGENTS.md")
    for candidate in candidates:
        candidate = candidate.expanduser()
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(
        "Could not find AGENTS.md. Pass --agents, add AGENTS.md to the vault, "
        "or install the runtime with the bundled default AGENTS.md."
    )


def parse_int(value: str, default: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def default_language_policy() -> list[dict[str, str]]:
    return [
        {
            "setting": "default_content_language",
            "value": "English",
            "rules": "Use for generated prose unless the source clearly requires another language.",
        },
        {
            "setting": "default_summary_language",
            "value": "English",
            "rules": "Write summaries and meeting preparation context in this language by default.",
        },
        {
            "setting": "title_language_policy",
            "value": "source_natural_name",
            "rules": (
                "Use the natural/common source name or explicit target title. Do not translate proper names. "
                "Prefer short readable titles over formal registry names unless the formal name is the common name."
            ),
        },
        {
            "setting": "preserve_source_language",
            "value": "yes",
            "rules": "Preserve user-authored excerpts, quotes, official titles, acronyms, and mixed-language terms.",
        },
        {
            "setting": "do_not_translate_proper_names",
            "value": "yes",
            "rules": "Do not translate person, organization, project, product, acronym, email, handle, or official names.",
        },
        {
            "setting": "mixed_language_allowed",
            "value": "yes",
            "rules": "Allow mixed language for official names, projects, acronyms, roles, and source-specific terms.",
        },
    ]


def load_spec(vault: Path, agents_path: str | None = None) -> VaultSpec:
    path = resolve_agents_path(vault, agents_path)
    text = read_text(path)

    raw_folders: dict[str, FolderSpec] = {}
    for row in parse_markdown_table(text, "Folders"):
        role = normalize_key(row.get("role", ""))
        folder_path = normalize_config_path(row.get("path", ""))
        if role and folder_path:
            raw_folders[role] = FolderSpec(role=role, path=folder_path, rules=row.get("rules", ""))
    missing = REQUIRED_FOLDER_ROLES - set(raw_folders)
    if missing:
        raise ValueError(f"AGENTS.md is missing required folder roles: {', '.join(sorted(missing))}")

    folders: dict[str, FolderSpec] = {}
    nested_folder_roles = {"queue": "inbox", "fallback": "knowledge"}
    for role, folder in raw_folders.items():
        folder_path = folder.path
        parent_role = nested_folder_roles.get(role)
        if parent_role:
            folder_path = config_join(
                raw_folders[parent_role].path,
                folder_path,
                legacy_parent=DEFAULT_ROLE_PATHS.get(parent_role),
            )
        folders[role] = FolderSpec(role=role, path=folder_path, rules=folder.rules)

    service_templates_root = config_join(folders["service"].path, "Templates")

    def resolve_knowledge_folder(value: str) -> str:
        return config_join(folders["knowledge"].path, value, legacy_parent=DEFAULT_ROLE_PATHS["knowledge"])

    def resolve_template(value: str) -> str:
        template_path = normalize_config_path(value)
        if config_path_is_within(template_path, folders["service"].path):
            return template_path
        legacy_service_suffix = strip_config_prefix(template_path, DEFAULT_ROLE_PATHS["service"])
        if legacy_service_suffix is not None:
            return config_join(folders["service"].path, legacy_service_suffix)
        if config_path_is_within(template_path, "Templates"):
            return config_join(folders["service"].path, template_path)
        return config_join(service_templates_root, template_path)

    types: dict[str, TypeSpec] = {}
    for row in parse_markdown_table(text, "Knowledge Types"):
        note_type = normalize_key(row.get("type", ""))
        folder = normalize_config_path(row.get("folder", ""))
        template = normalize_config_path(row.get("template", ""))
        if note_type and folder:
            folder = resolve_knowledge_folder(folder)
            template = resolve_template(template) if template else ""
            types[note_type] = TypeSpec(
                type=note_type,
                folder=folder,
                template=template,
                description=row.get("description", "").strip(),
            )

    sections: dict[str, SectionSpec] = {}
    for row in parse_markdown_table(text, "Note Sections"):
        role = normalize_key(row.get("role", ""))
        heading = row.get("heading", "").strip()
        placeholder = row.get("placeholder", "").strip()
        applies = tuple(
            normalize_key(part)
            for part in re.split(r"[,/]", row.get("applies_to", ""))
            if normalize_key(part)
        )
        if role and heading:
            sections[role] = SectionSpec(role=role, heading=heading, placeholder=placeholder, applies_to=applies)
    for role in ("summary", "user_notes"):
        if role not in sections:
            raise ValueError(f"AGENTS.md is missing required Note Sections role: {role}")

    language_policy: list[dict[str, str]] = []
    for row in parse_markdown_table(text, "Language Policy"):
        setting = normalize_key(row.get("setting", ""))
        value = row.get("value", "").strip()
        rules = row.get("rules", "").strip()
        if setting and value:
            language_policy.append({"setting": setting, "value": value, "rules": rules})
    if not language_policy:
        language_policy = default_language_policy()

    templates: dict[str, TemplateSpec] = {}
    for row in parse_markdown_table(text, "Templates"):
        role = normalize_key(row.get("role", ""))
        template_path = normalize_config_path(row.get("path", ""))
        if role and template_path:
            template_path = resolve_template(template_path)
            templates[role] = TemplateSpec(role=role, path=template_path, rules=row.get("rules", ""))

    templates.setdefault(
        "knowledge_default",
        TemplateSpec("knowledge_default", resolve_template("knowledge.md"), "Fallback knowledge template."),
    )
    templates.setdefault("meeting", TemplateSpec("meeting", resolve_template("meeting.md"), "Meeting template."))

    limits = {
        "max_llm_input_chars": 60000,
        "search_candidates": 8,
        "meeting_prep_context_notes": 5,
    }
    for row in parse_markdown_table(text, "Processing Limits"):
        setting = normalize_key(row.get("setting", ""))
        if setting:
            limits[setting] = parse_int(row.get("value", ""), limits.get(setting, 1))

    return VaultSpec(path, folders, types, sections, language_policy, templates, limits)


def folder_path(vault: Path, spec: VaultSpec, role: str) -> Path:
    return vault / spec.folders[role].path


def service_path(vault: Path, spec: VaultSpec, *parts: str) -> Path:
    return folder_path(vault, spec, "service").joinpath(*parts)


def cache_path(vault: Path, spec: VaultSpec, *parts: str) -> Path:
    return service_path(vault, spec, "cache", *parts)


def state_path(vault: Path, spec: VaultSpec, *parts: str) -> Path:
    return service_path(vault, spec, "state", *parts)


def log_path(vault: Path, spec: VaultSpec) -> Path:
    return service_path(vault, spec, "log", f"{datetime.now().strftime('%Y-%m')}.md")


def append_log(vault: Path, spec: VaultSpec, line: str) -> None:
    path = log_path(vault, spec)
    if not path.exists():
        write_text(path, "# Agent Log\n\n")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"- [{utc_now()}] {line}\n")


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = text[4:end].strip("\n")
    body = text[end + len("\n---") :].lstrip("\n")
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            data.setdefault(current_key, [])
            if isinstance(data[current_key], list):
                data[current_key].append(line[4:].strip().strip('"'))
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if value == "":
            data[key] = []
        elif value.lower() == "true":
            data[key] = True
        elif value.lower() == "false":
            data[key] = False
        elif value.startswith("[") and value.endswith("]"):
            try:
                data[key] = json.loads(value)
            except json.JSONDecodeError:
                data[key] = value
        else:
            data[key] = value.strip('"')
    return data, body


def format_frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif value is None:
            lines.append(f"{key}:")
        else:
            text = str(value)
            if any(char in text for char in [":", "#", "[", "]", "{", "}", ","]) and not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
                lines.append(f"{key}: {json.dumps(text, ensure_ascii=False)}")
            else:
                lines.append(f"{key}: {text}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def replace_frontmatter(text: str, data: dict[str, Any]) -> str:
    _old, body = parse_frontmatter(text)
    return format_frontmatter(data) + body.lstrip("\n")


def extract_h1(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def extract_headings(body: str) -> list[str]:
    return [match.group(2).strip() for match in re.finditer(r"^(#{1,6})\s+(.+)$", body, re.MULTILINE)]


def extract_links(text: str) -> list[str]:
    links: list[str] = []
    for match in re.finditer(r"\[\[([^\]]+)\]\]", text):
        target = match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            links.append(target)
    return sorted(set(links))


def sanitize_filename(title: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Untitled"


def markdown_wikilink(path: str) -> str:
    return f"[[{path[:-3] if path.endswith('.md') else path}]]"


def normalize_tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[\w\-']+", text.lower(), flags=re.UNICODE) if len(token) > 1]


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_vault_path(vault: Path, rel_path: str) -> Path:
    path = (vault / rel_path).resolve()
    if not is_within(path, vault):
        raise ValueError(f"Path escapes vault: {rel_path}")
    return path


def section_pattern(heading: str) -> re.Pattern[str]:
    return re.compile(rf"(?ms)^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s+|\Z)")


def section_content(body: str, heading: str) -> str | None:
    match = section_pattern(heading).search(body)
    return match.group(1).strip() if match else None


def normalize_markdown_block(value: Any) -> str:
    if isinstance(value, list):
        text = "\n".join(str(item).rstrip() for item in value)
    elif isinstance(value, str):
        text = value
    else:
        return ""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) >= 2 and lines[0].strip().startswith("```") and lines[-1].strip().startswith("```"):
        lines = lines[1:-1]
    return "\n".join(line.rstrip() for line in lines).strip()


def normalize_summary(value: Any) -> str:
    if isinstance(value, list):
        text = " ".join(str(item).strip() for item in value if str(item).strip())
    else:
        text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def replace_placeholder_or_section(
    text: str,
    spec: SectionSpec,
    replacement: str,
    *,
    append: bool = False,
    require_existing_target: bool = True,
) -> tuple[str, bool, str | None]:
    replacement = normalize_markdown_block(replacement)
    if not replacement:
        return text, False, "empty replacement"
    if spec.placeholder and spec.placeholder in text:
        return text.replace(spec.placeholder, replacement, 1), True, None
    fm, body = parse_frontmatter(text)
    pattern = section_pattern(spec.heading)
    match = pattern.search(body)
    if not match:
        if require_existing_target:
            return text, False, f"missing section '{spec.heading}' and placeholder '{spec.placeholder}'"
        new_body = body.rstrip() + f"\n\n## {spec.heading}\n{replacement}\n"
        return format_frontmatter(fm) + new_body, True, None
    if append:
        content = match.group(1).rstrip()
        if replacement in content:
            return text, False, None
        new_content = f"{content}\n\n{replacement}".strip() + "\n\n"
    else:
        new_content = replacement.strip() + "\n\n"
    new_body = body[: match.start(1)] + new_content + body[match.end(1) :]
    return format_frontmatter(fm) + new_body.rstrip() + "\n", True, None


def append_agent_note(path: Path, reason: str) -> None:
    text = read_text(path) if path.exists() else ""
    fm, body = parse_frontmatter(text)
    pattern = section_pattern(AGENT_NOTE_HEADING)
    body = pattern.sub("", body).rstrip()
    line = f"{utc_now()} skipped: {reason.strip()}"
    body = f"{body}\n\n## {AGENT_NOTE_HEADING}\n{line}\n".lstrip()
    write_text(path, (format_frontmatter(fm) if fm else "") + body)


def build_dated_block(markdown: str, heading: str) -> str:
    markdown = normalize_markdown_block(markdown)
    return f"### {heading}\n{markdown}"


def summary_source(text: str, spec: VaultSpec) -> str:
    summary = spec.sections["summary"]
    cleaned = text
    if summary.placeholder:
        cleaned = cleaned.replace(summary.placeholder, "")
    fm, body = parse_frontmatter(cleaned)
    pattern = section_pattern(summary.heading)
    body = pattern.sub(f"## {summary.heading}\n", body)
    return (format_frontmatter(fm) if fm else "") + body.strip()


def render_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def default_knowledge_template(spec: VaultSpec, note_type: str | None = None) -> str:
    summary = spec.sections["summary"]
    notes = spec.sections["user_notes"]
    fm = {"type": note_type} if note_type else {}
    prefix = format_frontmatter(fm) if fm else ""
    return (
        prefix
        + "# {title}\n\n"
        + f"## {summary.heading}\n{summary.placeholder}\n\n"
        + f"## {notes.heading}\n{notes.placeholder}\n"
    )


def default_meeting_template(spec: VaultSpec) -> str:
    summary = spec.sections["summary"]
    return (
        "---\n"
        "type: meeting\n"
        "date: {date}\n"
        "calendar_title: {calendar_title}\n"
        "agent_processed: false\n"
        "---\n"
        "# {date} - {title}\n\n"
        f"## {summary.heading}\n{summary.placeholder}\n\n"
        "## Before\n-\n\n"
        "## My notes\n-\n\n"
        "## After\n-\n\n"
        "## Related\n-\n"
    )


def template_for_type(vault: Path, spec: VaultSpec, note_type: str | None) -> tuple[str, Path | None]:
    if note_type and note_type in spec.types and spec.types[note_type].template:
        path = vault / spec.types[note_type].template
        if path.exists():
            return read_text(path), path
    default_path = vault / spec.templates["knowledge_default"].path
    if default_path.exists():
        return read_text(default_path), default_path
    return default_knowledge_template(spec, note_type), None


def target_path_for_new(vault: Path, spec: VaultSpec, title: str, note_type: str | None, fallback: bool = False) -> Path:
    filename = sanitize_filename(title) + ".md"
    if fallback or not note_type or note_type not in spec.types:
        return folder_path(vault, spec, "fallback") / filename
    return vault / spec.types[note_type].folder / filename


def scan_pages(vault: Path, spec: VaultSpec, include_text: bool = False) -> list[dict[str, Any]]:
    service_root = folder_path(vault, spec, "service").resolve()
    inbox_root = folder_path(vault, spec, "inbox").resolve()
    pages: list[dict[str, Any]] = []
    for path in sorted(vault.rglob("*.md")):
        resolved = path.resolve()
        if is_within(resolved, service_root) or is_within(resolved, inbox_root):
            continue
        text = read_text(path)
        fm, body = parse_frontmatter(text)
        rel = rel_to(vault, path)
        page = {
            "path": rel,
            "title": extract_h1(body) or path.stem,
            "frontmatter": fm,
            "type": fm.get("type", ""),
            "calendar_title": fm.get("calendar_title", ""),
            "agent_processed": fm.get("agent_processed"),
            "headings": extract_headings(body),
            "links": extract_links(text),
            "mtime": path.stat().st_mtime,
            "size": path.stat().st_size,
            "hash": sha256_text(text),
        }
        if include_text:
            page["text"] = text
        pages.append(page)
    return pages


def page_in_knowledge(vault: Path, spec: VaultSpec, page: dict[str, Any]) -> bool:
    return is_within(vault / page["path"], folder_path(vault, spec, "knowledge"))


def page_in_meetings(vault: Path, spec: VaultSpec, page: dict[str, Any]) -> bool:
    return is_within(vault / page["path"], folder_path(vault, spec, "meetings"))


def score_page(page: dict[str, Any], query: str, text: str) -> int:
    tokens = normalize_tokens(query)
    if not tokens:
        return 0
    haystacks = {
        "path": page.get("path", ""),
        "title": page.get("title", ""),
        "calendar": str(page.get("calendar_title", "")),
        "type": str(page.get("type", "")),
        "headings": " ".join(page.get("headings", [])),
        "body": text,
    }
    score = 0
    for token in tokens:
        if token in haystacks["path"].lower():
            score += 16
        if token in haystacks["title"].lower():
            score += 24
        if token in haystacks["calendar"].lower():
            score += 24
        if token in haystacks["type"].lower():
            score += 6
        if token in haystacks["headings"].lower():
            score += 8
        score += min(haystacks["body"].lower().count(token), 5)
    return score


def candidate_search(vault: Path, spec: VaultSpec, query: str, *, knowledge_only: bool = True, limit: int | None = None) -> list[dict[str, Any]]:
    limit = limit or spec.limits["search_candidates"]
    results: list[dict[str, Any]] = []
    for page in scan_pages(vault, spec, include_text=True):
        if knowledge_only and not page_in_knowledge(vault, spec, page):
            continue
        score = score_page(page, query, page.get("text", ""))
        if score <= 0:
            continue
        page = dict(page)
        page.pop("text", None)
        page["score"] = score
        results.append(page)
    results.sort(key=lambda item: (-item["score"], item["path"].lower()))
    return results[:limit]


def build_human_index(vault: Path, spec: VaultSpec, pages: list[dict[str, Any]]) -> str:
    lines = ["# Vault Index", ""]
    for page in pages:
        lines.append(f"- [[{page['path'][:-3]}]]")
    return "\n".join(lines).rstrip() + "\n"


def rebuild_index(vault: Path, spec: VaultSpec) -> dict[str, Any]:
    pages = scan_pages(vault, spec, include_text=False)
    write_json(cache_path(vault, spec, "pages.json"), pages)
    write_text(service_path(vault, spec, "index.md"), build_human_index(vault, spec, pages))
    return {"pages": len(pages), "cache": rel_to(vault, cache_path(vault, spec))}


def cmd_init(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    spec = load_spec(vault, args.agents)
    created: list[str] = []
    for folder in spec.folders.values():
        path = vault / folder.path
        path.mkdir(parents=True, exist_ok=True)
        created.append(folder.path)
    for type_spec in spec.types.values():
        path = vault / type_spec.folder
        path.mkdir(parents=True, exist_ok=True)
        created.append(type_spec.folder)
    for rel in ["cache", "state", "log", "Templates"]:
        path = service_path(vault, spec, rel)
        path.mkdir(parents=True, exist_ok=True)
        created.append(rel_to(vault, path))

    default_template = vault / spec.templates["knowledge_default"].path
    if args.overwrite_templates or not default_template.exists():
        write_text(default_template, default_knowledge_template(spec, None))
    meeting_template = vault / spec.templates["meeting"].path
    if args.overwrite_templates or not meeting_template.exists():
        write_text(meeting_template, default_meeting_template(spec))
    for type_spec in spec.types.values():
        if not type_spec.template:
            continue
        path = vault / type_spec.template
        if args.overwrite_templates or not path.exists():
            write_text(path, default_knowledge_template(spec, type_spec.type))

    write_json(state_path(vault, spec, "queue.json"), load_json(state_path(vault, spec, "queue.json"), {}))
    write_json(state_path(vault, spec, "summaries.json"), load_json(state_path(vault, spec, "summaries.json"), {}))
    print(json.dumps({"created_or_checked": sorted(set(created)), "agents": str(spec.agents_path)}, ensure_ascii=False, indent=2))
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    spec = load_spec(vault, args.agents)
    print(json.dumps(rebuild_index(vault, spec), ensure_ascii=False, indent=2))
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    spec = load_spec(vault, args.agents)
    results = candidate_search(vault, spec, args.query, knowledge_only=not args.all, limit=args.limit)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def source_too_large(text: str, spec: VaultSpec) -> bool:
    return len(text) > spec.limits["max_llm_input_chars"]


def allowed_type_items(spec: VaultSpec) -> list[dict[str, str]]:
    return [
        {"type": item.type, "folder": item.folder, "description": item.description}
        for item in spec.types.values()
    ]


def collect_candidate_targets(vault: Path, spec: VaultSpec, queries: list[str], *, limit: int | None = None) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    candidate_limit = limit or spec.limits["search_candidates"]
    for query in queries:
        if not query:
            continue
        for candidate in candidate_search(vault, spec, query, knowledge_only=True, limit=candidate_limit):
            candidates.setdefault(candidate["path"], candidate)
    return list(candidates.values())[:candidate_limit]


def build_source_task(vault: Path, spec: VaultSpec, source: Path, *, source_kind: str, source_policy: str) -> dict[str, Any]:
    text = read_text(source)
    fm, body = parse_frontmatter(text)
    rel = rel_to(vault, source)
    explicit_type = normalize_key(str(fm.get("type", "")))
    template_type = explicit_type if explicit_type in spec.types else None
    links = extract_links(text)
    title = extract_h1(body) or source.stem
    topic_candidates = [{"topic": source.stem, "source": "filename", "candidate_targets": collect_candidate_targets(vault, spec, [source.stem, title])}]
    for link in links:
        topic_candidates.append(
            {
                "topic": link,
                "source": "wikilink",
                "candidate_targets": collect_candidate_targets(vault, spec, [link]),
            }
        )
    queries = [source.stem, title, *links]
    summary = spec.sections["summary"]
    task: dict[str, Any] = {
        "kind": "source",
        "source_kind": source_kind,
        "source_policy": source_policy,
        "source": rel,
        "title": source.stem,
        "display_title": title,
        "template_type": template_type,
        "allowed_types": allowed_type_items(spec),
        "fallback_folder": spec.folders["fallback"].path,
        "topic_candidates": topic_candidates,
        "candidate_targets": collect_candidate_targets(vault, spec, queries),
        "source_text": text if not source_too_large(text, spec) else "",
        "error": "source exceeds max_llm_input_chars" if source_too_large(text, spec) else None,
    }
    if source_kind == "meeting":
        task.update(
            {
                "date": fm.get("date", ""),
                "calendar_title": fm.get("calendar_title", ""),
                "has_summary_placeholder": bool(summary.placeholder and summary.placeholder in text),
            }
        )
    return task


def cmd_queue_tasks(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    spec = load_spec(vault, args.agents)
    queue = folder_path(vault, spec, "queue")
    tasks: list[dict[str, Any]] = []
    for source in sorted(queue.glob("*.md")) if queue.exists() else []:
        tasks.append(build_source_task(vault, spec, source, source_kind="queue", source_policy="delete_after_success"))
        if len(tasks) >= args.limit:
            break
    payload = {
        "instruction": (
            "Each task is a source note. Use the same universal ingest flow for all sources: read "
            "the full source_text, inspect the filename topic and wikilinks in topic_candidates, "
            "identify every topic that has useful transferable knowledge, resolve target notes, and "
            "return updates. A queue source may produce zero, one, or many updates. If template_type "
            "is present, use it for the source filename topic when that topic becomes a new note; do "
            "not reclassify that topic. For linked topics, choose a configured type, fallback, or skip. "
            "Set coverage to complete only when all useful source content is represented in updates "
            "or explicitly ignored as not durable knowledge. Otherwise set coverage to partial or skipped "
            "with a compact reason. Follow language_policy when choosing target titles and generated prose. "
            "Do not create relationship links."
        ),
        "language_policy": spec.language_policy,
        "action_schema": {
            "kind": "source",
            "source": "Inbox/Queue/example.md",
            "source_policy": "delete_after_success",
            "coverage": "complete|partial|skipped",
            "reason": "required when coverage is not complete",
            "updates": [
                {
                    "topic": "filename topic or wikilink",
                    "decision": "update_existing|create_new|fallback|skip",
                    "target_path": "Knowledge/Type/Existing.md",
                    "target_title": "New title",
                    "type": "configured type unless fallback",
                    "notes_markdown": "Relevant source content to append under user_notes",
                    "reason": "required when skipped",
                }
            ],
        },
        "tasks": tasks,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_meeting_tasks(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    spec = load_spec(vault, args.agents)
    meetings = folder_path(vault, spec, "meetings")
    tasks: list[dict[str, Any]] = []
    for source in sorted(meetings.glob("*.md")) if meetings.exists() else []:
        text = read_text(source)
        fm, _body = parse_frontmatter(text)
        if fm.get("agent_processed") is True and not args.force:
            continue
        tasks.append(build_source_task(vault, spec, source, source_kind="meeting", source_policy="keep_and_mark_processed"))
        if len(tasks) >= args.limit:
            break
    payload = {
        "instruction": (
            "Each task is a source note. Use the same universal ingest flow for all sources: read "
            "the full source_text, inspect the filename topic and wikilinks in topic_candidates, "
            "identify every topic that has useful transferable knowledge, resolve target notes, and "
            "return updates. Meeting notes are never deleted or renamed. If has_summary_placeholder is "
            "true, also return source_summary as one useful paragraph for the meeting itself. Return an "
            "update only when source text clearly belongs to that topic. The notes_markdown may be "
            "shortened or paraphrased, but preserve useful Markdown structure. Follow language_policy when "
            "choosing target titles and generated prose. Do not create relationship links."
        ),
        "language_policy": spec.language_policy,
        "action_schema": {
            "kind": "source",
            "source": "Meetings/example.md",
            "source_policy": "keep_and_mark_processed",
            "source_summary": "one paragraph, required only when has_summary_placeholder is true",
            "coverage": "complete|partial|skipped",
            "reason": "required when coverage is not complete",
            "updates": [
                {
                    "topic": "filename topic or wikilink",
                    "decision": "update_existing|create_new|fallback|skip",
                    "target_path": "Knowledge/Type/Existing.md",
                    "target_title": "New title",
                    "type": "configured type unless fallback",
                    "notes_markdown": "Relevant excerpt for this link",
                    "reason": "required when skipped",
                }
            ],
        },
        "tasks": tasks,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def ensure_target_note(vault: Path, spec: VaultSpec, action: dict[str, Any]) -> tuple[Path | None, str | None, bool]:
    decision = str(action.get("decision", "")).strip()
    if decision == "skip":
        return None, str(action.get("reason", "skipped")), False
    note_type = normalize_key(str(action.get("type", "")))
    fallback = decision == "fallback" or note_type not in spec.types
    target_path_value = str(action.get("target_path", "")).strip()
    if decision == "update_existing" and target_path_value:
        target = safe_vault_path(vault, target_path_value)
    else:
        title = str(action.get("target_title", "")).strip()
        if not title:
            return None, "missing target_title", False
        target = target_path_for_new(vault, spec, title, note_type, fallback=fallback)
    if not is_within(target, folder_path(vault, spec, "knowledge")):
        return None, "target outside knowledge folder", False
    created = False
    if not target.exists():
        title = target.stem
        template, _template_path = template_for_type(vault, spec, None if fallback else note_type)
        rendered = render_template(
            template,
            {
                "title": title,
                "type": "" if fallback else note_type,
                "agent_summary": spec.sections["summary"].placeholder,
                "user_notes": spec.sections["user_notes"].placeholder,
            },
        )
        if not rendered.lstrip().startswith("---") and not fallback and note_type:
            rendered = format_frontmatter({"type": note_type}) + rendered
        write_text(target, rendered.rstrip() + "\n")
        created = True
    return target, None, created


def source_policy_for_path(vault: Path, spec: VaultSpec, source: Path) -> str | None:
    if is_within(source, folder_path(vault, spec, "queue")):
        return "delete_after_success"
    if is_within(source, folder_path(vault, spec, "meetings")):
        return "keep_and_mark_processed"
    return None


def normalize_updates(action: dict[str, Any]) -> list[dict[str, Any]]:
    updates = action.get("updates")
    if isinstance(updates, list):
        return [item for item in updates if isinstance(item, dict)]
    return []


def apply_source_update(
    vault: Path,
    spec: VaultSpec,
    source_rel: str,
    update: dict[str, Any],
    heading: str,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    topic = str(update.get("topic", update.get("link", ""))).strip()
    if str(update.get("decision", "")).strip() == "skip":
        return None, None
    notes = normalize_markdown_block(update.get("notes_markdown"))
    if not notes:
        return None, {"source": source_rel, "topic": topic, "reason": "missing notes_markdown"}
    target, error, created = ensure_target_note(vault, spec, update)
    if error or not target:
        return None, {"source": source_rel, "topic": topic, "reason": error or "target error"}
    text = read_text(target)
    block = build_dated_block(notes, heading)
    new_text, changed, error = replace_placeholder_or_section(text, spec.sections["user_notes"], block, append=True)
    if error:
        return None, {"source": source_rel, "topic": topic, "reason": error}
    if changed:
        write_text(target, new_text)
    return {
        "source": source_rel,
        "target": rel_to(vault, target),
        "topic": topic,
        "action": "created" if created else "updated",
    }, None


def apply_source_action(vault: Path, spec: VaultSpec, action: dict[str, Any], today: str) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    skipped: list[dict[str, str]] = []
    source_rel = str(action.get("source", "")).strip()
    if not source_rel:
        return None, [{"source": "", "reason": "missing source"}]
    source = safe_vault_path(vault, source_rel)
    if not source.exists():
        return None, [{"source": source_rel, "reason": "source missing"}]
    policy = str(action.get("source_policy", "")).strip() or source_policy_for_path(vault, spec, source)
    if policy == "delete_after_success":
        if not is_within(source, folder_path(vault, spec, "queue")):
            return None, [{"source": source_rel, "reason": "source outside queue"}]
    elif policy == "keep_and_mark_processed":
        if not is_within(source, folder_path(vault, spec, "meetings")):
            return None, [{"source": source_rel, "reason": "source outside meetings"}]
    else:
        return None, [{"source": source_rel, "reason": "unknown source policy"}]

    original_source_hash = sha256_text(read_text(source))
    coverage = str(action.get("coverage", "")).strip().lower() or "partial"
    reason = str(action.get("reason", "")).strip()
    updates = normalize_updates(action)
    applied: list[dict[str, Any]] = []
    had_errors = False

    if coverage in {"skipped", "skip"}:
        compact_reason = reason or "skipped by LLM"
        if policy == "delete_after_success":
            append_agent_note(source, compact_reason)
        return None, [{"source": source_rel, "reason": compact_reason}]

    if policy == "keep_and_mark_processed":
        meeting_text = read_text(source)
        placeholder = spec.sections["summary"].placeholder
        source_summary = normalize_summary(action.get("source_summary", action.get("summary")))
        if placeholder and placeholder in meeting_text:
            if not source_summary:
                skipped.append({"source": source_rel, "reason": "missing source_summary for meeting summary placeholder"})
                had_errors = True
            else:
                meeting_text = meeting_text.replace(placeholder, source_summary, 1)
                write_text(source, meeting_text)

    heading = today if policy == "delete_after_success" else markdown_wikilink(source_rel)
    for update in updates:
        result, error = apply_source_update(vault, spec, source_rel, update, heading)
        if result:
            applied.append(result)
        if error:
            skipped.append(error)
            had_errors = True

    if policy == "delete_after_success":
        if coverage != "complete":
            append_agent_note(source, reason or "source coverage is not complete")
            had_errors = True
        if not applied:
            append_agent_note(source, reason or "no target updates were applied")
            had_errors = True

    if policy == "keep_and_mark_processed" and coverage != "complete":
        skipped.append({"source": source_rel, "reason": reason or "source coverage is not complete"})
        had_errors = True

    if policy == "keep_and_mark_processed" and not had_errors:
        latest = read_text(source)
        latest_fm, latest_body = parse_frontmatter(latest)
        latest_fm["agent_processed"] = True
        write_text(source, format_frontmatter(latest_fm) + latest_body)

    if had_errors:
        return {
            "source": source_rel,
            "source_policy": policy,
            "coverage": coverage,
            "targets": sorted({item["target"] for item in applied}),
            "finalize_after_summaries": False,
        }, skipped

    return {
        "source": source_rel,
        "source_policy": policy,
        "coverage": coverage,
        "source_hash": original_source_hash,
        "targets": sorted({item["target"] for item in applied}),
        "processed_at": utc_now(),
        "status": "applied",
        "finalize_after_summaries": policy == "delete_after_success" and coverage == "complete",
    }, skipped


def cmd_apply_plan(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    spec = load_spec(vault, args.agents)
    payload = load_json(Path(args.input), {})
    actions = payload.get("actions", payload if isinstance(payload, list) else [])
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    queue_state_path = state_path(vault, spec, "queue.json")
    queue_state = load_json(queue_state_path, {})
    today = args.today or date.today().isoformat()
    for action in actions:
        kind = str(action.get("kind", "")).strip()
        if kind == "source":
            result, errors = apply_source_action(vault, spec, action, today)
            if result:
                applied.append(result)
                if result.get("finalize_after_summaries"):
                    queue_state[result["source"]] = {
                        "targets": result.get("targets", []),
                        "source_hash": result.get("source_hash", ""),
                        "applied_at": utc_now(),
                        "summary_required": True,
                    }
            skipped.extend(errors)
        else:
            skipped.append({"source": str(action.get("source", "")), "reason": f"unknown action kind '{kind}'"})
    write_json(queue_state_path, queue_state)
    append_log(vault, spec, f"APPLY_PLAN applied={len(applied)} skipped={len(skipped)}")
    index_result = rebuild_index(vault, spec)
    print(json.dumps({"applied": applied, "skipped": skipped, "index": index_result}, ensure_ascii=False, indent=2))
    return 0


def cmd_summary_tasks(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    spec = load_spec(vault, args.agents)
    state = load_json(state_path(vault, spec, "summaries.json"), {})
    tasks: list[dict[str, Any]] = []
    for path in sorted(folder_path(vault, spec, "knowledge").rglob("*.md")):
        rel = rel_to(vault, path)
        if args.path and rel not in args.path and path.name not in args.path and path.stem not in args.path:
            continue
        text = read_text(path)
        source = summary_source(text, spec)
        source_hash = sha256_text(source)
        if not args.all and state.get(rel, {}).get("source_hash") == source_hash:
            continue
        if source_too_large(source, spec):
            tasks.append({"kind": "summary_error", "path": rel, "error": "note exceeds max_llm_input_chars"})
        else:
            tasks.append(
                {
                    "kind": "summary",
                    "path": rel,
                    "title": extract_h1(parse_frontmatter(text)[1]) or path.stem,
                    "note_text_without_summary": source,
                    "current_summary": section_content(parse_frontmatter(text)[1], spec.sections["summary"].heading) or "",
                }
            )
        if len(tasks) >= args.limit:
            break
    payload = {
        "instruction": (
            "For each summary task, write one high-quality paragraph that captures the essential "
            "meaning of note_text_without_summary. Do not copy existing summary text or the first "
            "bullet list. Follow language_policy for summary language and proper names. Return "
            "{\"summaries\":[{\"path\":\"...\",\"summary\":\"one paragraph\"}]}."
        ),
        "language_policy": spec.language_policy,
        "tasks": tasks,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_apply_summaries(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    spec = load_spec(vault, args.agents)
    payload = load_json(Path(args.input), {})
    summaries = payload.get("summaries", payload if isinstance(payload, list) else [])
    state_file = state_path(vault, spec, "summaries.json")
    state = load_json(state_file, {})
    updated: list[str] = []
    skipped: list[dict[str, str]] = []
    for item in summaries:
        rel = str(item.get("path", "")).strip()
        summary = normalize_summary(item.get("summary"))
        if not rel or not summary:
            skipped.append({"path": rel, "reason": "missing path or summary"})
            continue
        path = safe_vault_path(vault, rel)
        if not path.exists() or not is_within(path, folder_path(vault, spec, "knowledge")):
            skipped.append({"path": rel, "reason": "missing knowledge note"})
            continue
        text = read_text(path)
        new_text, changed, error = replace_placeholder_or_section(text, spec.sections["summary"], summary, append=False)
        if error:
            skipped.append({"path": rel, "reason": error})
            continue
        if changed:
            write_text(path, new_text)
            updated.append(rel)
        state[rel] = {"source_hash": sha256_text(summary_source(read_text(path), spec)), "updated_at": utc_now()}
    write_json(state_file, state)
    append_log(vault, spec, f"APPLY_SUMMARIES updated={len(updated)} skipped={len(skipped)}")
    print(json.dumps({"updated": updated, "skipped": skipped}, ensure_ascii=False, indent=2))
    return 0


def cmd_finalize_queue(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    spec = load_spec(vault, args.agents)
    queue_state_file = state_path(vault, spec, "queue.json")
    queue_state = load_json(queue_state_file, {})
    summaries = load_json(state_path(vault, spec, "summaries.json"), {})
    deleted: list[str] = []
    skipped: list[dict[str, str]] = []
    for source_rel, record in list(queue_state.items()):
        source = safe_vault_path(vault, source_rel)
        if not source.exists():
            queue_state.pop(source_rel, None)
            continue
        recorded_hash = str(record.get("source_hash", ""))
        if recorded_hash and sha256_text(read_text(source)) != recorded_hash:
            skipped.append({"source": source_rel, "reason": "source changed after apply"})
            continue
        targets = record.get("targets", [])
        if not isinstance(targets, list):
            legacy_target = str(record.get("target", "")).strip()
            targets = [legacy_target] if legacy_target else []
        targets = [str(item).strip() for item in targets if str(item).strip()]
        if not targets:
            skipped.append({"source": source_rel, "reason": "no target records"})
            continue
        missing_target = False
        summary_pending = False
        for target_rel in targets:
            target = safe_vault_path(vault, target_rel)
            if not target.exists():
                skipped.append({"source": source_rel, "target": target_rel, "reason": "target missing"})
                missing_target = True
                break
            source_hash = sha256_text(summary_source(read_text(target), spec))
            if summaries.get(target_rel, {}).get("source_hash") != source_hash:
                skipped.append({"source": source_rel, "target": target_rel, "reason": "target summary not applied"})
                summary_pending = True
                break
        if missing_target or summary_pending:
            continue
        source.unlink()
        deleted.append(source_rel)
        queue_state.pop(source_rel, None)
    write_json(queue_state_file, queue_state)
    append_log(vault, spec, f"FINALIZE_QUEUE deleted={len(deleted)} skipped={len(skipped)}")
    print(json.dumps({"deleted": deleted, "skipped": skipped}, ensure_ascii=False, indent=2))
    return 0


def cmd_meeting_prep_task(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    spec = load_spec(vault, args.agents)
    filename_title = sanitize_filename(args.calendar_title)
    prefix = args.date if not args.time else f"{args.date} {args.time.replace(':', '-')}"
    target = folder_path(vault, spec, "meetings") / f"{prefix} - {filename_title}.md"
    query = args.calendar_title
    candidates = candidate_search(vault, spec, query, knowledge_only=False, limit=50)
    candidates = [candidate for candidate in candidates if page_in_meetings(vault, spec, candidate) or page_in_knowledge(vault, spec, candidate)]
    candidates.sort(key=lambda item: item.get("mtime", 0), reverse=True)
    selected = candidates[: spec.limits["meeting_prep_context_notes"]]
    budget = spec.limits["max_llm_input_chars"]
    contexts: list[dict[str, Any]] = []
    used = 0
    for candidate in selected:
        path = vault / candidate["path"]
        text = read_text(path)
        if used + len(text) > budget:
            contexts.append({"path": candidate["path"], "title": candidate["title"], "omitted": "context limit"})
            continue
        used += len(text)
        contexts.append({"path": candidate["path"], "title": candidate["title"], "mtime": candidate["mtime"], "text": text})
    payload = {
        "instruction": (
            "Create one paragraph of preparation context for the future meeting. Use the supplied "
            "calendar_title, date, and recent relevant context notes. Focus on what should be "
            "remembered before the meeting. Follow language_policy for summary language and proper names. "
            "Return {\"target_path\":\"...\",\"summary\":\"...\"}."
        ),
        "language_policy": spec.language_policy,
        "exists": target.exists(),
        "target_path": rel_to(vault, target),
        "calendar_title": args.calendar_title,
        "date": args.date,
        "time": args.time or "",
        "context_notes": contexts,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_apply_meeting_prep(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser().resolve()
    spec = load_spec(vault, args.agents)
    payload = load_json(Path(args.input), {})
    target_rel = str(payload.get("target_path", "")).strip()
    if not target_rel:
        print(json.dumps({"created": None, "skipped": "missing target_path"}, ensure_ascii=False, indent=2))
        return 1
    target = safe_vault_path(vault, target_rel)
    if target.exists():
        print(json.dumps({"created": None, "skipped": "meeting note already exists"}, ensure_ascii=False, indent=2))
        return 0
    if not is_within(target, folder_path(vault, spec, "meetings")):
        print(json.dumps({"created": None, "skipped": "target outside meetings folder"}, ensure_ascii=False, indent=2))
        return 1
    template_path = vault / spec.templates["meeting"].path
    template = read_text(template_path) if template_path.exists() else default_meeting_template(spec)
    summary = normalize_summary(payload.get("summary")) or spec.sections["summary"].placeholder
    calendar_title = str(payload.get("calendar_title", "")).strip()
    meeting_date = str(payload.get("date", "")).strip()
    title = target.stem
    title = re.sub(r"^\d{4}-\d{2}-\d{2}(?: \d{2}-\d{2})? - ", "", title)
    rendered = render_template(
        template,
        {
            "title": title,
            "date": meeting_date,
            "calendar_title": calendar_title,
            "agent_summary": summary,
        },
    )
    write_text(target, rendered.rstrip() + "\n")
    append_log(vault, spec, f"MEETING_PREP created={target_rel}")
    print(json.dumps({"created": target_rel}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generic Obsidian vault engine for Codex skills")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--vault", required=True)
        p.add_argument(
            "--agents",
            help="Path to AGENTS.md. Defaults to vault/AGENTS.md, then ./AGENTS.md, then runtime default.",
        )

    p = sub.add_parser("init", help="create configured folders, templates, and service state")
    add_common(p)
    p.add_argument("--overwrite-templates", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("index", help="build rebuildable page cache and human index")
    add_common(p)
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("search", help="generic candidate search")
    add_common(p)
    p.add_argument("--query", required=True)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--all", action="store_true", help="search meetings and knowledge, not only knowledge")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("queue-tasks", help="emit queue source tasks for LLM planning")
    add_common(p)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_queue_tasks)

    p = sub.add_parser("meeting-tasks", help="emit unprocessed meeting source tasks for LLM planning")
    add_common(p)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_meeting_tasks)

    p = sub.add_parser("apply-plan", help="apply LLM universal source ingest plan")
    add_common(p)
    p.add_argument("--input", required=True)
    p.add_argument("--today", help="Date heading for queue notes, default today")
    p.set_defaults(func=cmd_apply_plan)

    p = sub.add_parser("summary-tasks", help="emit knowledge notes that need LLM summaries")
    add_common(p)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--all", action="store_true")
    p.add_argument("--path", action="append")
    p.set_defaults(func=cmd_summary_tasks)

    p = sub.add_parser("apply-summaries", help="apply LLM one-paragraph summaries")
    add_common(p)
    p.add_argument("--input", required=True)
    p.set_defaults(func=cmd_apply_summaries)

    p = sub.add_parser("finalize-queue", help="delete queue sources whose target summaries are current")
    add_common(p)
    p.set_defaults(func=cmd_finalize_queue)

    p = sub.add_parser("meeting-prep-task", help="emit context task for future meeting preparation")
    add_common(p)
    p.add_argument("--calendar-title", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--time")
    p.set_defaults(func=cmd_meeting_prep_task)

    p = sub.add_parser("apply-meeting-prep", help="create a future meeting note from LLM prep summary")
    add_common(p)
    p.add_argument("--input", required=True)
    p.set_defaults(func=cmd_apply_meeting_prep)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
