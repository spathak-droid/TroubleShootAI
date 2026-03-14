# Tech Context

## Backend
- Python 3.11+ (uses tomllib, match statements)
- Pydantic v2 (model_validator, not validator)
- FastAPI + Uvicorn (API server)
- Anthropic SDK (Claude API client)
- Loguru (logging, not print)
- aiofiles (async file I/O)
- Typer (CLI framework)
- pytest + pytest-asyncio (testing)

## Frontend
- Next.js 16.1.6 (App Router)
- React 19.2.3
- Tailwind CSS 4 + PostCSS
- Framer Motion 12.36 (animations)
- Zustand 5.0.11 (state management)
- TanStack React Query (data fetching)
- Lucide React (icons)
- TypeScript

## Constraints
- ANTHROPIC_API_KEY required in .env
- Bundles can be 500MB+ — streaming mandatory
- `***HIDDEN***` markers in bundles are pre-existing redaction, not errors
- RBAC errors in bundles are findings, not parser errors
- All data to LLM must pass through BundleScrubber
