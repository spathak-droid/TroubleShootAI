# TroubleShootAI

AI-powered Kubernetes support bundle forensics. Upload a support bundle, get instant root cause analysis with correlated timelines and actionable fix recommendations — all grounded in evidence from your actual cluster data.

**Live:** [troubleshootai.vercel.app](https://troubleshootai.vercel.app) (frontend) • Railway backend

## What It Does

TroubleShootAI takes a Kubernetes support bundle (`.tar.gz` from [Replicated Troubleshoot](https://troubleshoot.sh/), kubectl, or custom collectors) and runs a two-stage analysis:

1. **Deterministic Triage** — 24 parallel scanners detect 20+ issue categories using pattern matching. No tokens spent on what regex can catch.
2. **AI Root Cause Analysis** — Claude receives the triage output (never raw files) and performs cross-resource correlation, temporal archaeology, and hypothesis generation.

The result: severity-ranked findings with evidence citations, a reconstructed failure timeline, change correlation, anomaly detection, and an interactive Q&A interface.

## Key Features

| Feature | Description |
|---------|-------------|
| **24 Triage Scanners** | Pod failures, crash loops, OOMKills, image pull errors, node conditions, deployment issues, config drift, RBAC errors, resource quotas, network policies, DNS, TLS/certificates, scheduling failures, probe misconfigs, storage issues, ingress errors, log intelligence, anomaly detection, dependency analysis, change correlation, coverage gaps, silence signals |
| **Multi-Analyst AI Pipeline** | Specialized analysts (pod, node, config, log) run in parallel, coordinated by an orchestrator that builds a dynamic work tree based on triage findings |
| **Temporal Archaeology** | Reconstructs failure timelines by mining timestamps from events, conditions, pod transitions, and deployment changes |
| **Change Correlation** | Detects config updates, image version bumps, and resource limit changes that preceded failures |
| **Anomaly Detection** | Compares failing pods against healthy ones in the same deployment to spot divergences |
| **Interactive Investigation** | Ask follow-up questions in natural language with full bundle context |
| **Uncertainty Reporting** | Reports what it couldn't determine — missing data, ambiguous signals, areas needing manual investigation |
| **Evidence Citations** | Every finding cites specific files, log lines, and resource specs. No hallucinated diagnoses |
| **7-Layer Security** | Pre-ingestion scrubbing, pre-LLM scrubbing, structural K8s scrubbers, entropy-based secret detection, prompt injection defense, audit logging, configurable security policies |

## Architecture

```
Bundle Upload (.tar.gz, up to 500MB+)
    │  ← Streaming extraction (never fully loaded into memory)
    ▼
┌─────────────────────────────────────────────┐
│  Triage Engine (24 scanners in parallel)    │
│  Pod · Node · Deployment · Event · Config   │
│  CrashLoop · RBAC · DNS · TLS · Storage     │
│  Network · Scheduling · Probe · Ingress     │
│  Drift · Quota · Resource · Silence         │
│  Log Intelligence · Anomaly · Dependency    │
│  Change Correlator · Coverage · Troubleshoot│
└─────────────┬───────────────────────────────┘
              │  ← TriageResult (structured findings)
              ▼
┌─────────────────────────────────────────────┐
│  Security Layer (7-layer scrubbing)         │
│  Pattern redaction · Entropy detection      │
│  K8s structural scrubbers · Prompt guards   │
│  Audit logging · Policy engine              │
└─────────────┬───────────────────────────────┘
              │  ← Scrubbed data only
              ▼
┌─────────────────────────────────────────────┐
│  AI Orchestrator                            │
│  PodAnalyst · NodeAnalyst · ConfigAnalyst   │
│  LogAnalyst · Temporal Archaeology          │
│  Prediction Engine · Synthesis              │
└─────────────┬───────────────────────────────┘
              │  ← AnalysisResult (structured JSON)
              ▼
┌─────────────────────────────────────────────┐
│  Frontend Dashboard                         │
│  Findings · Validation · Timeline · Q&A     │
│  Real-time WebSocket progress updates       │
└─────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 16, React 19, TypeScript, Tailwind CSS 4, Framer Motion, TanStack React Query, Zustand |
| **Backend** | FastAPI, Python 3.11+, Pydantic v2, async/await throughout |
| **AI** | Multi-provider (OpenRouter → OpenAI → Anthropic fallback), structured JSON output, exponential retry |
| **Database** | PostgreSQL (async SQLAlchemy) — optional, works without DB |
| **Auth** | Firebase Authentication |
| **Real-time** | WebSocket for analysis progress streaming |
| **Deployment** | Railway (backend) + Railway/Vercel (frontend) |

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- At least one AI provider API key (`OPEN_ROUTER_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`)

### Backend

```bash
# Clone and install
git clone https://github.com/spathak-droid/TroubleShootAI.git
cd TroubleShootAI

# Create virtual environment
python3 -m venv venv && source venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run the server
bundle-analyzer serve
# → FastAPI running on http://localhost:8001
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# → Next.js running on http://localhost:3000
```

### CLI Usage

```bash
# Analyze a bundle directly (outputs HTML report)
bundle-analyzer analyze ./support-bundle.tar.gz

# Start the web server
bundle-analyzer serve
```

## Testing

```bash
# Run all 280 tests
pip install -e ".[dev]"
pytest

# Run specific test modules
pytest tests/test_triage.py          # Triage scanners
pytest tests/test_security.py        # Data scrubbing
pytest tests/test_ai_pipeline.py     # AI orchestration
pytest tests/test_integration.py     # End-to-end pipeline

# Frontend linting
cd frontend && npm run lint
```

## Security Model

All bundle data passes through a 7-layer security pipeline before reaching any LLM:

1. **Pre-ingestion scrubbing** — Pattern-based redaction at upload time
2. **Pre-LLM scrubbing** — Additional sanitization before API calls
3. **Structural K8s scrubbers** — Understands K8s resource structure (preserves diagnostic names, redacts values)
4. **Entropy detection** — Catches high-entropy strings (secrets that don't match known patterns)
5. **Prompt injection defense** — Wraps untrusted log content in boundary markers
6. **Audit logging** — Records all redactions for compliance
7. **Security policy engine** — Configurable scrub behavior (standard/strict/allowlist)

**What's preserved** (diagnostic value): env var names, K8s resource names, namespaces, labels
**What's redacted**: env var values, API keys, passwords, internal IPs, hostnames, cluster names, high-entropy strings

## Project Structure

```
TroubleShootAI/
├── bundle_analyzer/
│   ├── ai/                  # AI pipeline
│   │   ├── analysts/        # Specialized analysts (pod, node, config, log)
│   │   ├── orchestration/   # Multi-analyst coordinator
│   │   ├── prompts/         # System & user prompt templates
│   │   └── client.py        # Multi-provider LLM client
│   ├── api/                 # FastAPI web server & routes
│   ├── bundle/              # Streaming extraction & indexing
│   ├── cli/                 # Typer CLI app
│   ├── db/                  # PostgreSQL models & repository
│   ├── graph/               # Dependency graph & chain walking
│   ├── models/              # Pydantic v2 data contracts
│   ├── rca/                 # Root cause analysis engines
│   ├── security/            # 7-layer data protection
│   └── triage/              # 24 parallel scanners
├── frontend/                # Next.js 16 React app
│   └── src/app/
│       ├── analysis/[id]/   # Analysis dashboard (5 views)
│       ├── login/           # Firebase auth
│       └── about/           # Product overview
├── tests/                   # 280 pytest tests
│   └── fixtures/            # Sample bundle data
└── docs/                    # Documentation
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/bundles/upload` | Upload bundle (streaming) |
| `GET` | `/api/v1/bundles` | List bundles |
| `POST` | `/api/v1/bundles/{id}/analyze` | Start analysis |
| `GET` | `/api/v1/bundles/{id}/analysis` | Get analysis status |
| `GET` | `/api/v1/bundles/{id}/triage` | Get triage results |
| `GET` | `/api/v1/bundles/{id}/findings` | Get AI findings |
| `POST` | `/api/v1/bundles/{id}/interview` | Interactive Q&A |
| `WS` | `/api/v1/bundles/{id}/ws` | Real-time progress |
| `GET` | `/api/v1/health` | Health check |

## License

MIT
