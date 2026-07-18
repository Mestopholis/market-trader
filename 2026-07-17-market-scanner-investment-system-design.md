# Taxable Investment Portfolio and One-Click Market Scanner

Date: July 17, 2026  
Status: Approved design

## 1. Purpose

Create a disciplined investment and trading system for a $50,000 taxable brokerage account with an approximately 18-year retirement horizon. Most capital remains in a diversified, tax-efficient long-term portfolio. A strictly limited sleeve supports bullish and bearish share and defined-risk option trades surfaced by a real-time scanner and submitted only after explicit user approval.

This specification is an operational design, not a promise of returns or individualized tax advice.

## 2. Goals

- Preserve long-term compounding as the primary objective.
- Isolate active-trading losses from the retirement-oriented portfolio.
- Support bullish and bearish opportunities while retaining a structural bullish bias.
- Explain every signal, proposed order, risk, catalyst and option exposure.
- Require one-click user approval followed by a fresh quote and final order preview.
- Begin in paper mode and graduate cautiously to live trading.
- Run locally at first and move to a Proxmox-hosted deployment without redesign.
- Retain sufficient audit data to reconstruct and evaluate every alert and trade.

## 3. Non-goals for Version One

- Fully automatic trade execution.
- Naked options, short shares, credit spreads or undefined-risk positions.
- 0DTE options or earnings-event speculation.
- High-frequency trading or latency-sensitive strategies.
- Treating social sentiment as a standalone trade trigger.
- Definitive legal or tax determinations.
- Guaranteed stop prices, fills, profits or loss limits.

## 4. Portfolio Structure

The starting account is divided as follows:

| Sleeve | Amount | Initial vehicle | Purpose |
|---|---:|---|---|
| Broad U.S. equities | $25,000 | VTI or equivalent | Primary long-term growth |
| International equities | $5,000 | VXUS | Geographic diversification |
| Quality/dividend equities | $5,000 | SCHD | Quality and value diversification |
| Treasury reserve | $5,000 | SGOV or Treasury money-market fund | Stability and deployable cash |
| Tactical positions | $5,000 | Sector ETFs or selected companies | Medium-term opportunities |
| Active/options sleeve | $5,000 | Cash and defined-risk trades | Scanner-driven experimentation |

The $40,000 core is retirement-oriented. Tactical and active capital must not be used to average down or rescue losing trades. The core should be funded in four installments: 40% initially and the balance over roughly three months, unless changed by the user.

### 4.1 Suitability checkpoint

The allocation is provisional until it is evaluated with the user's entire household balance sheet and existing 401(k) allocation. Before funding, confirm that the $50,000 is surplus to:

- A separately held emergency reserve.
- Expected federal and Illinois tax payments, including consulting-business taxes.
- Near-term solar payments and other committed obligations.
- Any cash reserved for a real-estate down payment or acquisition costs.
- High-interest debt, if any.

The user's low-rate 2.875% mortgage is not treated as high-interest debt. Because the user has also considered short-term-rental real estate and has significant W-2/consulting income, the application must report trading results after estimated tax drag, not only pre-tax performance. The long-term allocation should be revisited after importing the existing 401(k) holdings; apparent diversification inside this account may duplicate exposure held elsewhere.

VTI and SCHD overlap by design, but the quality/dividend tilt must be justified against its taxable dividend cost. The portfolio review should compare that tilt with a simpler VTI/VXUS/Treasury allocation before funding.

Review the core at least annually and rebalance with new cash when possible. A holding that moves more than five percentage points from its target triggers review, not an automatic taxable sale.

### 4.2 Tactical-sleeve boundary

The $5,000 tactical sleeve is not additional intraday buying power. It begins in the Treasury reserve until a separate medium-term thesis qualifies. Tactical positions:

- Prefer diversified sector ETFs over single companies during the first year.
- Are limited to two positions and $2,500 per position.
- Require a written catalyst, invalidation condition and intended review date.
- Are evaluated weekly rather than by the intraday approval workflow.
- Count toward correlation, sector and total drawdown limits.
- Cannot be transferred into the active sleeve after a trading loss.

## 5. Taxable-Account Policy

