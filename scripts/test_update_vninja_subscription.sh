#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_dir="$(mktemp -d)"
cleanup() {
  local exit_code=$?
  if [ "${exit_code}" -ne 0 ] && [ -f "${tmp_dir}/script.log" ]; then
    cat "${tmp_dir}/script.log" >&2
  fi
  rm -rf "${tmp_dir}"
  exit "${exit_code}"
}
trap cleanup EXIT

fake_bin="${tmp_dir}/bin"
data_dir="${tmp_dir}/vninja"
mkdir -p "${fake_bin}" "${data_dir}/profiles"

cat > "${data_dir}/profiles.yaml" <<'YAML'
current: remote-1
items:
  - uid: remote-1
    type: remote
    name: Remote Subscription
    url: "https://old.example/sub"
    file: remote.yaml
    updated: 123
YAML

cat > "${data_dir}/profiles/remote.yaml" <<'YAML'
proxies: []
YAML

cat > "${tmp_dir}/subscription-url.txt" <<'EOF_URL'
https://new.example/sub
EOF_URL

cat > "${fake_bin}/curl" <<'SH'
#!/usr/bin/env bash
set -Eeuo pipefail

method="GET"
output=""
write_out=""
args=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    -X)
      method="$2"
      shift 2
      ;;
    -o)
      output="$2"
      shift 2
      ;;
    -w)
      write_out="$2"
      shift 2
      ;;
    -A|-H|--max-time|--connect-timeout|--retry|--proxy)
      shift 2
      ;;
    -fsS|-fsSL|-fsSLk|-sS|-k)
      shift
      ;;
    *)
      args+=("$1")
      shift
      ;;
  esac
done

url="${args[-1]:-}"
case "${url}" in
  https://new.example/sub)
    echo "direct subscription download attempted" >> "${DIRECT_DOWNLOAD_LOG}"
    exit 22
    ;;
  http://127.0.0.1:9097/configs)
    printf '{}'
    ;;
  http://127.0.0.1:9097/proxies)
    printf '{"proxies":{"Ai":{"type":"Selector","all":["a"],"now":"a"},"a":{"type":"ss"}}}'
    ;;
  http://127.0.0.1:9097/providers/proxies)
    printf '{"providers":{"default":{},"💬 Ai平台":{}}}'
    ;;
  http://127.0.0.1:9097/providers/proxies/%F0%9F%92%AC%20Ai%E5%B9%B3%E5%8F%B0)
    if [ "${method}" = "PUT" ]; then
      printf '%s\n' "${url}" >> "${PROVIDER_REFRESH_LOG}"
      [ -n "${write_out}" ] && printf '%s' "${write_out//%\{http_code\}/204}"
      exit 0
    fi
    exit 1
    ;;
  https://www.gstatic.com/generate_204|https://chatgpt.com/)
    [ -n "${write_out}" ] && printf '%s' "${write_out//%\{http_code\}/204}"
    ;;
  *)
    echo "unexpected curl url: ${url}" >&2
    exit 4
    ;;
esac

if [ -n "${output}" ]; then
  : > "${output}"
fi
SH
chmod +x "${fake_bin}/curl"

cat > "${fake_bin}/systemctl" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "is-active" ]; then
  echo active
fi
exit 0
SH
chmod +x "${fake_bin}/systemctl"

cat > "${fake_bin}/ss" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "${fake_bin}/ss"

cat > "${fake_bin}/docker" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "${fake_bin}/docker"

cat > "${fake_bin}/sudo" <<'SH'
#!/usr/bin/env bash
exec "$@"
SH
chmod +x "${fake_bin}/sudo"

cat > "${fake_bin}/python3" <<'SH'
#!/usr/bin/env bash
converted=()
for arg in "$@"; do
  case "${arg}" in
    /tmp/*|/c/*)
      converted+=("$(cygpath -w "${arg}")")
      ;;
    *)
      converted+=("${arg}")
      ;;
  esac
done
exec /c/Users/frank.wang/genpano/backend/.venv/Scripts/python.exe "${converted[@]}"
SH
chmod +x "${fake_bin}/python3"

allow_lan_script="${tmp_dir}/vninja-allow-lan.sh"
cat > "${allow_lan_script}" <<'SH'
#!/usr/bin/env bash
echo allow-lan-started >> "${ALLOW_LAN_LOG}"
SH
chmod +x "${allow_lan_script}"

export DIRECT_DOWNLOAD_LOG="${tmp_dir}/direct-download.log"
export PROVIDER_REFRESH_LOG="${tmp_dir}/provider-refresh.log"
export ALLOW_LAN_LOG="${tmp_dir}/allow-lan.log"

PATH="${fake_bin}:${PATH}" \
PYTHONIOENCODING="utf-8" \
VNINJA_DATA_DIR="${data_dir}" \
VNINJA_ALLOW_LAN_SCRIPT="${allow_lan_script}" \
GITHUB_RUN_ID="test-run" \
bash "${repo_root}/scripts/update_vninja_subscription.sh" update "${tmp_dir}/subscription-url.txt" > "${tmp_dir}/script.log"

grep -q 'url: "https://new.example/sub"' "${data_dir}/profiles.yaml"
grep -q 'updated: 0' "${data_dir}/profiles.yaml"
grep -q 'remote_profiles_updated=1' "${tmp_dir}/script.log"
grep -q 'http://127.0.0.1:9097/providers/proxies/%F0%9F%92%AC%20Ai%E5%B9%B3%E5%8F%B0' "${PROVIDER_REFRESH_LOG}"
grep -q 'allow-lan-started' "${ALLOW_LAN_LOG}"

if [ -s "${DIRECT_DOWNLOAD_LOG}" ]; then
  echo "direct subscription download should not be the update path" >&2
  exit 1
fi

echo "update_vninja_subscription app-first regression checks passed"
