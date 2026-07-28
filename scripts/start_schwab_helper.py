#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode


REPO_ROOT = Path(__file__).resolve().parents[1]
API_SRC = REPO_ROOT / "apps" / "api" / "src"
DATA_DIR = REPO_ROOT / "data"
DEFAULT_DATABASE_URL = "sqlite:///data/market_trader.db"
CERT_FILE = DATA_DIR / "local-certs" / "schwab-helper-127-cert.pem"
KEY_FILE = DATA_DIR / "local-certs" / "schwab-helper-127-key.pem"

os.chdir(REPO_ROOT)
os.environ.setdefault("MARKET_TRADER_DATABASE_URL", DEFAULT_DATABASE_URL)
sys.path.insert(0, str(API_SRC))

from fastapi import Request  # noqa: E402
from fastapi.responses import HTMLResponse, RedirectResponse  # noqa: E402

from market_trader.config import get_settings  # noqa: E402
from market_trader.db.migrations import upgrade_to_head  # noqa: E402
from market_trader.main import create_app  # noqa: E402


app = create_app()


@app.get("/", include_in_schema=False, response_model=None)
def schwab_helper_root(request: Request):
    query = dict(request.query_params)
    if "state" in query or "code" in query or "error" in query:
        product = _product_from_state(query.get("state"))
        target = (
            "/api/broker/schwab/accounts/oauth/callback"
            if product == "accounts_trading"
            else "/api/broker/schwab/oauth/callback"
        )
        if query:
            target = f"{target}?{urlencode(query)}"
        return RedirectResponse(target, status_code=307)

    return HTMLResponse(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Market Trader Schwab Connect</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, -apple-system, sans-serif; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #101418; color: #f5f7fa; }
    main { width: min(560px, calc(100vw - 32px)); border: 1px solid #2c3642; border-radius: 8px; padding: 24px; background: #171d24; }
    h1 { margin: 0 0 16px; font-size: 24px; }
    label { display: grid; gap: 6px; margin: 12px 0; color: #c9d2dc; }
    input { font: inherit; padding: 10px 12px; border-radius: 6px; border: 1px solid #3d4a58; background: #0f141a; color: #fff; }
    button { font: inherit; padding: 10px 14px; border: 0; border-radius: 6px; background: #4f8cff; color: white; cursor: pointer; }
    button:disabled { opacity: .6; cursor: wait; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #0f141a; padding: 12px; border-radius: 6px; color: #dbe6f1; }
  </style>
</head>
<body>
  <main>
    <h1>Schwab Connect</h1>
    <form id="connect-form">
      <label>Product
        <select id="product">
          <option value="market_data">Market Data</option>
          <option value="accounts_trading">Accounts and Trading</option>
        </select>
      </label>
      <label>Local username <input id="username" autocomplete="username" required /></label>
      <label>Local password <input id="password" type="password" autocomplete="current-password" required /></label>
      <button id="connect" type="submit">Connect</button>
    </form>
    <pre id="status">Ready.</pre>
  </main>
  <script>
    const status = document.querySelector('#status')
    const button = document.querySelector('#connect')
    const csrfToken = () => document.cookie
      .split('; ')
      .find((part) => part.startsWith('market_trader_csrf='))
      ?.split('=')
      .slice(1)
      .join('=')

    document.querySelector('#connect-form').addEventListener('submit', async (event) => {
      event.preventDefault()
      button.disabled = true
      status.textContent = 'Logging in locally...'
      try {
        const login = await fetch('/api/auth/login', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({
            username: document.querySelector('#username').value,
            password: document.querySelector('#password').value,
          }),
        })
        if (!login.ok) throw new Error(`Local login failed: HTTP ${login.status}`)

        const csrf = csrfToken()
        if (!csrf) throw new Error('Local login did not set a CSRF cookie.')

        status.textContent = 'Starting Schwab OAuth...'
        const product = document.querySelector('#product').value
        const startPath = product === 'accounts_trading'
          ? '/api/broker/schwab/accounts/oauth/start'
          : '/api/broker/schwab/oauth/start'
        const started = await fetch(startPath, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { Accept: 'application/json', 'X-CSRF-Token': csrf },
        })
        const payload = await started.json()
        if (!started.ok) throw new Error(JSON.stringify(payload))
        window.location.assign(payload.authorization_url)
      } catch (error) {
        status.textContent = String(error)
        button.disabled = false
      }
    })
  </script>
</body>
</html>
        """
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the local Schwab OAuth helper.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8182, type=int)
    parser.add_argument("--check", action="store_true", help="Validate setup without starting uvicorn.")
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    _ensure_certificate()
    upgrade_to_head(get_settings().database_url)

    if args.check:
        print("schwab_helper_ok")
        return

    import uvicorn

    print(f"Open https://{args.host}:{args.port}/")
    uvicorn.run(
        "start_schwab_helper:app",
        app_dir=str(REPO_ROOT / "scripts"),
        host=args.host,
        port=args.port,
        ssl_keyfile=str(KEY_FILE),
        ssl_certfile=str(CERT_FILE),
    )


def _ensure_certificate() -> None:
    if CERT_FILE.is_file() and KEY_FILE.is_file():
        return
    CERT_FILE.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(KEY_FILE),
            "-out",
            str(CERT_FILE),
            "-days",
            "30",
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
        ],
        check=True,
    )


def _product_from_state(state: str | None) -> str:
    if not state:
        return "market_data"
    encoded = state.split(".", maxsplit=1)[0]
    try:
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode((encoded + padding).encode("ascii")))
    except (ValueError, json.JSONDecodeError):
        return "market_data"
    product = payload.get("product")
    return str(product) if product is not None else "market_data"


if __name__ == "__main__":
    main()
