# Method

The vault is human-first. The agent exists to reduce repetitive filing and summarization work without taking ownership of the user's notes.

## Source Rules

- Notes directly in the inbox folder are not processed.
- Queue notes are working inputs and may be deleted only after successful ingest.
- Meeting notes are permanent evidence and are never deleted or renamed.
- Knowledge notes are the only normal notes the agent creates or updates.

## Universal Source Ingest

Queue notes and meeting notes use the same semantic flow.

For each source note:

1. Read the whole source note.
2. Extract topic candidates from the filename and all wikilinks.
3. Search candidate knowledge notes for each topic.
4. Ask the LLM which topics have useful transferable knowledge and which text belongs to each topic, following language policy for prose and operating rules for titles.
5. Resolve each target as an existing note, new note, fallback note, or skip.
6. Insert each selected excerpt under the configured `user_notes` section.
7. Ask the LLM to summarize each full updated target note into one paragraph.
8. Apply summaries, log, and rebuild the index.
9. Finalize the source according to its policy.

Source-derived excerpts may be shortened or paraphrased, but useful Markdown structure should be preserved.

If the type is unclear but the topic is meaningful, use the configured fallback folder. If the source cannot be processed, keep it unfinalized.

## Source Policies

Queue notes use `delete_after_success`.

- A queue note may create or update zero, one, or many target notes.
- A queue note is deleted only when all useful source text has been transferred or explicitly ignored as non-durable knowledge.
- Every target note must have a current summary before deletion.
- If full coverage is not possible, the queue note stays in place and receives a compact `Agent note`.

Meeting notes use `keep_and_mark_processed`.

- Meeting notes are never deleted or renamed.
- Only meetings where `agent_processed` is missing or false are processed.
- If the meeting still contains the configured summary placeholder, the LLM writes one useful paragraph into it.
- After successful processing, the engine sets `agent_processed: true`.

## Meeting Preparation

Future meeting preparation is a separate workflow. It creates a meeting note from the configured meeting template, searches recent relevant meetings and knowledge notes by calendar title, and writes one paragraph into `{agent_summary}`. It does not set `agent_processed: true`.

Meeting preparation also follows the configured language policy, so a title-only calendar event still gets a summary in the vault's preferred language while preserving official names and acronyms.
