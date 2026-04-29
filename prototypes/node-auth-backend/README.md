# Node Auth Backend Prototype

This directory contains the archived Node/Express auth prototype that used to
live under `backend/src`.

It covers:

- public work-email registration
- login and JWT issuing
- password reset
- email verification and setup
- Google OAuth
- a `/health` endpoint
- an in-memory user/token store

It does not cover the GEO monitoring platform, Admin control plane, pipeline
execution, adapters, account pools, knowledge graph governance, or metric
snapshots.

This prototype is retained for reference only. The active backend lives in
`backend/app` and runs on FastAPI.

Historical docs for this prototype are in `docs/` inside this directory.

## Run Locally

```bash
npm install
npm run dev
```

The server starts on port `4000` by default. Data is in-memory and is lost on
process restart.
