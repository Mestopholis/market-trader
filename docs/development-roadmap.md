# Market Trader Development Roadmap

Date: July 17, 2026  
Status: Approved roadmap  
Foundation branch: `foundation`

## Purpose

This roadmap sequences the work remaining after the paper-only FastAPI, React, Docker Compose, and CI foundation. Each milestone must receive its own reviewed specification and implementation plan before development begins. Completing a milestone does not authorize work from a later milestone.

The system remains paper-only until Milestone 14 is separately approved. Schwab credentials are prohibited before Milestone 11, Schwab order submission is prohibited before Milestone 12, and live-order submission is prohibited before Milestone 14.

## Delivery rules

- Preserve a working, testable application at the end of every milestone.
- Default to paper mode after every install, upgrade, restart, or authentication recovery.
- Keep provider integrations behind explicit interfaces so deterministic fixtures and replay remain available.
- Treat broker data as authoritative for any future order-affecting decision.
- Store timestamps in UTC and display market times with explicit U.S. Eastern labels.
- Version deterministic rules, configurations, inputs, and decisions.
- Add automated tests, documentation, migrations, and operational checks within the milestone that needs them.
- Do not combine Schwab authentication, paper orders, and live-mode arming into one implementation plan.

## Milestone dependency flow

1. Domain storage and audit foundation
2. Market calendar and scheduling foundation
3. Provider-neutral market data and replay
4. Eligible universe, regime, scanner, and scoring
5. Catalysts, events, news, and filings
6. Options analysis and spread construction
7. Risk, sizing, exposure, and tax warnings
8. Decision-support dashboard expansion
9. Paper approval, execution, and position lifecycle
10. Reliability, recovery, observability, and security
11. Schwab OAuth and read-only integration
12. Schwab order-contract integration and extended paper validation
13. Proxmox and PostgreSQL deployment
14. Separately approved live-mode arming

Milestones 5 and 6 may begin independently after Milestone 3, but both must be complete before Milestone 7. All other milestones should follow the listed order unless a reviewed plan explicitly demonstrates that an earlier start preserves the same safety gates.

---

## Milestone 1: Domain storage and audit foundation

**Status:** Complete.

**Objective:** Establish persistent, versioned domain records without introducing market providers or broker access.

**Depends on:** Completed application foundation.

**Deliverables:**

- SQLAlchemy or equivalent repository boundary compatible with SQLite and PostgreSQL.
- Migration tooling and a repeatable database initialization workflow.
- Domain models for symbols, instruments, market-data snapshots, signals, candidates, proposed trades, approvals, orders, fills, positions, risk locks, journal events, and configuration versions.
- UTC timestamp and immutable event conventions.
- Append-only audit journal with correlation identifiers connecting inputs, decisions, and user actions.
- Repository tests, migration tests, and backup/restore fixtures.

**Exit criteria:** A clean database can be migrated forward, representative records can be stored and reconstructed through repositories, and an audit trail cannot be changed through normal application APIs.

**Explicitly excluded:** Market data, scanner logic, external providers, Schwab authentication, and order submission.

## Milestone 2: Market calendar and scheduling foundation

**Status:** Complete.

**Objective:** Make all time-sensitive behavior exchange-calendar aware and deterministic.

**Depends on:** Milestone 1.

**Deliverables:**

- U.S. equity exchange calendar supporting holidays, early closes, and daylight-saving transitions.
- Session-date and market-state services with explicit U.S. Eastern display labels.
- Version-one entry window rules, normally 9:45 a.m. through 3:30 p.m. Eastern during regular sessions.
- Scheduler interfaces for scans, refreshes, end-of-day jobs, and recovery work.
- Deterministic clock injection and calendar fixtures for tests.

**Exit criteria:** Automated tests cover normal sessions, weekends, holidays, early closes, daylight-saving boundaries, stale timestamps, and prohibited entry windows.

**Explicitly excluded:** Live schedules driven by broker data, background trade execution, and automatic orders.

## Milestone 3: Provider-neutral market data and replay

**Status:** Complete.

**Completion:** Delivered by the approved
[specification](plans/2026-07-18-milestone-3-provider-neutral-market-data-and-replay-spec.md),
[implementation plan](plans/2026-07-18-milestone-3-provider-neutral-market-data-and-replay-implementation-plan.md),
and [operator runbook](milestone-3-market-data-replay.md).

**Objective:** Support deterministic development and testing with normalized data contracts before connecting Schwab.

**Depends on:** Milestones 1 and 2.

**Deliverables:**

- Provider interfaces for quotes, candles, option chains, corporate actions, and data freshness.
- Normalized schemas containing source, observed time, session date, quality state, and configuration version.
- Recorded fixtures and replay tools for regular sessions, stale data, halts, splits, wide spreads, and provider failures.
- Validation and quarantine of malformed, incomplete, out-of-order, or stale payloads.
- Cache and rate-limit boundaries that do not obscure data timestamps.

