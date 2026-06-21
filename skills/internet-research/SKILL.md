---
name: internet-research
description: Manually research public internet sources for an Obsidian note or topic and add sourced findings to the note. Use when the user asks for OSINT, web enrichment, official names, public roles, negative mentions, or external facts. This is not part of normal ingest.
---

# Internet Research

This skill is manual. Do not run it during normal ingest unless the user explicitly asks.

Use `AGENTS.md` for folder and section configuration. The deterministic engine does not perform web research.

Research rules:

- Build web queries from public identifiers only.
- Prefer official sources, registries, reputable news, and primary documents.
- Search negative/risk mentions by default only for people and organizations.
- Keep sourced web findings separate from the user's own notes.
- Do not silently promote web findings into canonical note text.

Recommended write section:

```md
## Internet Data

Checked: YYYY-MM-DD

### Summary

### Facts
- 

### Sources
- 

### Uncertain
- 

### Suggested Updates
- 
```
