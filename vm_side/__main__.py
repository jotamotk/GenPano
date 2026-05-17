"""Entry point: ``python -m vm_side <subcommand>``.

Subcommands:
    runner    Start the FastAPI runner on 127.0.0.1:7000.
    watchdog  Start the login watchdog + Prometheus gauges on :8000.
"""
from __future__ import annotations

import sys


_USAGE = (
    "usage: python -m vm_side <subcommand>\n"
    "\n"
    "subcommands:\n"
    "    runner    Start the FastAPI runner (default 127.0.0.1:7000)\n"
    "    watchdog  Start the login watchdog (Prometheus on :8000, posts to ORCHESTRATOR_URL)\n"
)


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args or args[0] in ("-h", "--help"):
        sys.stdout.write(_USAGE)
        return 0 if args else 2
    sub = args[0]
    if sub == "runner":
        from vm_side.runner import main as runner_main

        runner_main()
        return 0
    if sub == "watchdog":
        from vm_side.login_watchdog import main as wd_main

        wd_main()
        return 0
    sys.stderr.write(f"unknown subcommand: {sub}\n\n{_USAGE}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