**Exit criteria:** Downstream code can run entirely from deterministic fixtures, provider failures degrade safely, and stale critical data is represented as a blocking state.

**Explicitly excluded:** Schwab credentials, real-time Schwab data, account data, and orders.

## Milestone 4: Eligible universe, regime, scanner, and scoring

**Status:** Complete.

**Completion:** Delivered by the approved
[specification](plans/2026-07-19-milestone-4-eligible-universe-regime-scanner-and-scoring-spec.md),
[implementation plan](plans/2026-07-19-milestone-4-eligible-universe-regime-scanner-and-scoring-implementation-plan.md),
and [operator runbook](milestone-4-scanner-and-scoring.md).

**Objective:** Generate explainable bullish and bearish candidates from deterministic market inputs.

**Depends on:** Milestones 1–3.

**Deliverables:**

- Curated-symbol universe and versioned eligibility filters for price, liquidity, history, security type, halts, and adjusted instruments.
- Market-regime classification using the approved trend, breadth, sector, volume, volatility, and macro inputs available at this stage.
- Bullish breakout, bullish pullback, bearish breakdown, bearish failed-rally, and news-continuation strategy interfaces.
- Versioned component scoring and thresholds with exposed observations and explanations.
- Candidate persistence, deduplication, correlation-aware evidence handling, and replay evaluation.

**Exit criteria:** Fixed input snapshots always produce identical candidates and scores; ineligible symbols cannot become approval-ready; every score can be reconstructed and explained.

**Explicitly excluded:** Trade sizing, option selection, approval actions, and order submission.

## Milestone 5: Catalysts, events, news, and filings

**Status:** Complete.

**Completion:** Delivered by the approved
[specification](plans/2026-07-19-milestone-5-catalysts-events-news-and-filings-spec.md),
[implementation plan](plans/2026-07-19-milestone-5-catalysts-events-news-and-filings-implementation-plan.md),
and [operator runbook](milestone-5-catalysts-events-news-and-filings.md).

**Objective:** Add verified event context without allowing untrusted text or language-model output to control trading decisions.

**Depends on:** Milestone 3. Integrates with Milestone 4.

**Deliverables:**

- Interfaces for company news, earnings calendars, SEC filings, economic releases, and optional authorized social data.
- Source attribution, publication and ingestion timestamps, deduplication, and materiality categories.
- Deterministic catalyst confirmation rules and event-risk windows.
- Isolation of external text from credentials, tools, and approval instructions.
- Optional language-model summaries that remain cited, non-authoritative, and excluded from scores and order selection.

**Exit criteria:** Every catalyst is traceable to a source; earnings and macro conflicts can block candidates; social activity alone cannot satisfy the catalyst requirement; malformed or unavailable sources fail safely.

**Explicitly excluded:** Automated sentiment trading, uncited summaries, and model-driven eligibility or scoring.

## Milestone 6: Options analysis and spread construction

**Status:** Complete.

**Completion:** Delivered by the approved
[specification](plans/2026-07-19-milestone-6-options-analysis-and-spread-construction-spec.md),
[implementation plan](plans/2026-07-19-milestone-6-options-analysis-and-spread-construction-implementation-plan.md),
and [operator runbook](milestone-6-options-analysis-and-spread-construction.md).

**Objective:** Analyze standard option contracts and construct defined-risk candidates without placing orders.

**Depends on:** Milestone 3. Integrates with Milestones 4 and 5.

**Deliverables:**

- Standard-contract validation and rejection of adjusted or nonstandard deliverables.
- Expiration, delta, open-interest, volume, bid/ask, and width filters.
- Bull call spread and bear put spread construction for the approved 30–60 DTE range.
- Greeks, payoff, technical-stop, maximum-loss, liquidity, and execution-quality calculations.
- Earnings, ex-dividend, early-assignment, expiration, and pin-risk warnings.
- Synthetic option-chain and early-assignment test scenarios.

**Exit criteria:** Identical chains produce identical spread candidates; invalid or illiquid contracts are rejected with reasons; maximum loss and assignment stress are displayed and tested.

**Explicitly excluded:** Naked options, credit spreads, 0DTE, broker previews, and order submission.

## Milestone 7: Risk, sizing, exposure, and tax warnings

**Status:** Complete.

**Completion:** Delivered by the approved
[specification](plans/2026-07-20-milestone-7-risk-sizing-exposure-and-tax-warnings-spec.md),
[implementation plan](plans/2026-07-20-milestone-7-risk-sizing-exposure-and-tax-warnings-implementation-plan.md),
and [operator runbook](milestone-7-risk-sizing-exposure-and-tax-warnings.md).

