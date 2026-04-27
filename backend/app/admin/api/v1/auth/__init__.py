"""Admin auth API endpoints — Session A0' Step 5.

Six handlers under POST /admin/api/v1/auth/:
- login           — rate-limited credential check + audit row + cookie set
- refresh         — opaque refresh-cookie rotation (revoke old + issue new)
- logout          — revoke session + clear both cookies
- forgot_password — issue password-reset token + send Resend email
- reset_password  — consume reset token + set new password + revoke siblings
- change_password — re-auth gate + update password + revoke other sessions

The handlers wire together every primitive built in Steps 2-4 (constants /
JWT / refresh_token / password / cookies / reauth_gate / rate_limiter /
middleware / session_repo / audit / email). They live in a single APIRouter
exported as `router` so `app/main.py` can mount once.
"""

from app.admin.api.v1.auth.router import router

__all__ = ["router"]
