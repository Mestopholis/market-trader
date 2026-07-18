from market_trader.market_data.models import (
    CandleInterval,
    DataKind,
    NormalizationResult,
    NormalizedCandle,
    NormalizedCorporateAction,
    NormalizedOptionChain,
    NormalizedProviderState,
    NormalizedQuote,
    ProviderEvent,
    QualityState,
    RejectedObservation,
)
from market_trader.market_data.normalizers import (
    normalize_candle,
    normalize_corporate_action,
    normalize_option_chain,
    normalize_provider_state,
    normalize_quote,
)
from market_trader.market_data.quality import FreshnessPolicy

type NormalizedObservation = (
    NormalizedQuote
    | NormalizedCandle
    | NormalizedOptionChain
    | NormalizedCorporateAction
    | NormalizedProviderState
)


class MarketDataPipeline:
    def __init__(self, *, freshness_policy: FreshnessPolicy) -> None:
        self._freshness_policy = freshness_policy

    def normalize(self, event: ProviderEvent) -> NormalizationResult[NormalizedObservation]:
        result: NormalizationResult[NormalizedObservation]
        if event.data_kind is DataKind.QUOTE:
            result = normalize_quote(event)
        elif event.data_kind is DataKind.CANDLE:
            result = normalize_candle(event)
        elif event.data_kind is DataKind.OPTION_CHAIN:
            result = normalize_option_chain(event)
        elif event.data_kind is DataKind.CORPORATE_ACTION:
            result = normalize_corporate_action(event)
        elif event.data_kind is DataKind.PROVIDER_STATE:
            result = normalize_provider_state(event)
        else:
            return NormalizationResult(
                rejection=self.reject(event, "unsupported_data_kind")
            )
        if result.rejection is not None:
            return result

        value = result.accepted
        assert value is not None
        if isinstance(value, NormalizedProviderState):
            return result
        if isinstance(value, NormalizedCandle) and value.interval is CandleInterval.DAILY:
            session_date = value.metadata.session_date
            if session_date is None:
                return NormalizationResult(rejection=self.reject(event, "missing_session_date"))
            freshness = self._freshness_policy.evaluate_daily_candle(session_date=session_date)
        else:
            candle_end = value.end if isinstance(value, NormalizedCandle) else None
            freshness = self._freshness_policy.evaluate(
                event.data_kind,
                observed_at=event.observed_at,
                ingested_at=event.ingested_at,
                candle_end=candle_end,
            )
        if freshness.blocking:
            return NormalizationResult(
                rejection=self.reject(
                    event,
                    *freshness.reason_codes,
                    quality_state=freshness.state,
                    symbol_identity=self.identity(value),
                )
            )
        return result

    @staticmethod
    def identity(value: NormalizedObservation) -> str:
        if isinstance(value, NormalizedOptionChain):
            return value.underlying
        if isinstance(value, NormalizedProviderState):
            return value.provider
        return value.symbol

    @staticmethod
    def reject(
        event: ProviderEvent,
        *reason_codes: str,
        quality_state: QualityState = QualityState.QUARANTINED,
        symbol_identity: str | None = None,
    ) -> RejectedObservation:
        return RejectedObservation(
            source=event.source,
            event_id=event.event_id,
            data_kind=event.data_kind,
            observed_at=event.observed_at,
            ingested_at=event.ingested_at,
            reason_codes=tuple(reason_codes),
            quality_state=quality_state,
            symbol_identity=symbol_identity,
        )
