from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, timedelta

from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_data.models import (
    AdjustmentState,
    NormalizedCandle,
    NormalizedCorporateAction,
    NormalizedProviderState,
    NormalizedQuote,
)
from market_trader.scanner.configuration import ScannerConfiguration, UniverseEntry
from market_trader.scanner.eligibility import EligibilityEvaluator, EligibilityQuality
from market_trader.scanner.evidence import SupplementalEvidence
from market_trader.scanner.features import (
    FeatureCalculator,
    FeatureResult,
    assign_relative_performance_percentiles,
)
from market_trader.scanner.models import (
    EligibilityStatus,
    ScanCounts,
    ScannerInput,
    ScanResult,
    StrategyResult,
    SymbolInput,
)
from market_trader.scanner.regime import RegimeClassifier
from market_trader.scanner.scoring import CandidateScorer, CandidateSelector
from market_trader.scanner.serialization import stable_digest
from market_trader.scanner.strategies import (
    BearishBreakdownEvaluator,
    BearishFailedRallyEvaluator,
    BullishBreakoutEvaluator,
    BullishPullbackEvaluator,
    NewsContinuationEvaluator,
    StrategyEvaluator,
)


class ScannerEngine:
    def __init__(self, configuration: ScannerConfiguration) -> None:
        self._configuration = configuration
        self._features = FeatureCalculator()
        self._eligibility = EligibilityEvaluator(configuration.eligibility)
        self._regime = RegimeClassifier(configuration.regime)
        self._scorer = CandidateScorer(configuration.scoring)
        self._selector = CandidateSelector(configuration.scoring)
        evaluators: tuple[StrategyEvaluator, ...] = (
            BullishBreakoutEvaluator(configuration.strategies),
            BullishPullbackEvaluator(configuration.strategies),
            BearishBreakdownEvaluator(configuration.strategies),
            BearishFailedRallyEvaluator(configuration.strategies),
            NewsContinuationEvaluator(configuration.strategies),
        )
        self._evaluators = {evaluator.strategy_id: evaluator for evaluator in evaluators}

    def scan(self, scanner_input: ScannerInput) -> ScanResult:
        self._validate_configuration(scanner_input)
        effective = _effective_input(scanner_input)
        evidence = effective.supplemental_evidence or _empty_evidence(effective)
        session = XNYSCalendarAdapter(
            start=effective.session_date - timedelta(days=7),
            end=effective.session_date + timedelta(days=1),
        ).session(effective.session_date)
        grouped: dict[str, list[SymbolInput]] = defaultdict(list)
        for symbol in effective.symbols:
            grouped[symbol.symbol].append(symbol)

        members = tuple(
            sorted(
                self._configuration.universe.entries,
                key=lambda member: member.display_symbol,
            )
        )
        symbol_inputs: dict[str, SymbolInput | None] = {}
        raw_features: list[FeatureResult] = []
        for member in members:
            matches = grouped.get(member.display_symbol, [])
            symbol_input = matches[0] if len(matches) == 1 else None
            symbol_inputs[member.display_symbol] = symbol_input
            raw_features.append(
                self._features.calculate(
                    symbol_input or SymbolInput(symbol=member.display_symbol),
                    as_of=effective.as_of,
                    session=session,
                )
            )
        features = assign_relative_performance_percentiles(raw_features)
        features_by_symbol = {item.symbol: item for item in features}
        regime = self._regime.classify(features, evidence)

        eligibility = tuple(
            self._eligibility.evaluate(
                member,
                features_by_symbol[member.display_symbol],
                _quality(
                    member,
                    symbol_inputs[member.display_symbol],
                    duplicate=len(grouped.get(member.display_symbol, [])) > 1,
                    session_date=effective.session_date,
                ),
            )
            for member in members
        )
        input_digest = stable_digest(effective)
        run_key = _run_key(effective, input_digest)
        strategies: list[StrategyResult] = []
        candidates = []
        for decision in eligibility:
            if decision.status is not EligibilityStatus.ELIGIBLE:
                continue
            symbol_input = symbol_inputs[decision.symbol]
            if symbol_input is None:
                continue
            feature = features_by_symbol[decision.symbol]
            references = symbol_input.evidence
            primary_ingestion_key = references[0].ingestion_key if references else None
            for rule in self._configuration.strategies.rules:
                evaluator = self._evaluators[rule.strategy_id]
                evaluated = evaluator.evaluate(feature, regime, evidence)
                identified = replace(
                    evaluated,
                    signal_key=(
                        f"{run_key}:{decision.symbol}:{rule.strategy_id}:"
                        f"{self._configuration.strategies.version}"
                    ),
                    input_references=references,
                    primary_ingestion_key=primary_ingestion_key,
                    input_digest=input_digest,
                )
                scored = self._scorer.score(identified, feature, regime)
                strategies.append(scored)
                candidate = self._selector.select(decision, scored)
                if candidate is not None:
                    candidates.append(candidate)

        counts = ScanCounts(
            eligible=sum(item.status is EligibilityStatus.ELIGIBLE for item in eligibility),
            ineligible=sum(item.status is EligibilityStatus.INELIGIBLE for item in eligibility),
            blocked=sum(item.status is EligibilityStatus.BLOCKED for item in eligibility),
            signals=len(strategies),
            candidates=len(candidates),
        )
        result_digest = stable_digest(
            {
                "run_key": run_key,
                "input_digest": input_digest,
                "regime": regime,
                "eligibility": eligibility,
                "strategies": tuple(strategies),
                "candidates": tuple(candidates),
                "counts": counts,
            }
        )
        return ScanResult(
            run_key=run_key,
            as_of=effective.as_of,
            session_date=effective.session_date,
            versions=effective.versions,
            input_digest=input_digest,
            regime=regime,
            eligibility=eligibility,
            strategies=tuple(strategies),
            candidates=tuple(candidates),
            counts=counts,
            result_digest=result_digest,
            configuration_hashes=effective.configuration_hashes,
        )

    def _validate_configuration(self, scanner_input: ScannerInput) -> None:
        if scanner_input.versions != self._configuration.versions:
            raise ValueError("scanner input versions do not match configuration")
        if dict(scanner_input.configuration_hashes) != dict(self._configuration.content_hashes):
            raise ValueError("scanner input hashes do not match configuration")
        evidence = scanner_input.supplemental_evidence
        if evidence is not None and evidence.as_of != scanner_input.as_of:
            raise ValueError("supplemental evidence as_of does not match scanner input")