- Use specific-lot identification for dispositions.
- Do not actively trade VTI, VXUS or SCHD in the scanner sleeve.
- Prefer SPY, QQQ, IWM and sector ETFs for index-based tactical signals.
- Maintain an internal wash-sale warning calendar for shares and options.
- Warn about purchases within 30 days before or after a proposed loss sale.
- Treat wash-sale output as a warning, not a definitive tax conclusion.
- Separate estimated short-term and long-term gains in analytics.
- Export broker transactions and realized-gain data monthly for reconciliation.
- Rebalance the core primarily with new contributions and cash flows.
- Automatic dividend reinvestment should initially remain disabled to preserve tax-lot control and reduce accidental wash-sale conflicts.
- The wash-sale warning must consider known activity in all user-controlled taxable accounts, IRAs and a spouse's accounts where applicable; the application cannot detect accounts that have not been connected or imported.
- Options, exercises, assignments and replacement securities can create fact-specific tax treatment. The system records them for review but does not label a transaction definitively tax-safe.
- Track qualified dividends, nonqualified dividends, Treasury income and return-of-capital adjustments separately when broker data supports it.
- Preserve original broker statements and tax documents as the authoritative records; internal estimates are for decision support only.

## 6. Brokerage Choice

Charles Schwab is the target broker. The design uses thinkorswim for charting and paper trading and Schwab's individual Trader API for market data, account information and order submission. Broker access is isolated behind an adapter so another broker can be supported later.

Initial option permissions may include long calls and puts, covered calls, cash-secured puts and defined-risk vertical spreads. The application will use only long shares, bull call spreads and bear put spreads in version one.

If Schwab requires a margin-enabled account for spreads, margin may be enabled for permission and settlement mechanics only. The risk engine must never size a position using borrowed buying power. It must also account for unsettled funds, T+1 settlement, broker house requirements and current intraday-margin rules before presenting an order.

## 7. Architecture

### 7.1 Components

- **FastAPI backend:** orchestration, APIs, authentication and application logic.
- **React dashboard:** market overview, scanner, approval, positions and analytics.
- **Scanner engine:** technical indicators, regime classification and candidate generation.
- **Catalyst engine:** news, filings, earnings, macro events and social signals.
- **Option engine:** chain filtering, Greeks, liquidity and spread construction.
- **Risk engine:** position sizing, exposure limits, circuit breakers and tax warnings.
- **Broker adapter:** quotes, chains, accounts, order preview, submission and status.
- **Audit journal:** immutable decision and execution events plus user annotations.
- **Scheduler:** market-session scans, refreshes and end-of-day analysis.

All trade eligibility, scoring, sizing and risk decisions are deterministic and versioned. Any language model may summarize cited news or explain a signal, but its output cannot change a score, select an order or bypass a risk rule. External text is treated as untrusted input and isolated from credentials, tools and approval instructions.

### 7.2 Storage and deployment

- SQLite is the local default.
- Database access must use migrations and a repository boundary compatible with PostgreSQL.
- Docker Compose packages the frontend, backend and supporting services.
- Secrets remain outside source control and never enter logs.
- The initial system binds to localhost.
- A future Proxmox deployment uses PostgreSQL, HTTPS, authenticated access and VPN-only network exposure.

### 7.3 Time and session model

- Store timestamps in UTC and display market times in U.S. Eastern Time with explicit timezone labels.
- Use an exchange calendar that handles holidays, early closes and daylight-saving transitions.
- Version one opens new trades only during regular market hours, normally from 9:45 a.m. through 3:30 p.m. Eastern.
- Premarket, after-hours and overnight entry are excluded.
- Every calculation and stored decision includes the data timestamp, session date and strategy/configuration version.

## 8. Market-Regime Model

Regime inputs include SPY and QQQ relative to their 20-, 50- and 200-day averages, breadth, sector participation, volatility, relative volume and scheduled macro events.

| Regime | Bullish alert allocation | Bearish alert allocation |
|---|---:|---:|
| Strong uptrend | 90% | 10% |
| Normal/neutral | 70% | 30% |
| Correction | 50% | 50% |
| Confirmed bear trend | 30% | 70% |

These values influence alert ranking and permitted active risk. They do not liquidate or reverse the long-term core. Bearish trades require stronger evidence when the broad market is bullish.

## 9. Scanning Strategies

### 9.0 Eligible universe

