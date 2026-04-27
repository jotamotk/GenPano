"""GENPANO L1 Harness rule scan (Python era).

Translates 5 rules from the TypeScript era ci-check.mjs into native Python
AST/regex scanners:

  - F1  no-bare-playwright-import         (origin: CLAUDE.md #22.F)
  - F4  response_source stamping (3 sub)  (origin: CLAUDE.md #28.G C2)
       F4-1  adapter execute() return dict must include `response_source`
       F4-2  api_fallback path return dict must stamp 'api_fallback'
       F4-3  AiResponse(...) constructor must include explicit kwarg
  - D8  no-hardcoded-jwt-secret           (origin: CLAUDE.md #24.F)
  - D9  admin-password-bcrypt-cost ≥ 12   (origin: CLAUDE.md #24.F)
  - D10 admin-cookie-samesite=strict      (origin: CLAUDE.md #24.F)

Self-seeded fixtures live under backend/app/__ci_fixtures__/ and are excluded
from the default scan (only the selftest opts them in).

Per CLAUDE.md #29 (Python pivot), the TS .mjs registry is retired; the rule
*ideas* survive, the implementation is rewritten.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Violation:
    rule_id: str
    file_path: Path
    line: int
    message: str

    def render(self, root: Path) -> str:
        try:
            rel = self.file_path.relative_to(root)
        except ValueError:
            rel = self.file_path
        return f"[{self.rule_id}] {rel.as_posix()}:{self.line}: {self.message}"


DEFAULT_INCLUDE = ["app"]
DEFAULT_EXCLUDE_DIR_NAMES = {"__ci_fixtures__", "__pycache__", ".venv", "node_modules"}


def iter_python_files(
    root: Path,
    include_subdirs: list[str],
    *,
    include_fixtures: bool = False,
) -> list[Path]:
    out: list[Path] = []
    for sub in include_subdirs:
        base = root / sub
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            parts = set(path.parts)
            if not include_fixtures and "__ci_fixtures__" in parts:
                continue
            if parts & (DEFAULT_EXCLUDE_DIR_NAMES - {"__ci_fixtures__"}):
                continue
            out.append(path)
    return sorted(out)


_SENTINEL_MISSING = object()
_SENTINEL_NON_CONST = object()


def _dict_has_key(node: ast.Dict, key_name: str) -> bool:
    for k in node.keys:
        if isinstance(k, ast.Constant) and k.value == key_name:
            return True
    return False


def _dict_const_value(node: ast.Dict, key_name: str) -> object:
    for k, v in zip(node.keys, node.values, strict=True):
        if isinstance(k, ast.Constant) and k.value == key_name:
            if isinstance(v, ast.Constant):
                return v.value
            return _SENTINEL_NON_CONST
    return _SENTINEL_MISSING


class F1NoBarePlaywrightImport:
    id = "F1"
    description = "Bare playwright import not allowed in app/ (Camoufox wrapper lands later)"

    _PATTERN = re.compile(
        r"^\s*(?:from\s+playwright(?:\.\w+)*\s+import|import\s+playwright(?:\.\w+)*)\b"
    )

    def scan(self, files: list[Path]) -> list[Violation]:
        out: list[Violation] = []
        for path in files:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(lines, start=1):
                if self._PATTERN.match(line):
                    out.append(
                        Violation(
                            self.id,
                            path,
                            i,
                            "bare playwright import; route through the Camoufox wrapper instead",
                        )
                    )
        return out


class F4_1AdapterExecuteResponseSourceStamp:
    id = "F4-1"
    description = "Adapter execute() return dict literals must include `response_source`"

    def scan(self, files: list[Path]) -> list[Violation]:
        out: list[Violation] = []
        for path in files:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for fn in ast.walk(tree):
                if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if fn.name != "execute":
                    continue
                for ret in ast.walk(fn):
                    if not isinstance(ret, ast.Return):
                        continue
                    if not isinstance(ret.value, ast.Dict):
                        continue
                    if not _dict_has_key(ret.value, "response_source"):
                        out.append(
                            Violation(
                                self.id,
                                path,
                                ret.lineno,
                                f"`{fn.name}()` returns dict literal without `response_source` key",
                            )
                        )
        return out


class F4_2ApiFallbackResponseSourceLabel:
    id = "F4-2"
    description = "api_fallback path return dict must stamp `response_source: 'api_fallback'`"

    def scan(self, files: list[Path]) -> list[Violation]:
        out: list[Violation] = []
        for path in files:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for fn in ast.walk(tree):
                if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if "api_fallback" not in fn.name:
                    continue
                for ret in ast.walk(fn):
                    if not isinstance(ret, ast.Return):
                        continue
                    if not isinstance(ret.value, ast.Dict):
                        continue
                    val = _dict_const_value(ret.value, "response_source")
                    if val is _SENTINEL_MISSING:
                        out.append(
                            Violation(
                                self.id,
                                path,
                                ret.lineno,
                                f"`{fn.name}()` missing `response_source` key",
                            )
                        )
                    elif val is _SENTINEL_NON_CONST:
                        out.append(
                            Violation(
                                self.id,
                                path,
                                ret.lineno,
                                f"`{fn.name}()` `response_source` is not a string literal",
                            )
                        )
                    elif val != "api_fallback":
                        out.append(
                            Violation(
                                self.id,
                                path,
                                ret.lineno,
                                f"`{fn.name}()` `response_source={val!r}` should be 'api_fallback'",
                            )
                        )
        return out


class F4_3AiResponseInsertExplicitKwarg:
    id = "F4-3"
    description = "AiResponse(...) constructor must include explicit `response_source=` kwarg"

    def scan(self, files: list[Path]) -> list[Violation]:
        out: list[Violation] = []
        for path in files:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for call in ast.walk(tree):
                if not isinstance(call, ast.Call):
                    continue
                func_name: str | None = None
                if isinstance(call.func, ast.Name):
                    func_name = call.func.id
                elif isinstance(call.func, ast.Attribute):
                    func_name = call.func.attr
                if func_name != "AiResponse":
                    continue
                kw_names = {kw.arg for kw in call.keywords if kw.arg is not None}
                if "response_source" not in kw_names:
                    out.append(
                        Violation(
                            self.id,
                            path,
                            call.lineno,
                            "AiResponse(...) call missing explicit `response_source=` kwarg",
                        )
                    )
        return out


class D8NoHardcodedJwtSecret:
    id = "D8"
    description = "JWT/SECRET assignment must come from env/settings, not a string literal"

    _TARGET_NAMES = frozenset({"JWT_SECRET", "SECRET_KEY", "ADMIN_JWT_SECRET"})

    def scan(self, files: list[Path]) -> list[Violation]:
        out: list[Violation] = []
        for path in files:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if not isinstance(target, ast.Name):
                        continue
                    if target.id not in self._TARGET_NAMES:
                        continue
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        out.append(
                            Violation(
                                self.id,
                                path,
                                node.lineno,
                                f"`{target.id}` assigned a string literal; use env/settings",
                            )
                        )
        return out


class D9BcryptCostAtLeast12:
    """`bcrypt.gensalt(rounds=N)` literal must have N ≥ 12.

    Walks call-sites for `bcrypt.gensalt(...)`/`gensalt(...)` and inspects
    the `rounds=` kwarg. A constant int < 12 is the violation. Non-literals
    (e.g. `rounds=BCRYPT_COST`) are allowed — those route through the
    constants module which is the single canonical source. Files under
    `app/admin/auth/password.py` are NOT whitelisted: they MUST use
    `BCRYPT_COST` (the constant), not a literal — so they pass naturally
    without a special-case here.
    """

    id = "D9"
    description = "bcrypt cost factor must be ≥ 12 (or routed through BCRYPT_COST)"

    def scan(self, files: list[Path]) -> list[Violation]:
        out: list[Violation] = []
        for path in files:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for call in ast.walk(tree):
                if not isinstance(call, ast.Call):
                    continue
                func_name: str | None = None
                if isinstance(call.func, ast.Name):
                    func_name = call.func.id
                elif isinstance(call.func, ast.Attribute):
                    func_name = call.func.attr
                if func_name != "gensalt":
                    continue
                for kw in call.keywords:
                    if kw.arg != "rounds":
                        continue
                    if (
                        isinstance(kw.value, ast.Constant)
                        and isinstance(kw.value.value, int)
                        and kw.value.value < 12
                    ):
                        out.append(
                            Violation(
                                self.id,
                                path,
                                call.lineno,
                                f"bcrypt.gensalt(rounds={kw.value.value}) "
                                f"violates BCRYPT_COST ≥ 12 floor",
                            )
                        )
        return out


class D10CookieSameSiteStrict:
    """`samesite=` kwarg must be the literal 'strict' (case-insensitive).

    Walks calls (e.g. `response.set_cookie(..., samesite='lax')`) and any
    plain assignment whose target name contains 'samesite' / 'same_site'
    bound to a string literal != 'strict'. Catches both Starlette's API
    surface and hand-rolled Set-Cookie strings that bind a SameSite value
    to a top-level constant.
    """

    id = "D10"
    description = "admin auth cookies must use SameSite=Strict (no 'lax' / 'none')"

    _SAMESITE_NAMES = ("samesite", "same_site")

    def _bad_const(self, value: ast.AST) -> str | None:
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            return None
        if value.value.lower() != "strict":
            return value.value
        return None

    def scan(self, files: list[Path]) -> list[Violation]:
        out: list[Violation] = []
        for path in files:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    for kw in node.keywords:
                        if kw.arg is None:
                            continue
                        if kw.arg.lower() not in self._SAMESITE_NAMES:
                            continue
                        bad = self._bad_const(kw.value)
                        if bad is not None:
                            out.append(
                                Violation(
                                    self.id,
                                    path,
                                    node.lineno,
                                    f"samesite={bad!r} — must be 'strict'",
                                )
                            )
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if not isinstance(target, ast.Name):
                            continue
                        lower = target.id.lower()
                        if not any(token in lower for token in self._SAMESITE_NAMES):
                            continue
                        bad = self._bad_const(node.value)
                        if bad is not None:
                            out.append(
                                Violation(
                                    self.id,
                                    path,
                                    node.lineno,
                                    f"`{target.id} = {bad!r}` — SameSite must be 'strict'",
                                )
                            )
        return out


ALL_RULES: list[object] = [
    F1NoBarePlaywrightImport(),
    F4_1AdapterExecuteResponseSourceStamp(),
    F4_2ApiFallbackResponseSourceLabel(),
    F4_3AiResponseInsertExplicitKwarg(),
    D8NoHardcodedJwtSecret(),
    D9BcryptCostAtLeast12(),
    D10CookieSameSiteStrict(),
]


def _select_rules(spec: str | None) -> list[object]:
    if not spec:
        return ALL_RULES
    wanted = {s.strip() for s in spec.split(",") if s.strip()}
    available = {r.id for r in ALL_RULES}  # type: ignore[attr-defined]
    missing = wanted - available
    if missing:
        raise SystemExit(f"unknown rule ids: {sorted(missing)}; available: {sorted(available)}")
    return [r for r in ALL_RULES if r.id in wanted]  # type: ignore[attr-defined]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GENPANO L1 Harness rule scan")
    parser.add_argument("--rules", help="Comma-separated rule IDs (default: all rules)")
    parser.add_argument(
        "--include-fixtures",
        action="store_true",
        help="Also scan __ci_fixtures__/ (selftest only; never use in CI main lane)",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Backend root (default: current working directory)",
    )
    args = parser.parse_args(argv)

    rules = _select_rules(args.rules)
    root = Path(args.root).resolve()
    files = iter_python_files(root, DEFAULT_INCLUDE, include_fixtures=args.include_fixtures)

    all_violations: list[Violation] = []
    for rule in rules:
        all_violations.extend(rule.scan(files))  # type: ignore[attr-defined]

    for v in all_violations:
        print(v.render(root))

    rule_ids = [r.id for r in rules]  # type: ignore[attr-defined]
    if all_violations:
        unique_rule_count = len({v.rule_id for v in all_violations})
        print(
            f"\n● ci_check: FAIL ({len(all_violations)} violation(s) "
            f"across {unique_rule_count} rule(s))"
        )
        return 1
    print(
        f"● ci_check: PASS (0 violations across {len(rule_ids)} rule(s) "
        f"on {len(files)} file(s); rules={rule_ids})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
