# Milestone 8 Decision-Support Dashboard Expansion Specification

Date: July 20, 2026
Status: Draft specification
Depends on: Milestones 1-7
Roadmap milestone: 8

## Purpose

Milestone 8 expands the local web application into a read-only decision-support
dashboard. It presents market state, scanner candidates, catalyst context,
options analysis, risk decisions, journal events, and system health without
adding approval, preview, execution, broker authentication, or order controls.

The dashboard is an inspection surface. It helps an operator trace a proposal
from source observations through score, catalyst, options, and risk output, but
it cannot create or modify any trading lifecycle record.

## Approved Design Decisions

- Keep every Milestone 8 API endpoint read-only and side-effect free.
- Build dashboard API responses from persisted records and deterministic fixture
  replay outputs already introduced by Milestones 1-7.
- Add bounded view-model endpoints instead of exposing repository models directly.
- Preserve the current paper-mode banner on every dashboard view.
- Use tabs or equivalent in-app navigation for market overview, scanner,
  candidate detail, risk, journal, and analytics views.
- Treat stale, unavailable, quarantined, or incomplete data as first-class states.
- Hide approval, order, broker, credential, and live-mode controls completely.
- Use compact, scan-friendly layouts rather than marketing pages or hero sections.

## Goals

- Show current health, market-state, data-freshness, and paper-mode status.
- Show the eligible universe and latest scanner runs with score components,
  reasons, strategy labels, and qualification state.
- Show candidate details linking source observations, scanner evidence,
  catalysts, options-analysis outcomes, and risk decisions.
- Show option-spread and share-proposal facts with maximum loss, liquidity,
  assignment, event, and tax warnings.
- Show risk checks, locks, sizing, exposure, reservations, and blocking reasons.
- Show append-only journal/audit events with correlation identifiers and source
  record keys.
- Show simple analytics for counts, blocked reasons, stale states, and strategy
  distribution from local deterministic data.
- Provide responsive, accessible UI behavior with contract tests and error
  boundary coverage.

## Non-Goals

- Approval buttons, paper execution, fills, position lifecycle operations, or
  simulated broker actions.
- Schwab OAuth, Schwab read-only account integration, broker balances, broker
  previews, or broker order contract validation.
- Live-mode arming, live order submission, credential entry, or secret display.
- New market-data, news, filings, options, or risk provider integrations.
- Background scheduling, polling beyond bounded frontend refreshes, websocket
  streaming, or push notifications.
- Portfolio accounting changes beyond displaying records already produced by
  approved milestones.

## Architecture

Milestone 8 adds a dashboard read-model layer on the backend and a richer React
application on the frontend.

1. Backend repository query services read existing append-only records and
   produce bounded DTOs for dashboard use.
2. FastAPI dashboard routes expose read-only JSON contracts under `/api/dashboard`.
3. Frontend API clients consume typed contracts and model unavailable, stale, and
   partial states explicitly.
4. React view components render compact dashboard sections with stable layout,
   keyboard navigation, error boundaries, and no executable trading controls.
5. Tests verify API contracts, state rendering, accessibility-critical labels,
   responsive behavior, and the absence of forbidden controls.

The dashboard must not import or call broker, approval, order-preview,
order-submission, credential, or live-mode modules. Backend endpoints may query
existing order/position/risk tables only for display facts that already exist in
storage.

## Dashboard API Contracts

All dashboard endpoints return `Cache-Control: no-store` and include:

- `as_of`: aware UTC timestamp for response assembly.
- `data_state`: `ready`, `stale`, `partial`, or `unavailable`.
- `sources`: sorted source summaries with source name, version, observed time,
  freshness state, and digest or stable key when available.
- `warnings`: bounded display warnings with stable codes.

Required endpoints:

- `GET /api/dashboard/overview`
- `GET /api/dashboard/candidates`
- `GET /api/dashboard/candidates/{candidate_key}`
- `GET /api/dashboard/risk`
- `GET /api/dashboard/journal`
- `GET /api/dashboard/analytics`