The initial universe is a curated list of highly liquid U.S.-listed stocks and unlevered ETFs. Initial eligibility rules are configurable but begin with:

- Price of at least $10.
- Median daily dollar volume of at least $50 million over 20 sessions.
- At least 90 calendar days of trading history.
- No OTC securities, penny stocks, leveraged/inverse ETFs, nonstandard adjusted options or symbols under a known trading halt.
- Options candidates require standard 100-share contracts, reliable Greeks, and both legs to meet the configured open-interest, volume and bid/ask tests.

Initial per-leg option thresholds are open interest of at least 500 contracts, current-day volume of at least 50 contracts and a bid/ask width no greater than 10% of the midpoint. These thresholds must be validated during paper testing and changed only through versioned configuration. The scanner may observe a broader discovery universe, but an ineligible symbol cannot generate an approval-ready order.

### 9.1 Bullish breakout

Require price above VWAP and relevant moving averages, strong relative volume, sector confirmation and a break through defined resistance.

### 9.2 Bullish pullback

Require an established uptrend, controlled pullback toward VWAP, the 9/20 EMA or a prior breakout, followed by renewed demand and improving volume.

### 9.3 Bearish breakdown

Require price below VWAP, weak relative strength, sector weakness and a confirmed break below defined support.

### 9.4 Bearish failed rally

Require an established downtrend, a rally into resistance or VWAP, rejection and renewed selling volume.

### 9.5 News-driven continuation

Require a confirmed material catalyst, abnormal volume and price structure that persists after the initial reaction. Social activity cannot satisfy the catalyst requirement by itself.

## 10. Candidate Scoring

| Component | Weight |
|---|---:|
| Trend and chart structure | 25 |
| Relative volume and liquidity | 20 |
| Market and sector alignment | 15 |
| Confirmed catalyst | 15 |
| Reward-to-risk | 15 |
| Option liquidity and Greeks | 10 |

- Below 75: logged but not alerted.
- 75–84: watch alert.
- 85–100: eligible for an approval-ready order, subject to all risk checks.

The score must expose its component values and supporting observations. A score alone is never an explanation.

Correlated inputs must not be counted as independent confirmation. Score definitions, thresholds and regime rules are versioned so performance can be attributed to the exact rule set. Changes require out-of-sample or walk-forward evidence rather than repeated tuning on the same history.

## 11. Options Policy

- Version one supports bull call spreads and bear put spreads only.
- Target 30–60 days to expiration.
- Prefer a purchased leg near 0.55–0.70 absolute delta and a sold leg near 0.25–0.40 absolute delta, subject to liquidity and payoff quality.
- Reject contracts with unacceptable bid/ask spreads, volume or open interest.
- Surface delta, gamma, theta, vega and implied volatility on every approval card.
- Do not hold a position inside 14 DTE under normal operation.
- Do not open positions immediately before the underlying's earnings.
- No naked positions, 0DTE, short shares, automatic exercise strategy or averaging down.
- Exclude adjusted and nonstandard deliverables in version one.
- Run an assignment stress test before submission: show the 100-share exposure, capital requirement and recovery procedure if either short leg is assigned.
- A short leg may be assigned before expiration. Check ex-dividend dates, remaining extrinsic value and whether the short leg is in the money on every scan and position refresh.
- Block a new call spread that crosses a near ex-dividend date when early-assignment risk is material.
- Close or escalate spreads before expiration to avoid pin risk and an unintended long or short stock position.
- Treat paperMoney results cautiously because early assignment is not modeled the same way as a live account. Paper validation must include synthetic early-assignment scenarios.
- Require the user to acknowledge the current OCC Characteristics and Risks of Standardized Options before live-option mode can be armed.

## 12. Risk Controls

| Control | Initial setting |
|---|---:|
| Maximum planned loss per trade | $100 |
| Maximum aggregate open risk | $250 |
| Maximum daily realized loss | $150 |
| Maximum weekly realized loss | $400 |
| Maximum simultaneous positions | 2 |
| Maximum new trades per day | 3 |
| Minimum planned reward-to-risk | 1.75:1 |
| Maximum debit/expiration loss per spread | $100 |
| Initial maximum holding period | 10 trading days |
| Maximum active+tactical drawdown before review | $1,000 |

