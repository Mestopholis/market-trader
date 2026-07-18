# Market Trader Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a testable local FastAPI/React/Docker foundation that defaults to paper mode and exposes no brokerage or live-order capability.

**Architecture:** A monorepo contains a FastAPI backend and React TypeScript frontend. The backend owns configuration and health state; the frontend consumes a same-origin `/api/health` endpoint and displays an unmistakable paper-mode banner. Docker Compose runs both services locally and the web container proxies API requests, preserving the deployment shape needed for Proxmox.

**Tech Stack:** Python 3.12, FastAPI, Pydantic Settings, pytest, Ruff, mypy, Node.js 24, React 19, TypeScript, Vite, Vitest, Testing Library, nginx, Docker Compose, GitHub Actions.

## Global Constraints

- Default to paper mode after every install, upgrade, unexpected restart or authentication recovery.
- Version one opens no live orders and stores no Schwab credentials.
- Bind local services to loopback-facing host ports.
- Store timestamps in UTC and display market times with explicit timezone labels.
- Keep secrets outside source control and redact them from logs and frontend responses.
- All trade eligibility, scoring, sizing and risk decisions will be deterministic and versioned in later milestones.
- No naked options, short shares, credit spreads, adjusted options or 0DTE trades may be introduced.
- Use test-driven development and commit after each independently testable task.

## Planned file structure

```text
market-trader/
├── .editorconfig
├── .env.example
├── .github/workflows/ci.yml
├── .gitignore
├── compose.yaml
├── README.md
├── apps/
│   ├── api/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   ├── src/market_trader/
│   │   │   ├── __init__.py
│   │   │   ├── api/health.py
│   │   │   ├── config.py
│   │   │   └── main.py
│   │   └── tests/
│   │       ├── test_config.py
│   │       └── test_health.py
│   └── web/
│       ├── Dockerfile
│       ├── eslint.config.js
│       ├── index.html
│       ├── nginx.conf
│       ├── package-lock.json
│       ├── package.json
│       ├── tsconfig.json
│       ├── vite.config.ts
│       └── src/
│           ├── App.test.tsx
│           ├── App.tsx
│           ├── api.ts
│           ├── index.css
│           ├── main.tsx
│           └── test/setup.ts
└── scripts/
    └── verify-foundation.sh
```

---

### Task 1: Backend configuration and health contract

**Files:**

- Create: `apps/api/pyproject.toml`
- Create: `apps/api/src/market_trader/__init__.py`
- Create: `apps/api/src/market_trader/config.py`
- Create: `apps/api/src/market_trader/api/health.py`
- Create: `apps/api/src/market_trader/main.py`
- Create: `apps/api/tests/test_config.py`
- Create: `apps/api/tests/test_health.py`

**Interfaces:**

- Consumes: Environment variables prefixed with `MARKET_TRADER_`.
- Produces: `market_trader.main.app`, `GET /api/health`, and `Settings` with `environment`, `trading_mode`, `app_version`, and `database_url`.

- [ ] **Step 1: Create backend packaging and test configuration**

Create `apps/api/pyproject.toml`:

```toml
[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[project]
name = "market-trader-api"
version = "0.1.0"
requires-python = ">=3.12,<3.14"
dependencies = [
  "fastapi>=0.116,<1",
  "pydantic-settings>=2.10,<3",
  "uvicorn[standard]>=0.35,<1",
]

[project.optional-dependencies]
dev = [
  "httpx>=0.28,<1",
  "mypy>=1.17,<2",
  "pytest>=8.4,<9",
  "pytest-cov>=6.2,<7",
  "ruff>=0.12,<1",
]

[tool.hatch.build.targets.wheel]
packages = ["src/market_trader"]

[tool.pytest.ini_options]
addopts = "-q --strict-markers --cov=market_trader --cov-report=term-missing"
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["market_trader"]
```

- [ ] **Step 2: Write failing configuration tests**

Create `apps/api/tests/test_config.py`:

