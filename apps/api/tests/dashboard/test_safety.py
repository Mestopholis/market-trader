from pathlib import Path

from fastapi.testclient import TestClient

from market_trader.main import app

DASHBOARD_PATHS = (
    "/api/dashboard/overview",
    "/api/dashboard/candidates",
    "/api/dashboard/candidates/candidate:aapl",
    "/api/dashboard/risk",
    "/api/dashboard/journal",
    "/api/dashboard/analytics",
)

FORBIDDEN_TERMS = (
    "approval",
    "approve",
    "preview",
    "submit",
    "buy",
    "sell",
    "execute",
    "broker",
    "live_mode",
    "order_payload",
    "credential",
    "token",
    "secret",
)


def test_dashboard_routes_expose_no_write_methods() -> None:
    methods_by_path = {
        path: set(route.keys())
        for path, route in TestClient(app).get("/api/openapi.json").json()["paths"].items()
        if path.startswith("/api/dashboard")
    }

    assert methods_by_path
    for methods in methods_by_path.values():
        assert methods == {"get"}


def test_dashboard_openapi_contract_has_no_forbidden_action_fields() -> None:
    dashboard_paths = {
        path: route
        for path, route in TestClient(app).get("/api/openapi.json").json()["paths"].items()
        if path.startswith("/api/dashboard")
    }
    payload = str(dashboard_paths).lower()

    for term in FORBIDDEN_TERMS:
        assert term not in payload


def test_dashboard_write_requests_are_rejected() -> None:
    client = TestClient(app)

    for path in DASHBOARD_PATHS:
        for method in (client.post, client.put, client.patch, client.delete):
            assert method(path).status_code in {404, 405}


def test_foundation_smoke_checks_dashboard_overview() -> None:
    script = Path("../../scripts/verify-foundation.sh").read_text()

    assert "/api/dashboard/overview" in script
    assert "paper_mode" in script
