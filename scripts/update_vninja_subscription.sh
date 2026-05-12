#!/usr/bin/env bash
# Check or update the host-level V-Ninja subscription used by scraper workers.
#
# Usage:
#   bash scripts/update_vninja_subscription.sh check
#   bash scripts/update_vninja_subscription.sh update /path/to/subscription-url.txt
#
# The subscription URL is read from a file so GitHub Actions can pass it through
# a secret file without committing or logging the URL.

set -Eeuo pipefail

MODE="${1:-check}"
SUB_URL_FILE="${2:-}"
VNINJA_API_SECRET="${VNINJA_API_SECRET:-set-your-secret}"
VNINJA_DATA_DIR="${VNINJA_DATA_DIR:-}"

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

find_vninja_dir() {
  if [ -n "${VNINJA_DATA_DIR}" ] && as_root test -f "${VNINJA_DATA_DIR}/profiles.yaml"; then
    printf '%s\n' "${VNINJA_DATA_DIR}"
    return 0
  fi

  local candidate
  for candidate in \
    /root/.local/share/io.github.clash-verge-ninja.clash-verge-ninja \
    /home/*/.local/share/io.github.clash-verge-ninja.clash-verge-ninja
  do
    if as_root test -f "${candidate}/profiles.yaml"; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  return 1
}

wait_for_vninja_api() {
  local i
  for i in $(seq 1 40); do
    if curl -fsS --max-time 3 \
      -H "Authorization: Bearer ${VNINJA_API_SECRET}" \
      http://127.0.0.1:9097/configs >/dev/null 2>&1; then
      return 0
    fi
    sleep 3
  done
  return 1
}

print_profiles_summary() {
  local profiles_yaml="$1"
  as_root python3 - "${profiles_yaml}" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8", errors="replace")

def redact_url(value: str) -> str:
    value = value.strip().strip('"').strip("'")
    if not value:
        return ""
    if len(value) <= 18:
        return "[redacted]"
    return f"{value[:14]}...[redacted]...{value[-6:]}"

print("profiles_yaml=" + str(path))
for line in text.splitlines():
    if re.match(r"^\s*(current|uid|type|name|file|updated):", line) or re.match(r"^\s*-\s+uid:", line):
        print(line)
    elif re.match(r"^\s*url:", line):
        indent = re.match(r"^(\s*)", line).group(1)
        _, value = line.split(":", 1)
        print(f"{indent}url: {redact_url(value)}")
PY
}

print_proxy_summary() {
  echo "=== V-Ninja service and ports ==="
  systemctl is-active vninja || true
  systemctl status --no-pager -l vninja | sed -n '1,18p' || true
  ss -ltnp | grep -E ':(6789|9097|9098)\b' || true

  echo "=== V-Ninja API proxy summary ==="
  local api_json
  api_json="$(mktemp)"
  if curl -fsS --max-time 10 \
    -H "Authorization: Bearer ${VNINJA_API_SECRET}" \
    http://127.0.0.1:9097/proxies > "${api_json}"; then
    python3 - "${api_json}" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
proxies = data.get("proxies", {})
leaf_count = 0
group_count = 0
for name, info in proxies.items():
    members = info.get("all") or []
    if members:
        group_count += 1
        now = info.get("now", "")
        print(f"group={name} type={info.get('type')} now={now} members={len(members)}")
    else:
        leaf_count += 1
print(f"proxy_groups={group_count} leaf_proxies={leaf_count}")
PY
  else
    echo "proxy_api_unavailable"
  fi
  rm -f "${api_json}"

  echo "=== Optional provider refresh ==="
  local providers_json
  providers_json="$(mktemp)"
  if curl -fsS --max-time 10 \
    -H "Authorization: Bearer ${VNINJA_API_SECRET}" \
    http://127.0.0.1:9097/providers/proxies > "${providers_json}"; then
    python3 - "${providers_json}" <<'PY' | while IFS= read -r provider_name; do
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for name in sorted(data.get("providers", {})):
    if name != "default":
        print(name)
PY
      [ -n "${provider_name}" ] || continue
      status="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 -X PUT \
        -H "Authorization: Bearer ${VNINJA_API_SECRET}" \
        "http://127.0.0.1:9097/providers/proxies/${provider_name}" || true)"
      echo "provider_refresh=${provider_name} http_code=${status}"
    done
  else
    echo "provider_api_unavailable"
  fi
  rm -f "${providers_json}"

  echo "=== Connectivity checks ==="
  curl -fsS --max-time 12 --proxy http://127.0.0.1:6789 \
    https://www.gstatic.com/generate_204 \
    -o /dev/null \
    -w 'proxy_generate_204_http_code=%{http_code} total=%{time_total}\n' || true
  curl -sS --max-time 25 --proxy http://127.0.0.1:6789 \
    https://chatgpt.com/ \
    -o /dev/null \
    -w 'chatgpt_http_code=%{http_code} ssl_verify=%{ssl_verify_result} remote_ip=%{remote_ip} total=%{time_total}\n' || true

  if [ -d /opt/genpano ]; then
    cd /opt/genpano
    docker compose exec -T worker python - <<'PY' || true
import os
import socket

print("worker_CLASH_PROXY_URL=" + str(os.getenv("CLASH_PROXY_URL")))
print("worker_CLASH_API_URL=" + str(os.getenv("CLASH_API_URL")))
for host, port in [("host.docker.internal", 6789), ("host.docker.internal", 9098)]:
    try:
        with socket.create_connection((host, port), timeout=5):
            print(f"worker_socket_ok {host}:{port}")
    except Exception as exc:
        print(f"worker_socket_fail {host}:{port} {type(exc).__name__}: {exc}")
PY
  fi
}

update_profiles_yaml_and_file() {
  local profiles_yaml="$1"
  local sub_url_file="$2"
  local downloaded_sub="$3"
  local write_profile_payload="$4"
  local run_id="${GITHUB_RUN_ID:-manual}"

  as_root cp "${profiles_yaml}" "${profiles_yaml}.bak.${run_id}"
  as_root python3 - "${profiles_yaml}" "${sub_url_file}" "${downloaded_sub}" "${write_profile_payload}" "${run_id}" <<'PY'
import json
import re
import shutil
import sys
from pathlib import Path

profiles_path = Path(sys.argv[1])
url_path = Path(sys.argv[2])
downloaded_path = Path(sys.argv[3])
write_profile_payload = sys.argv[4] == "true"
run_id = sys.argv[5]

new_url = url_path.read_text(encoding="utf-8").strip()
if not re.match(r"^https?://", new_url):
    raise SystemExit("subscription URL must start with http:// or https://")

text = profiles_path.read_text(encoding="utf-8", errors="replace")
lines = text.splitlines(keepends=True)
header = []
blocks = []
current = []
in_items = False

for line in lines:
    if re.match(r"^-\s+uid:\s*", line):
        if in_items:
            blocks.append(current)
        else:
            header = current
            in_items = True
        current = [line]
    else:
        current.append(line)

if in_items:
    blocks.append(current)
else:
    raise SystemExit("profiles.yaml does not contain item blocks")

profiles_dir = (profiles_path.parent / "profiles").resolve()
remote_files = []
new_blocks = []
changed = False

for block in blocks:
    block_text = "".join(block)
    if not re.search(r"^\s*type:\s*remote\s*$", block_text, re.MULTILINE):
        new_blocks.append(block)
        continue

    file_match = re.search(r"^\s*file:\s*[\"']?([^\"'\n#]+)", block_text, re.MULTILINE)
    if file_match:
        remote_files.append(file_match.group(1).strip())

    out = []
    url_replaced = False
    for line in block:
        url_match = re.match(r"^(\s*)url:\s*", line)
        updated_match = re.match(r"^(\s*)updated:\s*", line)
        if url_match:
            out.append(f"{url_match.group(1)}url: {json.dumps(new_url, ensure_ascii=False)}\n")
            url_replaced = True
            changed = True
        elif updated_match:
            out.append(f"{updated_match.group(1)}updated: 0\n")
            changed = True
        else:
            out.append(line)

    if not url_replaced:
        inserted = False
        injected = []
        for line in out:
            injected.append(line)
            if not inserted and re.match(r"^\s*type:\s*remote\s*$", line):
                indent = re.match(r"^(\s*)", line).group(1)
                injected.append(f"{indent}url: {json.dumps(new_url, ensure_ascii=False)}\n")
                inserted = True
                changed = True
        out = injected

    new_blocks.append(out)

if not changed:
    raise SystemExit("no remote subscription URL was changed")
if not remote_files:
    raise SystemExit("remote profile item has no file field")

profiles_path.write_text("".join(header + [line for block in new_blocks for line in block]), encoding="utf-8")

if write_profile_payload:
    for rel_file in remote_files:
        dest = (profiles_dir / rel_file).resolve()
        if dest.parent != profiles_dir:
            raise SystemExit(f"refusing unsafe profile file path: {rel_file}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.copy2(dest, dest.with_name(dest.name + f".bak.{run_id}"))
        shutil.copy2(downloaded_path, dest)
        print(f"updated_profile_file={dest.name} bytes={dest.stat().st_size}")
else:
    print("updated_profile_file=skipped_download_failed")

print(f"remote_profiles_updated={len(remote_files)}")
PY
}

download_subscription() {
  local sub_url_file="$1"
  local output_file="$2"
  local sub_url
  sub_url="$(tr -d '\r\n' < "${sub_url_file}")"

  if [ -z "${sub_url}" ]; then
    echo "subscription URL secret is empty" >&2
    return 1
  fi
  if ! [[ "${sub_url}" =~ ^https?:// ]]; then
    echo "subscription URL secret must start with http:// or https://" >&2
    return 1
  fi

  local user_agent
  local user_agents=(
    "clash-verge/v2.3.1"
    "ClashforWindows/0.20.39"
    "Clash"
    "mihomo"
    "Mozilla/5.0"
  )
  for user_agent in "${user_agents[@]}"; do
    if curl -fsSL --retry 1 --connect-timeout 20 --max-time 90 \
      -A "${user_agent}" \
      -H "Accept: */*" \
      "${sub_url}" -o "${output_file}"; then
      echo "subscription_download_user_agent=${user_agent}"
      break
    fi
    echo "subscription_download_failed_user_agent=${user_agent}; retrying with --insecure"
    if curl -fsSLk --retry 1 --connect-timeout 20 --max-time 90 \
      -A "${user_agent}" \
      -H "Accept: */*" \
      "${sub_url}" -o "${output_file}"; then
      echo "subscription_download_user_agent=${user_agent} insecure_tls=true"
      break
    fi
  done

  if [ ! -s "${output_file}" ]; then
    echo "subscription_downloaded=false"
    return 1
  fi

  local bytes
  bytes="$(wc -c < "${output_file}" | tr -d '[:space:]')"
  if [ "${bytes}" -lt 100 ]; then
    echo "downloaded subscription is unexpectedly small: ${bytes} bytes" >&2
    return 1
  fi
  if grep -qiE '<html|<!doctype' "${output_file}"; then
    echo "downloaded subscription looks like an HTML error page" >&2
    return 1
  fi
  echo "subscription_downloaded_bytes=${bytes}"
}