```python
from market_trader.config import TradingMode, get_settings


def test_defaults_to_paper_mode(monkeypatch) -> None:
    monkeypatch.delenv("MARKET_TRADER_TRADING_MODE", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.trading_mode is TradingMode.PAPER


def test_live_mode_is_rejected_in_foundation(monkeypatch) -> None:
    monkeypatch.setenv("MARKET_TRADER_TRADING_MODE", "live")
    get_settings.cache_clear()

    try:
        get_settings()
    except ValueError as error:
        assert "Live trading is unavailable" in str(error)
    else:
        raise AssertionError("foundation configuration accepted live trading")
```

- [ ] **Step 3: Run the configuration tests and verify failure**

Run:

```bash
cd apps/api
python -m pip install -e '.[dev]'
pytest tests/test_config.py -q
```

Expected: collection fails because `market_trader.config` does not exist.

- [ ] **Step 4: Implement paper-only configuration**

Create `apps/api/src/market_trader/__init__.py`:

```python
"""Market Trader backend."""
```

Create `apps/api/src/market_trader/config.py`:

```python
from enum import StrEnum
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MARKET_TRADER_",
        extra="ignore",
    )

    environment: str = "local"
    trading_mode: TradingMode = TradingMode.PAPER
    app_version: str = "0.1.0"
    database_url: str = "sqlite:///./data/market_trader.db"

    @model_validator(mode="after")
    def reject_live_mode_during_foundation(self) -> "Settings":
        if self.trading_mode is TradingMode.LIVE:
            raise ValueError("Live trading is unavailable in the foundation release")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 5: Run configuration tests and static checks**

Run:

```bash
cd apps/api
pytest tests/test_config.py -q
ruff check src tests
mypy src
```

Expected: two tests pass; Ruff and mypy exit successfully.

- [ ] **Step 6: Write the failing health endpoint test**

Create `apps/api/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from market_trader.main import app


def test_health_reports_paper_mode_without_secrets() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "environment": "local",
        "trading_mode": "paper",
        "version": "0.1.0",
    }
    assert "database_url" not in response.text
```

- [ ] **Step 7: Run the health test and verify failure**

Run:

```bash
cd apps/api
pytest tests/test_health.py -q
```

Expected: collection fails because `market_trader.main` does not exist.

- [ ] **Step 8: Implement the health endpoint and application factory**

Create `apps/api/src/market_trader/api/health.py`:

```python
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from market_trader.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    environment: str
    trading_mode: Literal["paper"]
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        trading_mode="paper",
        version=settings.app_version,
    )
```

Create `apps/api/src/market_trader/main.py`:

```python
from fastapi import FastAPI

from market_trader.api.health import router as health_router
from market_trader.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Market Trader API",
        version=settings.app_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    application.include_router(health_router, prefix="/api")
    return application


app = create_app()
```

- [ ] **Step 9: Verify the complete backend task**

Run:

```bash
cd apps/api
pytest -q
ruff check src tests
mypy src
```

Expected: all tests pass and both static checks exit successfully.

- [ ] **Step 10: Commit the backend foundation**

```bash
git add apps/api
git commit -m "feat(api): add paper-only health foundation"
```

---

### Task 2: Frontend paper-mode status screen

**Files:**

- Create: `apps/web/package.json`
- Create: `apps/web/package-lock.json`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/index.html`
- Create: `apps/web/eslint.config.js`
- Create: `apps/web/src/api.ts`
- Create: `apps/web/src/App.tsx`
- Create: `apps/web/src/App.test.tsx`
- Create: `apps/web/src/index.css`
- Create: `apps/web/src/main.tsx`
- Create: `apps/web/src/test/setup.ts`

**Interfaces:**

- Consumes: `GET /api/health` returning the `HealthResponse` contract from Task 1.
- Produces: Browser application with loading, unavailable, and paper-mode states.

- [ ] **Step 1: Create the frontend package definition**

Create `apps/web/package.json`:

```json
{
  "name": "market-trader-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "eslint .",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^19.1.1",
    "react-dom": "^19.1.1"
  },
  "devDependencies": {
    "@eslint/js": "^9.31.0",
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.3.0",
    "@testing-library/user-event": "^14.6.1",
    "@types/node": "^24.0.14",
    "@types/react": "^19.1.8",
    "@types/react-dom": "^19.1.6",
    "@vitejs/plugin-react": "^4.6.0",
    "eslint": "^9.31.0",
    "eslint-plugin-react-hooks": "^5.2.0",
    "eslint-plugin-react-refresh": "^0.4.20",
    "globals": "^16.3.0",
    "jsdom": "^26.1.0",
    "typescript": "^5.8.3",
    "typescript-eslint": "^8.38.0",
    "vite": "^7.0.6",
    "vitest": "^3.2.4"
  }
}
```

