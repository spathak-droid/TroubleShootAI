# System Patterns

## Architecture
Two-layer design: Deterministic triage (80% of findings) -> AI analysis (20%)
- Triage: 12 regex/threshold scanners run in parallel
- AI: 3 concurrent analysts (pod, node, config) dispatched by orchestrator based on triage output
- Novel: 6 engines (archaeology, prediction, silence, diff, simulation, uncertainty)

## Key Patterns
- **Streaming extraction**: Bundles can be 500MB+ — never load fully into RAM
- **BundleIndex**: All file reads go through `index.read()`, never direct `open()`
- **Dynamic work tree**: Orchestrator only runs analysts relevant to triage findings
- **Evidence-grounded**: Every AI finding must cite source files
- **Dual-layer scrubbing**: Pre-ingestion + pre-LLM via `BundleScrubber`
- **Structured AI output**: All analysts return `AnalystOutput` (Pydantic), never free text

## Data Flow
```
Bundle.tar.gz → Extractor (streaming) → Indexer → Triage Engine (12 scanners)
→ Orchestrator (builds work tree) → AI Analysts (parallel) → Synthesis → Findings
```

## Security Flow
```
Raw data → Pre-ingestion scrub → Storage
Stored data → Pre-LLM scrub → K8s structural → Entropy check → Prompt guard → Claude API
All redactions → Audit log
```

## API Architecture
FastAPI backend with routes: bundles, analysis, findings, interview, diff, export, ws
WebSocket for real-time progress streaming to frontend

## Frontend Architecture
Next.js 16 App Router + Zustand state + React Query data fetching
Pages: Upload → Analysis Dashboard → Findings/Interview/Timeline/Validation
