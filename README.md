# TroubleShootAI

AI-powered Kubernetes support bundle forensics. Upload a support bundle, get instant root cause analysis with correlated timelines and actionable fix recommendations — all grounded in evidence from your actual cluster data.

**Live App:** [troubleshootai-production.up.railway.app](https://troubleshootai-production.up.railway.app)

---

## Try It Now (5 minutes)

### What you need
- Docker Desktop (running)
- `kind` and `kubectl` installed

### Step 1: Create a broken cluster

```bash
# Clone the repo
git clone https://github.com/spathak-droid/TroubleShootAI.git
cd TroubleShootAI

# Create a Kind cluster
kind create cluster --name test-cluster --wait 60s

# Deploy 8 broken workloads (CrashLoop, OOM, ImagePull, Pending, NetworkPolicy, DNS, missing config, no endpoints)
kubectl apply -f scripts/live_test/broken-workloads.yaml

# Wait 60 seconds for failures to fully manifest
sleep 60

# Check — you should see CrashLoopBackOff, OOMKilled, ImagePullBackOff, Pending, Error
kubectl get pods
```

### Step 2: Install Troubleshoot and collect a bundle

```bash
# Install the Troubleshoot kubectl plugin (one-time)
curl -L https://github.com/replicatedhq/troubleshoot/releases/latest/download/support-bundle_darwin_all.tar.gz | tar xz
mkdir -p ~/bin && mv support-bundle ~/bin/kubectl-support_bundle
export PATH="$HOME/bin:$PATH"

# Collect a support bundle (produces a single .tar.gz)
kubectl-support_bundle scripts/live_test/support-bundle.yaml \
  --output bundle.tar.gz \
  --interactive=false
```

> **Note:** Troubleshoot.sh will report "1 passed, 0 warnings, 0 failures" — it only runs the basic analyzers defined in the spec. It misses all 8 failure scenarios. That's where TroubleShootAI comes in.

### Step 3: Upload to TroubleShootAI

1. Go to **[troubleshootai-production.up.railway.app](https://troubleshootai-production.up.railway.app)**
2. Upload `bundle.tar.gz`
3. Watch the analysis run in real-time

The analyzer will detect:
- **CrashLoopBackOff** — pods crashing because database is unreachable
- **OOMKilled** — container memory limit exceeded (exit code 137)
- **ImagePullBackOff** — image tag doesn't exist
- **Pending / FailedScheduling** — pod requests more CPU than cluster has
- **CreateContainerConfigError** — missing ConfigMap reference
- **NetworkPolicy deny-all** — pod is network-isolated
- **Service with no endpoints** — selector matches nothing
- **DNS NXDOMAIN** — services that don't exist

### Step 4: Clean up

```bash
kind delete cluster --name test-cluster
```

---

## What It Does

TroubleShootAI takes a Kubernetes support bundle (`.tar.gz` from [Replicated Troubleshoot](https://troubleshoot.sh/)) and runs a two-stage analysis:

1. **Deterministic Triage** — 24 parallel scanners detect 20+ issue categories using pattern matching. No tokens spent on what regex can catch.
2. **AI Root Cause Analysis** — Claude receives the triage output (never raw files) and performs cross-resource correlation, temporal archaeology, and hypothesis generation.

The result: severity-ranked findings with evidence citations, a reconstructed failure timeline, change correlation, anomaly detection, and an interactive Q&A interface.

### Why not just use Troubleshoot.sh?

Troubleshoot.sh is a **data collector** — it gathers cluster state into a tar.gz. Its built-in analyzers are basic rule-based checks that you write yourself, one by one.

TroubleShootAI is the **diagnostics engine** — it reads that same tar.gz and automatically finds every failure, correlates root causes across resources, reconstructs timelines, and generates actionable fixes.

| | Troubleshoot.sh | TroubleShootAI |
|---|---|---|
| Data collection | Yes | Uses Troubleshoot bundles |
| Auto-detection | Only what you manually configure | 24 scanners, 20+ issue types, zero config |
| Root cause analysis | No | AI-powered cross-resource correlation |
| Timeline reconstruction | No | Temporal archaeology from metadata |
| Fix recommendations | No | Specific kubectl commands and YAML patches |
| Interactive Q&A | No | Ask follow-up questions with full context |

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
| **Deployment** | Railway (backend + frontend) |

## Local Development

### Prerequisites
- Python 3.11+
- Node.js 18+
- At least one AI provider API key (`OPEN_ROUTER_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`)

### Backend

```bash
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
# Run all 295 tests
pip install -e ".[dev]"
pytest

# Run specific test modules
pytest tests/test_triage.py          # Triage scanners
pytest tests/test_security.py        # Data scrubbing
pytest tests/test_ai_pipeline.py     # AI orchestration
pytest tests/test_integration.py     # End-to-end pipeline
pytest tests/test_e2e_pipeline.py    # Full multi-failure scenarios

# Frontend linting
cd frontend && npm run lint
```

## Live Test (Generate a Real Bundle)

```bash
# Full run: create Kind cluster + deploy 8 failure scenarios + collect + analyze
./scripts/live_test/run.sh

# Reuse existing cluster
./scripts/live_test/run.sh --skip-cluster

# Clean up
./scripts/live_test/run.sh --cleanup
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
├── scripts/live_test/       # Kind cluster + broken workloads for testing
├── tests/                   # 295 pytest tests
│   └── fixtures/            # Sample bundle data
└── docs/                    # Documentation
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/bundles/upload` | Upload bundle (streaming) |
| `GET` | `/api/v1/bundles` | List bundles |
| `POST` | `/api/v1/bundles/{id}/analyze` | Start analysis |
| `GET` | `/api/v1/bundles/{id}/analysis` | Get full analysis |
| `GET` | `/api/v1/bundles/{id}/triage` | Get triage results |
| `GET` | `/api/v1/bundles/{id}/findings` | Get AI findings |
| `POST` | `/api/v1/bundles/{id}/evaluate` | Run deterministic validation |
| `POST` | `/api/v1/bundles/{id}/interview` | Start interactive Q&A |
| `POST` | `/api/v1/bundles/{id}/interview/{sid}/ask/stream` | Stream AI answers (SSE) |
| `WS` | `/ws/{id}/progress` | Real-time progress updates |
| `GET` | `/api/v1/health` | Health check |

## License

MIT
