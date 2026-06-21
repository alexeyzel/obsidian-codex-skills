---
name: meeting-prep
description: Create a future Obsidian meeting note from a calendar title and date, using recent relevant vault context to fill the configured summary placeholder. Use when the user or n8n asks to prepare a meeting note, create a note for a calendar event, or recap prior context for an upcoming meeting.
---

# Meeting Prep

Inputs:

- calendar title;
- date;
- optional time.

Resolve `ENGINE` to the installed engine at `${CODEX_HOME:-$HOME/.codex}/obsidian-knowledge-skills/scripts/vault_engine.py`. If working from a repository checkout, local `scripts/vault_engine.py` is also valid.

Procedure:

1. Generate a context task:

   ```bash
   python "$ENGINE" meeting-prep-task --vault "/path/to/vault" --calendar-title "Calendar title" --date 2026-06-22 > meeting-prep-task.json
   ```

2. If `exists` is true, skip unless the user explicitly asks otherwise.
3. As the LLM, write one paragraph of preparation context from the supplied recent notes. Follow `language_policy` for the summary language and preserve proper names, official names, acronyms, and established mixed-language names.
4. Save a plan:

   ```json
   {
     "target_path": "Meetings/2026-06-22 - Calendar title.md",
     "calendar_title": "Calendar title",
     "date": "2026-06-22",
     "summary": "One paragraph..."
   }
   ```

5. Apply:

   ```bash
   python "$ENGINE" apply-meeting-prep --vault "/path/to/vault" --input meeting-prep-plan.json
   ```

Meeting prep does not set `agent_processed: true`.