Share quantity is the integer floor of maximum trade risk divided by entry-to-stop distance. A debit spread must satisfy both the planned technical-stop loss and maximum-expiration-loss constraints. If one contract exceeds limits, the order is rejected rather than rounded up.

The system locks new trading after two losses in a day, a daily or weekly threshold breach, stale critical data, an authentication failure or an account-state mismatch. A daily lock may be reset no earlier than the next regular session. A weekly-loss lock persists through the remainder of the trading week and requires review before the following week. The $1,000 drawdown lock requires a documented strategy review and has no automatic time-based reset.

Daily and weekly loss calculations include realized losses, current unrealized losses and reserved risk on working orders. Aggregate risk includes gap exposure and assignment stress, not merely the premium paid.

Do not open more than one position in the same underlying. Treat highly correlated securities and options as a risk group; combined planned risk in one sector or correlation group may not exceed $150 initially. Broad-index exposure in the active sleeve must be evaluated together with the long-term core rather than treated as independent diversification.

If combined realized and unrealized drawdown across the tactical and active sleeves reaches $1,000, live entries remain locked until the strategy and allocation are manually reviewed. No automatic reset or automatic scaling is permitted.

Stops are not guaranteed execution prices. The UI must state that gaps, liquidity and broker behavior can produce larger realized losses.

## 13. One-Click Approval Lifecycle

1. Scanner detects and records a signal and its complete input snapshot.
2. Risk engine checks exposure, buying power, existing positions, loss limits, wash-sale warnings, earnings, macro events and data freshness.
3. Strategy engine selects shares or a defined-risk spread and calculates entry, stop, target, quantity and time exit.
4. Dashboard displays an approval card with all rationale and risks.
5. User selects Approve, Modify, Paper Trade or Reject.
6. Approve triggers a fresh quote, chain, Greeks, buying-power and account-position validation.
7. Approval expires after 30 seconds, on a halt or Limit Up-Limit Down state, or when configured price/spread movement invalidates it.
8. The exact refreshed order appears in a final broker preview.
9. A confirmed limit order is submitted. Market orders are prohibited.
10. An unfilled order times out and returns for review; it is never automatically chased. A cancel/replace cannot be sent until the broker confirms the original order is canceled or otherwise non-executable.
11. Fills, partial fills, rejects, cancels and reconciliation events are journaled.

Before submission, validate the symbol and option deliverable against splits, mergers, special dividends and other corporate actions. Use the broker's executable bid/ask and order preview rather than a theoretical midpoint to estimate cost. Record NBBO/midpoint, submitted limit and actual fill so execution quality can be measured.

The user action is explicit, and nothing is automatically sent merely because a signal qualifies.

## 14. Exit Management

- Primary exit: underlying invalidates the technical setup.
- Hard backstop: predefined dollar-risk threshold.
- Profit target: normally 1.75–2.0 risk units.
- Time exit: setup fails to progress within two trading days.
- Expiration exit: close before 14 DTE under normal policy.
- Event exit: close before earnings unless a later version explicitly supports event trades.
- Never move a stop solely to avoid realizing a loss.
- Never average down.

Where supported and verified by the broker API, protective contingent orders may be attached. Otherwise the application monitors the condition and presents an urgent exit confirmation. The UI must not imply protection exists until the broker acknowledges the protective order.

Long share entries require an acknowledged broker-native protective order before they are considered protected. Debit spreads have a defined expiration loss, but their technical exits still depend on the application unless a supported broker-native exit is acknowledged. The live-mode screen must state clearly that local monitoring and alerts stop when the computer, network or application is offline. Open-position recovery and reconciliation take priority when the application restarts.

## 15. Data Sources

| Data | Version-one source | Upgrade path |
|---|---|---|
| Quotes and candles | Schwab Trader API | Licensed streaming feed |
| Option chains and Greeks | Schwab Trader API | Institutional options feed |
| Account, positions and orders | Schwab Trader API | Schwab remains authoritative |
| Company news | Finnhub plus official sources | Premium real-time news |
| Earnings calendar | Finnhub, verified with company IR | Premium event feed |
| SEC filings | SEC EDGAR | SEC remains authoritative |
| Economic events | Fed, BLS and official sources | Consolidated licensed calendar |
| Social sentiment | Optional authorized provider | Licensed sentiment feed |