Run `npm install` in `apps/web` and commit the generated `package-lock.json`; subsequent installs must use `npm ci` so actual dependency versions are locked.

- [ ] **Step 2: Create TypeScript, Vite, ESLint and test setup**

Create `apps/web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "Bundler",
    "allowImportingTsExtensions": false,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "vite.config.ts"]
}
```

Create `apps/web/vite.config.ts`:

```typescript
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
```

Create `apps/web/eslint.config.js`:

```javascript
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: { globals: globals.browser },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
)
```

Create `apps/web/src/test/setup.ts`:

```typescript
import '@testing-library/jest-dom/vitest'
```

- [ ] **Step 3: Write failing UI tests**

Create `apps/web/src/App.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import App from './App'

afterEach(() => {
  vi.restoreAllMocks()
})

test('shows an unmistakable paper mode banner', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        status: 'ok',
        environment: 'local',
        trading_mode: 'paper',
        version: '0.1.0',
      }),
      { status: 200 },
    ),
  )

  render(<App />)

  expect(await screen.findByRole('status')).toHaveTextContent('PAPER MODE')
  expect(screen.getByText(/No live orders can be submitted/i)).toBeInTheDocument()
})

test('shows a safe unavailable state when health fails', async () => {
  vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'))

  render(<App />)

  expect(await screen.findByRole('alert')).toHaveTextContent('Trading controls unavailable')
})
```

- [ ] **Step 4: Run UI tests and verify failure**

Run:

```bash
cd apps/web
npm install
npm test
```

Expected: test collection fails because `src/App.tsx` does not exist.

- [ ] **Step 5: Implement the typed API client**

Create `apps/web/src/api.ts`:

```typescript
export type HealthResponse = {
  status: 'ok'
  environment: string
  trading_mode: 'paper'
  version: string
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch('/api/health', {
    headers: { Accept: 'application/json' },
    signal,
  })
  if (!response.ok) {
    throw new Error(`Health request failed with ${response.status}`)
  }
  return (await response.json()) as HealthResponse
}
```

- [ ] **Step 6: Implement the status screen**

Create `apps/web/src/App.tsx`:

```tsx
import { useEffect, useState } from 'react'

import { fetchHealth, type HealthResponse } from './api'
import './index.css'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; health: HealthResponse }
  | { kind: 'error' }

export default function App() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then((health) => setState({ kind: 'ready', health }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: 'error' })
      })
    return () => controller.abort()
  }, [])

  if (state.kind === 'loading') {
    return <main><p>Checking system safety state…</p></main>
  }

  if (state.kind === 'error') {
    return (
      <main>
        <section role="alert" className="unavailable">
          <h1>Trading controls unavailable</h1>
          <p>The backend safety state could not be verified.</p>
        </section>
      </main>
    )
  }

  return (
    <main>
      <section role="status" className="paper-banner">
        <strong>PAPER MODE</strong>
        <span>No live orders can be submitted.</span>
      </section>
      <h1>Market Trader</h1>
      <dl>
        <dt>Environment</dt><dd>{state.health.environment}</dd>
        <dt>Version</dt><dd>{state.health.version}</dd>
      </dl>
    </main>
  )
}
```

Create `apps/web/src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

Create `apps/web/src/index.css`:

```css
:root {
  color: #e7edf5;
  background: #0b1118;
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
}

