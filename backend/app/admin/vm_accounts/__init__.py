"""Admin vm_session sub-domain (Issue #1116 / Epic #1110).

Service-layer helpers for ``llm_accounts`` rows running in
``execution_mode = 'vm_session'`` (introduced by Issue #1114 schema
migration ``20260517_exec_mode``). Routes live in
``app/api/admin/vm_accounts/router.py``; raw-SQL DB helpers live in
``db.py``; Slack webhook fan-out lives in ``slack.py``.

R2.5 prevention (defense-in-depth):

- DB layer: CHECK ``chk_exec_mode_cookies`` rejects any vm_session row
  carrying ``cookies_json`` (Phase 1 migration).
- Backend layer (here): reject vm_session create/toggle payloads that
  include cookies_json before they ever touch the DB.
- Frontend layer (admin.html): disable the cookies input when the
  engine selector is set to vm_session.

Only the three MVP engines (chatgpt / doubao / deepseek-CN) are
permitted per ``docs/ADAPTER_CONTRACT.md`` §1.1 Decision #28.C1.
"""