Schwab is the source of truth for any data that affects an order. Critical stale or missing data blocks an approval-ready order.

Each provider adapter defines explicit freshness thresholds, rate limits, retry behavior and market-data entitlements. News is deduplicated by source, event and timestamp; corrected or withdrawn stories invalidate dependent candidates. Historical data use and retention must comply with provider licensing.

Repeated alerts for the same underlying, setup and catalyst are throttled and merged. The system records suppressed duplicates so alert fatigue is reduced without hiding scanner behavior from later analysis.

## 16. News and Social Classification

- **Tier 1:** SEC filings, company investor-relations releases and government announcements.
- **Tier 2:** reputable financial-news feeds and confirmed analyst actions.
- **Tier 3:** social posts, unconfirmed reports and unusual mention volume.

Tier 1 and Tier 2 may contribute to a trade score. Tier 3 may only elevate a symbol for investigation. Social analysis may measure mention acceleration, unique authors, concentrated/repeated language, sentiment disagreement and independent price/volume confirmation. All access must comply with provider terms.

The UI must distinguish publication time, event time and scanner-receipt time. Old news recirculating on social media cannot qualify as a fresh catalyst.

## 17. Dashboard

### 17.1 Market overview

Show regime, index and sector performance, breadth, volatility, relative volume, upcoming events, current limits and a prominent Paper/Live indicator.

### 17.2 Scanner

Provide ranked and filterable candidates with direction, setup, score, sector alignment, relative volume, VWAP relationship, catalyst, proposed vehicle and detection time.

### 17.3 Trade approval

Show intraday and daily charts, entry, invalidation, targets, option payoff, Greeks, implied volatility, maximum loss, expected reward, exposure, cited news, separated social evidence, event warnings and wash-sale warnings.

### 17.4 Open positions

Show profit/loss in dollars and risk units, remaining risk, stop/target status, Greeks, DTE and one-click close or reduction controls.

### 17.5 Journal and analytics

Store signals, approvals, modifications, rejections, fills, exits, chart snapshots, slippage, fees, rule violations and notes. Segment results by paper/live, direction, shares/options, strategy, regime and catalyst category. Report pre-tax results and estimated taxable gains separately.

Also report after-tax estimated expectancy, assignment events, missed alerts during downtime, rejected orders, data-quality failures and performance against a passive benchmark. The benchmark comparison must use the same dates and cash-flow timing as the strategy.

## 18. Security and Reliability

- Default to paper mode after every install, upgrade, unexpected restart or authentication recovery.
- Require a deliberate session-level live-mode unlock.
- Encrypt or OS-protect stored tokens and secrets.
- Redact account identifiers, tokens and secrets from logs.
- Use least-privilege API scopes where available.
- Protect against duplicate order submission with idempotency keys and broker reconciliation.
- Halt on uncertain order state rather than resubmitting.
- Validate clock synchronization and market-session state.
- Display data timestamps and source health.
- Keep an append-only audit trail for trading decisions and broker responses.
- When hosted on Proxmox, expose the dashboard only through the user's VPN with HTTPS and application authentication.
- Use CSRF protection, secure session cookies, origin checks and automatic session expiry for approval actions.
- Require reauthentication and a fresh live-mode arm after inactivity, token replacement or deployment restart.
- Back up the journal and configuration, test restoration and retain a human-readable export of orders and positions.
- Provide an emergency kill switch that cancels working entry orders, locks new entries and preserves exit access; it must not blindly liquidate positions.

## 19. Error Handling

- **Expired OAuth:** lock live actions and request reauthentication.
- **Stale data:** suppress approval and identify the stale dependency.
- **Partial fill:** reconcile filled quantity, cancel or review the remainder and recalculate risk.
- **Unknown broker response:** query order state; never blindly retry submission.
- **Provider outage:** degrade noncritical news/social scoring but block orders when price, option or account data is unavailable.
- **Database failure:** stop new submissions and preserve the last broker request/response safely.
- **Local shutdown:** reconcile broker orders and positions on restart before enabling live mode.
- **Risk-limit breach:** lock new entries while continuing position monitoring and exit controls.
- **Trading halt/LULD:** cancel or suppress affected entries, freeze repricing and show the halt state.
- **Corporate action:** invalidate cached indicators and option selections until deliverables and price history are reconciled.
- **Clock/calendar fault:** block new orders until authoritative market time and session state are restored.
- **Local connectivity loss:** mark monitoring unavailable and rely only on broker-acknowledged orders; reconcile immediately on recovery.