body { margin: 0; min-width: 320px; min-height: 100vh; }
main { max-width: 960px; margin: 0 auto; padding: 2rem; }
.paper-banner, .unavailable { padding: 1rem; border-radius: 0.5rem; }
.paper-banner { display: flex; gap: 1rem; background: #173f5f; border: 2px solid #58a6ff; }
.unavailable { background: #4a1717; border: 2px solid #ff7b72; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 0.5rem 1rem; }
dt { color: #9fb0c3; }
dd { margin: 0; }
```

Create `apps/web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Market Trader</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Verify frontend tests, lint and build**

Run:

```bash
cd apps/web
npm test
npm run lint
npm run build
```

Expected: two tests pass; lint exits successfully; Vite creates `dist/`.

- [ ] **Step 8: Commit the frontend foundation**

```bash
git add apps/web
git commit -m "feat(web): show verified paper-only status"
```

---

### Task 3: Local Docker Compose runtime

**Files:**

- Create: `.env.example`
- Create: `.editorconfig`
- Create: `compose.yaml`
- Create: `apps/api/Dockerfile`
- Create: `apps/web/Dockerfile`
- Create: `apps/web/nginx.conf`
- Create: `scripts/verify-foundation.sh`
- Modify: `README.md`

**Interfaces:**

- Consumes: Task 1 API on container port 8000 and Task 2 static web build.
- Produces: `http://127.0.0.1:8080` with same-origin `/api/health` proxying and a repeatable smoke test.

- [ ] **Step 1: Add safe local configuration examples**

Create `.env.example`:

```dotenv
MARKET_TRADER_ENVIRONMENT=local
MARKET_TRADER_TRADING_MODE=paper
MARKET_TRADER_APP_VERSION=0.1.0
MARKET_TRADER_DATABASE_URL=sqlite:////data/market_trader.db
```

Create `.editorconfig`:

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
indent_style = space
indent_size = 2

[*.py]
indent_size = 4

[Makefile]
indent_style = tab
```

- [ ] **Step 2: Create the backend container**

Create `apps/api/Dockerfile`:

```dockerfile
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown appuser:appuser /data
USER appuser

EXPOSE 8000
CMD ["uvicorn", "market_trader.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Create the web container and API proxy**

Create `apps/web/nginx.conf`:

```nginx
server {
    listen 8080;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://api:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 10s;
    }

    location / {
        try_files $uri /index.html;
    }
}
```

Create `apps/web/Dockerfile`:

```dockerfile
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.29-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
```

- [ ] **Step 4: Create Docker Compose orchestration**

Create `compose.yaml`:

```yaml
services:
  api:
    build:
      context: ./apps/api
    environment:
      MARKET_TRADER_ENVIRONMENT: ${MARKET_TRADER_ENVIRONMENT:-local}
      MARKET_TRADER_TRADING_MODE: paper
      MARKET_TRADER_APP_VERSION: ${MARKET_TRADER_APP_VERSION:-0.1.0}
      MARKET_TRADER_DATABASE_URL: sqlite:////data/market_trader.db
    volumes:
      - market-trader-data:/data
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped

  web:
    build:
      context: ./apps/web
    depends_on:
      api:
        condition: service_healthy
    ports:
      - "127.0.0.1:8080:8080"
    restart: unless-stopped

volumes:
  market-trader-data:
```

- [ ] **Step 5: Write the smoke verification script**

Create `scripts/verify-foundation.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

base_url="${MARKET_TRADER_URL:-http://127.0.0.1:8080}"
health="$(curl --fail --silent --show-error "${base_url}/api/health")"

test "$(printf '%s' "$health" | python3 -c 'import json,sys; print(json.load(sys.stdin)["trading_mode"])')" = "paper"
curl --fail --silent --show-error "$base_url/" | grep -q '<div id="root"></div>'

printf 'Foundation verification passed at %s\n' "$base_url"
```

Run:

```bash
chmod +x scripts/verify-foundation.sh
```

- [ ] **Step 6: Document local startup**

Append this section to `README.md`:

```markdown
## Local foundation startup

1. Copy `.env.example` to `.env`.
2. Run `docker compose up --build -d`.
3. Open `http://127.0.0.1:8080`.
4. Run `./scripts/verify-foundation.sh`.
5. Stop with `docker compose down`.

The foundation is paper-only and contains no broker credentials or order submission.
```

- [ ] **Step 7: Build and verify the local stack**

Run:

```bash
docker compose config
docker compose up --build -d
./scripts/verify-foundation.sh
docker compose ps
docker compose down
```

Expected: configuration validates; verification prints `Foundation verification passed`; both services report healthy/running before shutdown.

- [ ] **Step 8: Commit the local runtime**

```bash
git add .env.example .editorconfig compose.yaml apps/api/Dockerfile apps/web/Dockerfile apps/web/nginx.conf scripts README.md
git commit -m "build: add paper-only local container runtime"
```

---

### Task 4: Continuous integration and repository guardrails

**Files:**

- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

**Interfaces:**

- Consumes: Backend and frontend test/lint/build commands from Tasks 1–3.
- Produces: Pull-request and main-branch checks for backend, frontend and container builds.

- [ ] **Step 1: Add the CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: apps/api/pyproject.toml
      - run: python -m pip install -e '.[dev]'
        working-directory: apps/api
      - run: pytest -q
        working-directory: apps/api
      - run: ruff check src tests
        working-directory: apps/api
      - run: mypy src
        working-directory: apps/api

  web:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "24"
          cache: npm
          cache-dependency-path: apps/web/package-lock.json
      - run: npm ci
        working-directory: apps/web
      - run: npm test
        working-directory: apps/web
      - run: npm run lint
        working-directory: apps/web
      - run: npm run build
        working-directory: apps/web

  containers:
    runs-on: ubuntu-latest
    needs: [api, web]
    steps:
      - uses: actions/checkout@v4
      - run: docker compose config
      - run: docker compose build
```

- [ ] **Step 2: Add the CI badge**

Add this line below the title in `README.md`:

```markdown
[![CI](https://github.com/Mestopholis/market-trader/actions/workflows/ci.yml/badge.svg)](https://github.com/Mestopholis/market-trader/actions/workflows/ci.yml)
```

- [ ] **Step 3: Validate the workflow locally**

Run:

```bash
docker compose config
cd apps/api && pytest -q && ruff check src tests && mypy src
cd ../web && npm test && npm run lint && npm run build
```

Expected: Docker configuration validates and all tests, static checks and builds pass.

- [ ] **Step 4: Commit CI guardrails**

```bash
git add .github/workflows/ci.yml README.md
git commit -m "ci: verify API web and container foundations"
```

---

### Task 5: Foundation acceptance verification

**Files:**

- Modify: `README.md`

**Interfaces:**

- Consumes: Completed Tasks 1–4.
- Produces: Recorded foundation verification commands and an implementation handoff for the next scanner-domain plan.

- [ ] **Step 1: Run all non-container verification**

Run:

```bash
cd apps/api
pytest -q
ruff check src tests
mypy src
cd ../web
npm test
npm run lint
npm run build
```

Expected: every command exits with status zero.

- [ ] **Step 2: Run container verification from a clean state**

Run:

```bash
cd ../..
docker compose down --volumes
docker compose up --build -d
./scripts/verify-foundation.sh
docker compose ps
docker compose down --volumes
```

Expected: the smoke script passes, API health is `paper`, web is reachable only on `127.0.0.1:8080`, and no persistent test containers remain.

- [ ] **Step 3: Perform secret and live-mode scans**

Run:

```bash
rg -n --hidden -g '!*.md' -g '!.git/**' '(client_secret|access_token|refresh_token|BEGIN [A-Z ]+PRIVATE KEY)'
rg -n --hidden -g '!*.md' -g '!.git/**' 'TRADING_MODE.*live|trading_mode.*live'
```

Expected: the secret scan returns no results. The live-mode scan may match only the explicit backend rejection test and rejection enum/configuration; it must not find an order path or a live default.

- [ ] **Step 4: Record the foundation boundary**

Append to `README.md`:

```markdown
## Foundation boundary

The foundation milestone proves local startup, paper-only configuration, health-state visibility and CI. Market data, scanning, brokerage authentication, account access and order submission require separate reviewed implementation plans.
```

- [ ] **Step 5: Commit acceptance documentation**

```bash
git add README.md
git commit -m "docs: record foundation acceptance boundary"
```

## Plan self-review

- Spec coverage for this milestone: local FastAPI/React architecture, Docker portability, loopback binding, paper-mode default, secret isolation, explicit system state, tests and CI are covered.
- Deliberately deferred to separate plans: domain models, market calendar, market data, scanner scoring, options analysis, risk engine, journal database, news/social providers, Schwab OAuth, approval lifecycle, live-mode arming and Proxmox deployment.
- Type consistency: the backend and frontend use the same four-field health contract and the same literal `paper` trading mode.
- Safety boundary: no task creates credentials, brokerage code, market orders or a path that accepts live mode.
