# Tests

All fake services (AI, Dify, OpenHands, VTuber, Stripe, Paystack) come from one file:

    python3 tests/mock_services.py        # listens on 9411-9415

## Connectors (port 9420)

    ADMIN_PASSWORD= AI_API_KEY=test-key CONFIG_FILE=/tmp/conn-config.json \
      KNOWLEDGE_DIR=/tmp/kb PORT=9420 HOST=127.0.0.1 USAGE_DB=/tmp/usage-conn.db python3 app.py

`/tmp/conn-config.json`: `"base_url": "http://127.0.0.1:9411/v1"`, `"model": "mock-openai"`,
`"billing": {"enabled": false}`, and engines openhands→9413 (key `oh-secret`), dify→9412/v1
(key `app-good-key`), vtuber→9414, orca→9411/v1 (model `orca-mini`); main/ollama/free/custom2 off.

    python3 tests/test_connectors.py      # 59 checks: health, routing, streaming, keys, endpoints
    python3 tests/test_connector_ui.py    # the same through a real browser (needs playwright)

## Billing / paywall (port 9421)

    CONFIG_FILE=tests/billing-config.json KNOWLEDGE_DIR=/tmp/kb PORT=9421 HOST=127.0.0.1 \
      USAGE_DB=/tmp/usage.db ADMIN_PASSWORD=admin-pw AI_API_KEY=test-key python3 app.py

Start with a **fresh** `USAGE_DB` (delete the file) - `test_billing.py` uses fixed visitor ids.
`tests/billing-config.json` gives 2 free prompts, plan "Test Plus" R49/month, mock gateway
keys and `stripe_base`/`paystack_base` pointed at the mock on 9415.

    python3 tests/test_billing.py         # 56 checks: meter, paywall, EFT approve/reject,
                                          # coupons, Stripe + Paystack webhooks, admin API
    python3 tests/test_billing_ui.py      # paywall, EFT, dashboard and coupons in a real browser
                                          # (runnable repeatedly against the same DB)

## UI smoke (port 9422)

    ADMIN_PASSWORD= AI_API_KEY=test-key CONFIG_FILE=/tmp/smoke-config.json \
      KNOWLEDGE_DIR=/tmp/kb PORT=9422 HOST=127.0.0.1 USAGE_DB=/tmp/usage-smoke.db python3 app.py

(same as the connector config but `billing.enabled: true` with a huge allowance)

    python3 tests/test_ui_smoke.py        # chat, markdown, KaTeX, code buttons, attachments,
                                          # settings round-trip, retry, phone layout

Browser tests need `pip install playwright && python3 -m playwright install chromium-headless-shell`
(and on a fresh sandbox `python3 -m playwright install-deps chromium`).