**Objective:** Enforce the approved capital, loss, correlation, settlement, and taxable-account boundaries before a proposal can be approval-ready.

**Depends on:** Milestones 1–6.

**Deliverables:**

- Share and debit-spread sizing with integer and one-contract rejection rules.
- Per-trade, aggregate, daily, weekly, position-count, trade-count, correlation-group, and drawdown limits.
- Reserved-risk accounting for working orders and assignment stress.
- Daily, weekly, stale-data, authentication, account-mismatch, and strategy-review locks with explicit reset rules.
- Buying-power abstraction that excludes borrowed buying power and represents settlement restrictions.
- Wash-sale calendar and short-term/long-term tax-estimate warnings with clear non-advice language.
- Versioned risk decisions with a complete explanation and input snapshot.

**Exit criteria:** Boundary-value tests prove that unsafe proposals are rejected rather than rounded up; locks cannot be bypassed by the UI; every risk result is deterministic and auditable.

**Explicitly excluded:** Broker account balances, broker order previews, and live trading.

## Milestone 8: Decision-support dashboard expansion

**Status:** Complete.

**Completion:** Delivered by the approved
[specification](plans/2026-07-20-milestone-8-decision-support-dashboard-expansion-spec.md)
and
[implementation plan](plans/2026-07-20-milestone-8-decision-support-dashboard-expansion-implementation-plan.md),
and [operator runbook](milestone-8-decision-support-dashboard.md).

**Objective:** Present market state, candidates, risks, and audit information without exposing executable trading controls.

**Depends on:** Milestones 1–7.

**Deliverables:**

- Market-overview, scanner, candidate-detail, risk, journal, and analytics views.
- Explicit data timestamps, source states, session labels, rule versions, and paper-mode banner.
- Candidate explanations showing score components, catalysts, option exposures, and blocking conditions.
- Safe unavailable and stale-data states that hide or disable dependent actions.
- Accessibility, responsive layout, frontend contract tests, and error-boundary coverage.

**Exit criteria:** A user can trace a candidate from source observations through score and risk output; stale or unavailable state is unmistakable; no control can submit or simulate an order yet.

**Explicitly excluded:** Approval buttons, broker credentials, and order submission.

## Milestone 9: Paper approval, execution, and position lifecycle

**Status:** Complete. See the
[specification](plans/2026-07-20-milestone-9-paper-approval-execution-position-lifecycle-spec.md),
[implementation plan](plans/2026-07-20-milestone-9-paper-approval-execution-position-lifecycle-implementation-plan.md),
and [operator runbook](milestone-9-paper-approval-execution-position-lifecycle.md).

**Next planning action:** Review and approve the Milestone 10 reliability, recovery, observability, and security specification and implementation plan.

**Objective:** Validate the complete user workflow using a deterministic simulated broker only.

**Depends on:** Milestones 1–8.

**Deliverables:**

- Approval cards supporting approve, modify, paper trade, and reject actions.
- Expiring approvals, fresh simulated quotes, final previews, and limit-order-only enforcement.
- Deterministic paper broker for submissions, partial fills, rejects, cancels, cancel/replace, timeouts, and reconciliation.
- Position state, technical stops, profit targets, time exits, event exits, and expiration management.
- Restart recovery that prioritizes open positions and working orders.
- Journaled user actions, previews, state transitions, fills, and execution-quality data.

**Exit criteria:** End-to-end paper scenarios cover success, partial fill, reject, stale quote, expired approval, cancel race, restart recovery, and simulated assignment; no external broker endpoint is reachable.

**Explicitly excluded:** Schwab authentication, Schwab orders, and live mode.

## Milestone 10: Reliability, recovery, observability, and security

**Status:** Draft specification and implementation plan ready for review. See the
[specification](plans/2026-07-21-milestone-10-reliability-recovery-observability-security-spec.md)
and
[implementation plan](plans/2026-07-21-milestone-10-reliability-recovery-observability-security-implementation-plan.md).

**Objective:** Harden the local paper system before any brokerage credentials are introduced.

**Depends on:** Milestone 9.

**Deliverables:**

- Structured logs with secret redaction and correlation identifiers.
- Metrics and health states for providers, scheduler jobs, data freshness, risk locks, and reconciliation.
- Backup, restore, database-integrity, restart-recovery, and disaster-recovery procedures.
- Dependency, container, secret, and static-security scans in CI.
- Local authentication and session protection for sensitive screens.
- Fault-injection tests for provider loss, database contention, clock drift, disk pressure, and process restart.

**Exit criteria:** Recovery drills preserve the audit trail and paper positions; secrets cannot enter logs or frontend responses; critical failures produce blocking system states and actionable diagnostics.

**Explicitly excluded:** Schwab credentials and externally reachable deployment.

