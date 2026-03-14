# Product Context

## UX Goals
- Upload a bundle and get actionable findings in under 2 minutes
- Real-time progress visualization during analysis (WebSocket streaming)
- Interactive forensic interview — ask follow-up questions about findings
- Timeline view — see incident history reconstructed from metadata
- Evidence browser — verify AI findings against source data

## Design Principles
- **Speed**: Triage first (fast regex), AI second (expensive but deep)
- **Transparency**: Every finding has evidence citations
- **Honesty**: Report uncertainty and data gaps explicitly
- **Security**: Never leak sensitive bundle data to LLM without scrubbing
- **Progressive disclosure**: Summary → Findings → Evidence → Interview

## Migration Context
Originally designed as a Textual TUI (terminal UI). Migrated to Next.js web app for richer animations, drag-drop upload, and broader accessibility. FastAPI backend serves both web and CLI interfaces.