main() {
  case "${MODE}" in
    check|update) ;;
    *)
      echo "usage: $0 check|update [subscription-url-file]" >&2
      exit 2
      ;;
  esac

  local vninja_dir profiles_yaml
  vninja_dir="$(find_vninja_dir)" || {
    echo "could not find V-Ninja profiles.yaml" >&2
    exit 1
  }
  profiles_yaml="${vninja_dir}/profiles.yaml"

  echo "=== V-Ninja profiles summary ==="
  print_profiles_summary "${profiles_yaml}"

  if [ "${MODE}" = "update" ]; then
    if [ -z "${SUB_URL_FILE}" ] || [ ! -s "${SUB_URL_FILE}" ]; then
      echo "update mode requires a non-empty subscription URL file" >&2
      exit 1
    fi

    echo "=== Update V-Ninja subscription ==="
    local downloaded_sub write_profile_payload
    downloaded_sub="$(mktemp)"
    write_profile_payload="true"
    if ! download_subscription "${SUB_URL_FILE}" "${downloaded_sub}"; then
      write_profile_payload="false"
      echo "subscription_download_fallback=url_only_vninja_fetch"
    fi
    update_profiles_yaml_and_file "${profiles_yaml}" "${SUB_URL_FILE}" "${downloaded_sub}" "${write_profile_payload}"
    rm -f "${downloaded_sub}"

    echo "=== Restart V-Ninja ==="
    as_root systemctl restart vninja
    if wait_for_vninja_api; then
      echo "vninja_api_ready=true"
    else
      echo "vninja_api_ready=false"
    fi
    if as_root test -x /usr/local/bin/vninja-allow-lan.sh; then
      as_root /usr/local/bin/vninja-allow-lan.sh || true
    fi
    wait_for_vninja_api || true

    echo "=== V-Ninja profiles summary after update ==="
    print_profiles_summary "${profiles_yaml}"
  fi

  print_proxy_summary
}

main "$@"