Endpoints must use cursor or limit parameters for potentially long lists.
Invalid cursors return a safe validation error. Missing dashboard data returns a
successful unavailable or empty state unless the database itself cannot be read.

## View Requirements

### Market Overview

- Paper-mode banner remains visible.
- Market-state status includes XNYS session label, entry window, next transition,
  freshness, and explicit U.S. Eastern times with local display labels.
- Data-source summaries show whether market data, scanner, catalysts, options,
  and risk are ready, stale, partial, or unavailable.

### Scanner

- Candidate list shows symbol, direction, strategy, score, qualification state,
  catalyst state, risk state, source timestamps, and top reasons.
- Filters are local display filters only. They do not change policy or create
  records.
- Stale scanner data is visually distinct and cannot appear approval-ready.

### Candidate Detail

- Detail view traces the candidate through scanner evidence, score components,
  catalysts, options analysis, and risk decision.
- Every section shows source keys, policy versions, input/result digests, and
  observed timestamps when available.
- Missing downstream analysis shows a clear pending, unavailable, or blocked
  state instead of omitting the section.

### Risk

- Risk view shows latest risk decisions, blocking checks, warning checks,
  exposure summaries, sizing results, active locks, and reservations.
- Tax-warning language includes the existing non-advice disclaimer.
- No risk view control may clear a lock, reserve risk, approve a proposal, or
  submit any order-shaped payload.

### Journal

- Journal view shows append-only audit events by time, event type, correlation id,
  actor, source table/key, and bounded payload summary.
- It supports local filtering by event type and correlation id.
- It must not expose secrets, raw provider payloads, raw news text, credentials,
  or unbounded JSON blobs.

### Analytics

- Analytics view summarizes deterministic local data: candidate counts, strategy
  mix, qualified vs blocked counts, common block reasons, stale-data counts, and
  risk-status distribution.
- Analytics are explanatory only and cannot feed back into scoring, sizing, or
  eligibility.

## Frontend UX And Accessibility

- Use the existing dark, compact application style and extend it with restrained
  colors for ready, warning, blocked, stale, and unavailable states.
- Keep content dense but readable on desktop and mobile.
- Avoid nested cards and marketing-style hero layouts.
- Use semantic headings, tables or definition lists where appropriate, status
  regions for freshness changes, and accessible names for navigation controls.
- No text may overlap or overflow fixed UI surfaces at 320px width.
- Error boundaries show the affected panel as unavailable while preserving the
  paper-mode banner and other loaded panels.

## Safety Requirements

- The UI must not render buttons or links labeled or shaped as approve, preview,
  submit, buy, sell, execute, place order, connect broker, arm live mode, or clear
  lock.
- The backend must not accept POST, PUT, PATCH, or DELETE dashboard routes.
- Dashboard DTOs must reject or redact secret-like keys and unbounded provider
  text.
- Every endpoint and component must preserve paper-only messaging.
- Stale or unavailable data must never be shown as actionable or current.

## Testing And Verification

- Backend unit tests cover DTO assembly, pagination, stale/unavailable states,
  redaction, forbidden-route absence, and empty database behavior.
- Backend API tests cover every dashboard endpoint and response contract.
- Frontend tests cover navigation, panel rendering, unavailable states, candidate
  traceability, forbidden-control absence, and error boundaries.
- Accessibility-focused tests cover landmarks, headings, tab labels, and status
  text.
- Build checks include backend Ruff, strict mypy, pytest, frontend lint, frontend
  tests, frontend build, Alembic head upgrade, Docker compose smoke, and
  `scripts/verify-foundation.sh`.

## Exit Criteria

- A user can trace a candidate from source observations through score, catalysts,
  options analysis, and risk output.
- Stale, partial, and unavailable data states are unmistakable.
- No dashboard endpoint or UI control can approve, preview, simulate, submit, or
  live-arm a trade.
- Every display contract includes timestamps, source state, rule versions, and
  stable identifiers where available.
- Full backend, frontend, migration, fixture, Docker, and smoke gates pass.
