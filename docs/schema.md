# Schema

The schema is configured in `AGENTS.md`, not in Python.

## Folders

Folder roles are stable. Paths are configurable. The required roles are:

- `inbox`;
- `queue`;
- `meetings`;
- `knowledge`;
- `fallback`;
- `service`.

`Path` values are vault-relative, with two parent-aware exceptions:

- `queue` is resolved inside `inbox`, so `queue = Queue` becomes `Inbox/Queue`.
- `fallback` is resolved inside `knowledge`, so `fallback = Other` becomes `Knowledge/Other`.

Full old-style paths such as `Inbox/Queue` and `Knowledge/Other` are still accepted. If you rename a root folder, old default prefixes `Inbox`, `Knowledge`, and `Service` are treated as aliases for the current configured roots.

## Knowledge Types

Knowledge types are user-configurable rows in the `Knowledge Types` table. Each type has:

- `Type`;
- `Folder`;
- `Template`;
- `Description`.

The fallback folder is not a knowledge type. It is used when a note is meaningful but no configured type fits.

`Folder` values in `Knowledge Types` are resolved inside the configured `knowledge` folder. For example, if `knowledge = Knowledge`, then `Folder = People` becomes `Knowledge/People`. This keeps folder renaming in one place. Old-style `Knowledge/People` is also accepted and follows a renamed `knowledge` root.

`Template` values in `Knowledge Types` are resolved inside the directory that contains the configured `knowledge_default` template unless they already start with the configured service path. For example, if `knowledge_default = Templates/knowledge.md`, then `Template = person.md` becomes `Service/Templates/person.md`; if `knowledge_default = Шаблони/knowledge.md`, then `Template = person.md` becomes `Service/Шаблони/person.md`. Old-style `Service/Templates/person.md` is also accepted and follows the configured template directory.

## Sections

The engine manages only configured note section roles:

- `summary`;
- `user_notes`.

It uses placeholders first. If a placeholder has already been replaced, it finds the section by configured heading.

The engine does not manage `Related` or other relationship sections.

## Meeting Sections

The optional `Meeting Sections` table configures static headings used when the engine creates the default meeting template. It does not make those sections agent-managed.

Supported roles:

- `before`;
- `notes`;
- `after`;
- `related`.

If the table is missing, the engine uses English defaults, except `notes` follows the configured `user_notes` heading from `Note Sections`.

## Language Policy

The optional `Language Policy` table configures generated prose language, summary language, and title naming behavior. If the table is missing, the engine uses an English-by-default fallback policy.

Each row has:

- `Setting`;
- `Value`;
- `Rules`.

The engine emits `language_policy` in source ingest tasks, summary tasks, and meeting preparation tasks. LLM plans should follow it when choosing new note titles, writing generated summaries, and preserving proper names.

## Source Task Schema

Both `queue-tasks` and `meeting-tasks` emit `kind: source` tasks.

Important task fields:

- `source_kind`: `queue` or `meeting`;
- `source_policy`: `delete_after_success` or `keep_and_mark_processed`;
- `source`: path to the source note;
- `template_type`: configured type from frontmatter, when present;
- `topic_candidates`: filename topic plus wikilinks, each with candidate targets;
- `candidate_targets`: source-level retrieval candidates;
- `source_text`: full source text unless it exceeds the configured limit;
- `has_summary_placeholder`: meeting-only flag.
- `language_policy`: task-level language and naming rules.

The LLM returns actions:

```json
{
  "actions": [
    {
      "kind": "source",
      "source": "Inbox/Queue/example.md",
      "source_policy": "delete_after_success",
      "coverage": "complete",
      "reason": "",
      "updates": [
        {
          "topic": "Example topic",
          "decision": "create_new",
          "target_title": "Example topic",
          "type": "topic",
          "notes_markdown": "- Useful source excerpt."
        }
      ]
    }
  ]
}
```

For meetings, use `source_policy: keep_and_mark_processed`. If `has_summary_placeholder` is true, include `source_summary` as one paragraph.

`coverage` must be `complete` only when all useful source text was transferred or explicitly ignored as non-durable knowledge.

## Templates

Template `Path` values are resolved inside the configured `service` folder unless they already start with that service path. For example, `Templates/knowledge.md` becomes `Service/Templates/knowledge.md`.

Knowledge templates should include:

```md
{agent_summary}
{user_notes}
```

Meeting templates should include:

```md
{agent_summary}
```

Users may rename headings or change template layout as long as `AGENTS.md` points the engine to the right section names.