## Milestone 11: Schwab OAuth and read-only integration

**Objective:** Connect Schwab for read-only market and account information while keeping every order path disabled.

**Depends on:** Milestone 10 and a separately approved Schwab integration specification.

**Deliverables:**

- OAuth authorization, callback, token refresh, revocation, rotation, and encrypted secret storage.
- Broker adapter for read-only quotes, chains, accounts, balances, positions, and transaction reconciliation.
- Rate limiting, retry policy, stale-data handling, authentication locks, and account-identity verification.
- Strict credential isolation from frontend responses, logs, external text, and language-model inputs.
- Sandbox or recorded-contract tests where Schwab provides no test environment.

**Exit criteria:** Authentication recovery always returns the system to paper mode; revoked or expired credentials block broker-dependent actions; account and market data can be reconciled without an order-submission permission in the application.

**Explicitly excluded:** Order preview, order submission, and live-mode arming.

## Milestone 12: Schwab order-contract integration and extended paper validation

**Objective:** Validate broker-specific order contracts and the paper workflow without enabling live-account submission or assuming Schwab provides a paper-order API.

**Depends on:** Milestone 11 and a separately approved broker-order specification.

**Deliverables:**

- Schwab order translation for long shares, bull call spreads, and bear put spreads only.
- Fresh quote, chain, Greeks, account, position, buying-power, corporate-action, and order-preview checks through supported non-live capabilities or recorded contracts.
- Schwab sandbox or paper-order submission only if Schwab provides a supported non-live endpoint; otherwise retain the deterministic paper broker and validate separately in thinkorswim paperMoney. A live account must never be used as a test substitute.
- Broker-contract tests for idempotency, cancel/replace sequencing, timeouts, status transitions, and restart recovery.
- Synthetic early-assignment and broker-outage exercises where paperMoney behavior is incomplete.
- Paper-performance reports covering slippage, fill quality, false positives, drawdowns, and rule stability.

**Exit criteria:** The supported non-live validation mechanism is documented, the approved paper-graduation sample and duration are completed, reconciliation discrepancies block new submissions, and zero application path can target a live account.

**Explicitly excluded:** Live-account order submission and automatic trading.

## Milestone 13: Proxmox and PostgreSQL deployment

**Objective:** Move the validated paper system to a recoverable private deployment without changing domain behavior.

**Depends on:** Milestones 10–12.

**Deliverables:**

- PostgreSQL migration and repository-compatibility verification.
- Proxmox deployment manifests, persistent storage, encrypted backups, and restore drills.
- HTTPS, authenticated access, VPN-only exposure, firewall rules, and secret management.
- Deployment health checks, rolling or controlled upgrades, rollback, and maintenance procedures.
- Monitoring and alerts for service health, data freshness, jobs, storage, backups, and reconciliation.

**Exit criteria:** A clean environment can be deployed and restored from documentation; no service is publicly exposed; upgrade and rollback drills preserve paper state and audit history.

**Explicitly excluded:** Live-mode arming.

## Milestone 14: Separately approved live-mode arming

**Objective:** Consider limited live trading only after paper graduation, operational hardening, and explicit user approval.

**Depends on:** All prior milestones, documented paper-graduation evidence, account suitability review, current broker-rule review, and a new approved live-trading specification.

**Required design topics before implementation:**

- Multi-step arming ceremony with short expiry, explicit account identity, and automatic reversion to paper mode.
- Broker preview and confirmation requirements for every order.
- Limit-order-only enforcement and prohibition of fully automatic submission.
- Protective-order acknowledgement, monitoring-outage disclosure, and recovery behavior.
- Live risk limits, kill switches, reconciliation locks, credential incidents, and audit review.
- OCC options disclosure acknowledgement and current Schwab permission requirements.
- Rollback to paper mode after deploys, restarts, authentication recovery, discrepancies, or safety-rule changes.

**Exit criteria:** Defined only by the separately approved live-trading specification. This roadmap does not authorize implementation or activation.

**Explicitly excluded:** Fully automatic trading, naked options, short shares, credit spreads, undefined-risk positions, 0DTE, market orders, and bypasses of user confirmation.

---

## Cross-milestone acceptance requirements

Every milestone specification and implementation plan must identify:

- Exact files, interfaces, migrations, and data contracts it changes.
- Unit, integration, replay, fault-injection, security, and acceptance tests appropriate to its risk.
- How stale, missing, malformed, conflicting, or unavailable data fails safely.
- What is persisted for audit and how decisions are reconstructed.
- Which later milestones remain explicitly unavailable.
- Documentation and operational procedures required before completion.

## Next planning action

Review and approve the Milestone 10 reliability, recovery, observability, and
security specification and implementation plan. Milestone 10 must harden the
local paper system before any brokerage credentials are introduced.
