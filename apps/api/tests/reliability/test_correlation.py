from market_trader.observability.correlation import (
    CORRELATION_ID_HEADER,
    REQUEST_ID_HEADER,
    CorrelationContext,
    correlation_response_headers,
    new_request_id,
    resolve_correlation_context,
)


def test_generates_distinct_request_ids_with_expected_prefix() -> None:
    first = new_request_id()
    second = new_request_id()

    assert first.startswith("req_")
    assert second.startswith("req_")
    assert first != second
    assert len(first) <= 64


def test_uses_valid_inbound_correlation_id_and_new_request_id() -> None:
    context = resolve_correlation_context({CORRELATION_ID_HEADER: "corr-paper-123"})

    assert context.correlation_id == "corr-paper-123"
    assert context.request_id.startswith("req_")


def test_rejects_invalid_inbound_correlation_id_shape() -> None:
    context = resolve_correlation_context({CORRELATION_ID_HEADER: "corr with spaces and /slashes"})

    assert context.correlation_id.startswith("corr_")
    assert " " not in context.correlation_id
    assert "/" not in context.correlation_id


def test_response_headers_expose_request_and_correlation_ids() -> None:
    context = CorrelationContext(request_id="req_test", correlation_id="corr_test")

    assert correlation_response_headers(context) == {
        REQUEST_ID_HEADER: "req_test",
        CORRELATION_ID_HEADER: "corr_test",
    }
