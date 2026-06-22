# Schema

The schema is configured in `Config.md`, not in Python.

## Folders

In the default `Config.md`, folder labels live under `Language and Labels` because changing the vault language usually means changing these paths.

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

Prefer child folder names for `queue` and `fallback`. If you change the parent folder path, these child paths follow it automatically.

## Knowledge Types

Knowledge types are user-configurable rows in the `Knowledge Types` table. Each type has:

- `Type`;
- `Folder`;
- `Template`;
- `Description`.

The fallback folder is not a knowledge type. It is used when a note is meaningful but no configured type fits.

`Folder` values in `Knowledge Types` are resolved inside the configured `knowledge` folder. For example, if `knowledge = Knowledge`, then `Folder = People` becomes `Knowledge/People`. This keeps folder renaming in one place.

`Template` values in `Knowledge Types` are resolved inside the directory that contains the configured `knowledge_default` template unless they already start with the configured service path. For example, if `knowledge_default = Templates/knowledge.md`, then `Template = person.md` becomes `Service/Templates/person.md`; if `knowledge_default = TemplatesUa/knowledge.md`, then `Template = person.md` becomes `Service/TemplatesUa/person.md`.

## Sections

In the default `Config.md`, note and meeting section labels live under `Language and Labels`.

The engine manages only configured note section roles:

- `summary`;
- `user_notes`.

It uses placeholders first. If a placeholder has already been replaced, it finds the section by configured heading.

Sections without placeholders are template/manual sections. The default `related` section is created in generated templates, but the engine does not populate it automatically.

## Meeting Sections

The optional `Meeting Sections` table configures static headings used when the engine creates the default meeting template. It does not make those sections agent-managed.

Supported roles:

- `before`;
- `after`.

The meeting notes section follows the configured `user_notes` heading from `Note Sections`. The related section follows the configured `related` heading from `Note Sections`. If the `Meeting Sections` table is missing, the engine uses English defaults for `before` and `after`.

## Language Policy

The optional `Language Policy` table configures generated prose language and summary language. If the table is missing, the engine uses an English-by-default fallback policy.

Each row has:

- `Setting`;
- `Value`;
- `Rules`.

The engine emits `language_policy` in source ingest tasks, summary tasks, and meeting preparation tasks. LLM plans should follow it when writing generated prose, summaries, and preserving proper names.

Title naming belongs to `Operating Rules`, not `Language Policy`. Source ingest and meeting preparation tasks also emit `operating_rules`.

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
- `has_summary_placeholder`: meeting-only flag;
- `language_policy`: task-level language rules;
- `operating_rules`: task-level behavior rules from `Config.md`.

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
          "notes_markdown": "- Useful source excerpt with [[Existing source link]] preserved.",
          "preserve_links": ["[[Existing source link]]"]
        }
      ]
    }
  ]
}
```

For meetings, use `source_policy: keep_and_mark_processed`. If `has_summary_placeholder` is true, include `source_summary` as one paragraph.

`notes_markdown` should keep source wikilinks on the corresponding names. If the LLM paraphrases text and a source wikilink must remain connected to the update, include it in `preserve_links`. The engine may restore missing source wikilinks from exact names, and may append source lines that contain required wikilinks so the graph relationship is not silently lost.

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

Users may rename headings or change template layout as long as `Config.md` points the engine to the right section names.
