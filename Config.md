# Obsidian Vault Agent Config

This file configures the Obsidian vault maintenance agent. It is Markdown, not YAML, so a human can read and edit it comfortably.

## Language and Labels

Configure the vault language, generated prose language, folder names, and note section labels here.

### Language Policy

Human editing note: you may change `Value` and `Rules` to match your vault. Keep `Setting` values unchanged unless you also update the agent/engine.

Agent rule: use this table when choosing generated prose and summary language. Preserve proper names and established project names even when the surrounding prose uses another language.

| Setting | Value | Rules |
|---|---|---|
| default_content_language | English | Use for generated prose unless the source clearly requires another language. |
| default_summary_language | English | Write summaries and meeting preparation context in this language by default. |
| preserve_source_language | yes | Preserve user-authored excerpts, quotes, official titles, acronyms, and mixed-language terms when moving notes into `user_notes`. |
| do_not_translate_proper_names | yes | Do not translate person names, organization names, project names, product names, acronyms, emails, handles, or official terms. |
| mixed_language_allowed | yes | Mixed-language titles and summaries are allowed for official names, projects, acronyms, roles, and source-specific terminology. |

### Folders

Human editing note: keep the `Role` values unchanged. You may change only `Path` values if you want different folder names or another language.

Agent rule: folder roles define behavior. Use paths from this table; do not infer folder paths from hardcoded names.

Path rule: `queue` is written relative to `inbox`; `fallback` is written relative to `knowledge`. Other folder paths are vault-relative.

| Role | Path | Rules |
|---|---|---|
| inbox | Inbox | New notes may land here. Do not process notes directly in this folder. |
| queue | Queue | Child folder inside `inbox`. Process notes waiting for ingest. Delete a queue note only after successful ingest and summary application. |
| meetings | Meetings | Meeting notes are never deleted or renamed. |
| knowledge | Knowledge | Create and update knowledge notes only under this folder. |
| fallback | Other | Child folder inside `knowledge`. Required fallback folder for processable notes whose type is unclear. |
| service | Service | Agent state, logs, templates, cache, and other internal files. |

### Note Sections

Human editing note: you may change `Heading` values if your templates use another language. Keep `Role` values unchanged.

Agent rule: use placeholders first. If a placeholder is no longer present, find the section by `Heading`. Sections without placeholders are manual template sections; do not write to them unless the user explicitly asks.

| Role | Heading | Placeholder | Applies to |
|---|---|---|---|
| summary | Summary | {agent_summary} | knowledge, meeting |
| user_notes | My notes | {user_notes} | knowledge |
| related | Related |  | knowledge, meeting |

### Meeting Sections

Human editing note: you may change `Heading` values if your meeting template uses another language. Keep `Role` values unchanged.

Agent rule: these headings are used only when creating the default meeting template. The meeting notes section comes from `Note Sections` role `user_notes`; the related section comes from `Note Sections` role `related`. The agent still manages only the configured summary placeholder in meeting notes.

| Role | Heading |
|---|---|
| before | Before |
| after | After |

## Knowledge Types

Human editing note: you may change this table. Add, remove, or rename knowledge types as needed. The fallback folder is configured in `Folders`, not here.

Agent rule: use this table as the allowed list of explicit knowledge types. If no type fits but the note is still processable, use the fallback folder.

Path rule: `Folder` is written relative to the configured `knowledge` folder. `Template` is written relative to the directory that contains the `knowledge_default` template.

| Type | Folder | Template | Description |
|---|---|---|---|
| person | People | person.md | One note per person. |
| organization | Organizations | organization.md | Companies, institutions, agencies, public bodies, and informal organizations. |
| project | Projects | project.md | Projects, programs, grants, and long-running structured efforts. |
| activity | Activities | activity.md | Concrete initiatives, contracts, tasks, actions, services, or workstreams. |
| topic | Topics | topic.md | General concepts, themes, policy areas, technologies, and reusable ideas. |
| reference | Reference | reference.md | Reference material, guidance, reusable instructions, and informational notes. |

## Templates

Human editing note: you may change template paths and template text. Keep required placeholders where the agent should write.

Agent rule: create missing templates during setup. For knowledge notes, `{agent_summary}` and `{user_notes}` are the only required write targets. For meeting notes, only `{agent_summary}` is agent-managed.

Path rule: `Path` is written relative to the configured `service` folder.

| Role | Path | Rules |
|---|---|---|
| knowledge_default | Templates/knowledge.md | Path relative to `service`. Used for fallback notes and as a backup when a type template is missing. |
| meeting | Templates/meeting.md | Path relative to `service`. Used by the meeting preparation skill. |

## Obsidian Graph

Human editing note: you may change `Value` values. Keep `Setting` values unchanged unless you also update the agent/engine.

Agent rule: during vault setup, update `.obsidian/graph.json` so Obsidian graph view shows only the configured folder roles listed here. Preserve other existing graph settings.

| Setting | Value | Rules |
|---|---|---|
| manage_graph_search | yes | Set to `no` if you want to manage Obsidian graph search manually. |
| visible_folder_roles | knowledge, meetings | Comma-separated folder roles to include in graph view. |

## Processing Limits

Human editing note: adjust these values for your model context window and vault size.

Agent rule: never silently exceed these limits. If a source cannot fit, leave it unprocessed and add an `Agent note`.

| Setting | Value |
|---|---|
| max_llm_input_chars | 60000 |
| search_candidates | 8 |
| meeting_prep_context_notes | 5 |

## Operating Rules

- Ingest uses one universal source flow for queue notes and meeting notes.
- For every source note, inspect the full text, the filename topic, and all wikilinks. Decide which topics have useful transferable knowledge.
- A source note may create or update zero, one, or many knowledge notes.
- Resolve target notes before writing: existing note, new note, fallback note, or skip with a reason.
- When creating a new note, use the natural/common name from the source or explicit target title. Do not translate proper names. Prefer short readable titles over formal registry names unless the formal name is the common name.
- If a queue source has an explicit `type` in frontmatter and the type exists in `Knowledge Types`, use that type for the source filename topic when that topic becomes a new note.
- If a topic type is unclear but the topic is meaningful, write it to the `fallback` folder.
- Queue notes are disposable only when all useful source content has been transferred or explicitly ignored as non-durable knowledge, all target notes have current summaries, and the action has been logged and indexed.
- If a queue source cannot be fully processed, append `## Agent note` with a compact reason and keep it in `queue`.
- Meeting notes are permanent evidence. Never delete or rename them.
- Process only meeting notes where `agent_processed` is missing or false. After successful processing, set `agent_processed: true`.
- If a user wants a meeting note processed again, they should set `agent_processed: false`.
- If a meeting note still contains the configured summary placeholder, write one useful paragraph into it before setting `agent_processed: true`.
- Source-derived excerpts may be shortened or paraphrased, but they should preserve useful markdown structure.
- Source-derived excerpts should preserve existing source wikilinks. Do not remove brackets from links that were already present in the source; if text is paraphrased, keep source wikilinks on the corresponding names or include them in `preserve_links`.
- Knowledge summaries must be one high-quality paragraph that captures the important essence of the full updated note.
- Meeting preparation creates future meeting notes, writes only the summary placeholder, and does not set `agent_processed: true`.