## 20. Testing and Graduation

### 20.1 Automated testing

- Unit tests for indicators, scoring, Greeks normalization, sizing and regime classification.
- Property and boundary tests for all risk limits.
- Contract tests for broker and data-provider adapters.
- Replay tests using recorded market snapshots.
- Backtests that include delisted symbols and point-in-time index membership where available, with adjusted and unadjusted price series used appropriately to prevent survivorship and look-ahead bias.
- Integration tests against the Schwab sandbox where available.
- Failure-injection tests for stale quotes, expired tokens, partial fills and ambiguous broker responses.
- Assignment, ex-dividend, pin-risk, split, special-dividend, halt and early-close scenarios.
- Cash-account and margin-enabled-account tests for settled funds, buying power and broker house requirements.
- End-to-end tests for scan, approval, refresh, preview, submission, reconciliation and exit.
- Security tests confirming secrets never enter logs or frontend responses.

### 20.2 Paper-trading graduation

Live trading remains locked until all are satisfied:

- At least 100 paper trades.
- At least eight weeks of observation spanning more than one market condition.
- Positive expectancy after estimated spreads, slippage and contract fees.
- Maximum drawdown below 8% of the active sleeve.
- No unresolved critical order or reconciliation defect.
- Documented adherence to risk rules.
- Successful manual drills for early assignment, local/network outage, kill switch and restart reconciliation.

Initial live deployment uses no more than $2,000 of the active sleeve. Scaling requires another documented review; it is not automatic.

### 20.3 Evaluation safeguards

Performance assessment must report sample size, win rate, average win/loss, expectancy, profit factor, maximum drawdown, exposure time, slippage and results by regime. Avoid optimizing thresholds repeatedly on the same historical data. Retain an out-of-sample period and use walk-forward evaluation before changing production rules.

Paper fills must be modeled conservatively from contemporaneous bid/ask data; midpoint fills are not assumed. Simulated results include option fees, regulatory fees, missed fills and realistic latency. Because paperMoney does not reliably reproduce early assignment, explicit assignment simulations are mandatory.

## 21. Daily Workflow

1. Start locally and review data-source health.
2. Review economic events, earnings exclusions and the classified regime.
3. Confirm paper or live mode and all current circuit breakers.
4. Allow the first 15 minutes to establish an opening range.
5. Review only qualified alerts.
6. Approve no more than three new trades.
7. Monitor open positions and respond to exit conditions.
8. After the close, reconcile broker activity, annotate trades and review rule adherence.

## 22. Acceptance Criteria

- The application starts locally through Docker Compose and defaults to paper mode.
- A configured universe can be scanned and each candidate has a reconstructable component score.
- Bullish and bearish rankings respect the classified regime.
- A candidate cannot reach approval-ready status without complete, fresh critical data.
- Every proposed order displays its planned and maximum loss before approval.
- Every option spread displays early-assignment and expiration stress outcomes before approval.
- Approving an order forces fresh validation and a final preview.
- No market, naked, short-share or 0DTE order can be constructed.
- Duplicate clicks or ambiguous responses cannot create duplicate orders.
- All signals and user actions are journaled, including rejected opportunities.
- Daily and weekly circuit breakers prevent new entries while leaving exits available.
- Halts, corporate actions, stale clocks and connectivity loss cannot produce a new live entry.
- A local outage is visible after recovery, and broker positions/orders reconcile before live mode can be rearmed.
- The same application can migrate from SQLite/local deployment to PostgreSQL/Proxmox deployment without changing domain logic or the user interface.

## 23. Future Enhancements

- Premium streaming news and licensed social sentiment.
- Additional brokers through the broker-adapter interface.
- Mobile-friendly approval notifications.
- Portfolio-aware hedging suggestions.
- Tax-lot import and stronger reconciliation with broker reports.
- Additional defined-risk strategies only after separate design, testing and approval.
- Continuous Proxmox operation with VPN-only access and high-availability monitoring.