def _effective_input(scanner_input: ScannerInput) -> ScannerInput:
    reference = scanner_input.as_of
    symbols = tuple(
        replace(
            symbol,
            daily_candles=tuple(
                candle
                for candle in symbol.daily_candles
                if _market_record_current(candle, reference) and candle.end <= reference
            ),
            intraday_candles=tuple(
                candle
                for candle in symbol.intraday_candles
                if _market_record_current(candle, reference) and candle.end <= reference
            ),
            quotes=tuple(
                quote for quote in symbol.quotes if _market_record_current(quote, reference)
            ),
            provider_states=tuple(
                state
                for state in symbol.provider_states
                if _market_record_current(state, reference)
            ),
            corporate_actions=tuple(
                action
                for action in symbol.corporate_actions
                if _market_record_current(action, reference)
            ),
            evidence=tuple(
                item
                for item in symbol.evidence
                if item.observed_at <= reference and item.ingested_at <= reference
            ),
        )
        for symbol in scanner_input.symbols
    )
    supplemental = scanner_input.supplemental_evidence
    if supplemental is not None:
        supplemental = SupplementalEvidence(
            as_of=supplemental.as_of,
            breadth=tuple(item for item in supplemental.breadth if item.observed_at <= reference),
            sector=tuple(item for item in supplemental.sector if item.observed_at <= reference),
            volatility=tuple(
                item for item in supplemental.volatility if item.observed_at <= reference
            ),
            macro=tuple(item for item in supplemental.macro if item.observed_at <= reference),
            catalysts=tuple(
                item
                for item in supplemental.catalysts
                if item.observed_at <= reference and item.published_at <= reference
            ),
        )
    return replace(scanner_input, symbols=symbols, supplemental_evidence=supplemental)


def _market_record_current(
    record: NormalizedCandle
    | NormalizedQuote
    | NormalizedProviderState
    | NormalizedCorporateAction,
    reference: datetime,
) -> bool:
    return record.metadata.observed_at <= reference and record.metadata.ingested_at <= reference


def _quality(
    member: UniverseEntry,
    symbol: SymbolInput | None,
    *,
    duplicate: bool,
    session_date: date,
) -> EligibilityQuality:
    if symbol is None:
        return EligibilityQuality(
            repository_symbol=None,
            symbol_active=None,
            daily_quality_state=None,
            provider_state=None,
            halted=None,
            quote_updating=None,
            adjustment_supported=None,
            corporate_actions_resolved=None,
            conflicting_input=duplicate,
        )
    latest_daily = symbol.daily_candles[-1] if symbol.daily_candles else None
    latest_provider = symbol.provider_states[-1] if symbol.provider_states else None
    active = _attribute_bool(symbol, "symbol_active")
    if active is None:
        active = member.active_from <= session_date and (
            member.active_to is None or session_date <= member.active_to
        )
    adjustment_supported = _attribute_bool(symbol, "adjustment_supported")
    if adjustment_supported is None and symbol.daily_candles:
        adjustment_supported = all(
            candle.adjustment is AdjustmentState.ADJUSTED
            for candle in (*symbol.daily_candles, *symbol.intraday_candles)
        )
    corporate_actions_resolved = _attribute_bool(symbol, "corporate_actions_resolved")
    if corporate_actions_resolved is None:
        corporate_actions_resolved = not symbol.corporate_actions
    return EligibilityQuality(
        repository_symbol=symbol.symbol,
        symbol_active=active,
        daily_quality_state=(
            latest_daily.metadata.quality_state if latest_daily is not None else None
        ),
        provider_state=(latest_provider.state if latest_provider is not None else None),
        halted=_attribute_bool(symbol, "halted"),
        quote_updating=_attribute_bool(symbol, "quote_updating"),
        adjustment_supported=adjustment_supported,
        corporate_actions_resolved=corporate_actions_resolved,
        conflicting_input=duplicate,
    )


def _attribute_bool(symbol: SymbolInput, name: str) -> bool | None:
    value = symbol.attributes.get(name)
    return value if isinstance(value, bool) else None


def _empty_evidence(scanner_input: ScannerInput) -> SupplementalEvidence:
    return SupplementalEvidence(
        as_of=scanner_input.as_of,
        breadth=(),
        sector=(),
        volatility=(),
        macro=(),
        catalysts=(),
    )


def _run_key(scanner_input: ScannerInput, input_digest: str) -> str:
    versions = scanner_input.versions
    identity_digest = stable_digest(
        {
            "as_of": scanner_input.as_of,
            "session_date": scanner_input.session_date,
            "versions": versions,
            "universe_hash": scanner_input.configuration_hashes.get("universe"),
            "input_digest": input_digest,
        }
    )
    return (
        f"scan:{versions.universe}:{versions.eligibility}:{versions.features}:"
        f"{versions.regime}:{versions.strategies}:{versions.scoring}:"
        f"{versions.evidence}:{identity_digest}"
    )
