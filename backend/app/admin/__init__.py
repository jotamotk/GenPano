"""GenPano admin domain (Phase R.4 — Flask → FastAPI migration target).

This package houses the admin operator-only routes + shared service code.
Migration plan (ADR-001) lives in `docs/ADR/001-admin-flask-to-fastapi.md`.

Per ADR-014, every admin write route must use `@audit(action, severity)`.
"""
