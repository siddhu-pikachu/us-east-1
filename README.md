# NMC² Ops Console (MVP)

Streamlit app with three roles and Jira Cloud integration (with Demo Mode).

## Quick start

1) Python 3.11 installed.

2) `cp .env.example .env` and set values. For Jira live mode:

   - Create API token: https://id.atlassian.com/manage/api-tokens

   - Set JIRA_BASE_URL like `https://YOUR_DOMAIN.atlassian.net`

   - Set DEMO_MODE=false

3) `make setup`

4) `make run`  (opens http://localhost:8501)

## Scripts

- `make seed` — generates synthetic data.

- `make fmt` / `make lint` — formatting and linting.

## Docker

- `make docker` or `docker compose up --build`

