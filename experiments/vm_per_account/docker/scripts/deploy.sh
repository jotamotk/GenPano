#!/usr/bin/env bash
# Single deploy script invoked by .github/workflows/vm-docker-deploy.yml.
#
# All required files (Dockerfile, docker-compose.yml, entrypoint.sh, this
# script) are SCP'd to the ECS host by the workflow *before* this runs.
# We never git clone on the ECS side — the user's repo is private and we
# don't want to fight credentials. The workflow already has the repo
# checked out on the GH Actions runner via actions/checkout.
#
# Layout on ECS after workflow scp:
#   $VM_DEPLOY_PATH/Dockerfile
#   $VM_DEPLOY_PATH/docker-compose.yml
#   $VM_DEPLOY_PATH/entrypoint.sh
#   $VM_DEPLOY_PATH/.env.example
#   $VM_DEPLOY_PATH/scripts/deploy.sh   (this file)
#   $VM_DEPLOY_PATH/data/profile-doubao-01  (created at runtime)
#
# Call: ACTION=inspect bash deploy.sh
set -uo pipefail

: "${ACTION:?must set ACTION env}"
VM_DEPLOY_PATH="${VM_DEPLOY_PATH:-/opt/vm-per-account-deploy}"
CONTAINER="${CONTAINER:-}"
TAIL_LINES="${TAIL_LINES:-200}"

# The workflow scp's the docker/ subdir contents directly into VM_DEPLOY_PATH,
# so DOCKER_DIR == VM_DEPLOY_PATH.
DOCKER_DIR="$VM_DEPLOY_PATH"

# Helper: run docker compose, fallback to sudo if user not in docker group
dc() {
  if groups | grep -q docker; then
    docker compose "$@"
  else
    sudo docker compose "$@"
  fi
}

case "$ACTION" in
  inspect)
    # Read-only path discovery.
    echo "=== whoami + home ==="
    whoami
    echo "\$HOME=$HOME"
    echo
    echo "=== /opt content ==="
    ls -la /opt 2>/dev/null | head -20 || echo "/opt does not exist"
    echo
    echo "=== /root content ==="
    sudo ls -la /root 2>/dev/null | head -20 || echo "(no perms or empty)"
    echo
    echo "=== /home content ==="
    ls -la /home 2>/dev/null | head -20
    echo
    echo "=== find: genpano / trash_test / geo_tracker / backend dirs ==="
    sudo find / -maxdepth 5 -type d \
      \( -name "genpano*" -o -name "trash_test*" -o -name "geo_tracker" -o -name "backend" \) \
      2>/dev/null | head -30
    echo
    echo "=== which git docker python ==="
    which git docker python python3 2>/dev/null || true
    docker --version 2>/dev/null || echo "(docker not installed yet)"
    echo
    echo "=== disk usage ==="
    df -h | head -10
    echo
    echo "=== VM_DEPLOY_PATH state ==="
    ls -la "$VM_DEPLOY_PATH" 2>/dev/null || echo "($VM_DEPLOY_PATH does not exist)"
    echo
    echo "=== systemd services (genpano backend etc.) ==="
    systemctl list-units --type=service --no-pager 2>/dev/null \
      | grep -iE "(genpano|fastapi|celery|backend|gunicorn|uvicorn)" \
      | head -20 || true
    ;;

  bootstrap)
    set -euxo pipefail
    # docker
    if ! command -v docker >/dev/null; then
      curl -fsSL https://get.docker.com | sudo sh
      sudo usermod -aG docker "$(whoami)" || true
    fi
    # ufw
    if ! command -v ufw >/dev/null; then
      sudo apt-get update -qq && sudo apt-get install -y ufw
    fi
    sudo ufw --force default deny incoming
    sudo ufw --force default allow outgoing
    local_ssh_port="${SSH_PORT:-22}"
    sudo ufw allow "${local_ssh_port}/tcp" comment 'ssh for vm-docker-deploy'
    sudo ufw deny in proto tcp to any port 6080:6090 || true
    sudo ufw deny in proto tcp to any port 9222:9232 || true
    sudo ufw --force enable
    sudo ufw status numbered
    # Verify scp'd files are present
    cd "$DOCKER_DIR"
    for f in Dockerfile docker-compose.yml entrypoint.sh; do
      if [ ! -f "$f" ]; then
        echo "FATAL: $f missing in $DOCKER_DIR — workflow scp step incomplete?"
        ls -la
        exit 1
      fi
    done
    # build image
    dc build
    echo "=== bootstrap complete ==="
    docker --version 2>/dev/null || sudo docker --version
    sudo ufw status
    df -h "$DOCKER_DIR"
    ;;

  up)
    set -euxo pipefail
    cd "$DOCKER_DIR"
    # Write .env atomically (mode 0600).
    umask 0177
    {
      printf 'VNC_PASSWORD_01=%s\n' "${VNC_PASSWORD_01:?must set VNC_PASSWORD_01}"
      printf 'VNC_PASSWORD_02=%s\n' "${VNC_PASSWORD_02:?must set VNC_PASSWORD_02}"
    } > .env.tmp && mv .env.tmp .env
    dc up -d
    sleep 3
    dc ps
    ;;

  down)
    set -euxo pipefail
    cd "$DOCKER_DIR"
    dc down
    ;;

  restart)
    set -euxo pipefail
    cd "$DOCKER_DIR"
    if [ -z "$CONTAINER" ] || [ "$CONTAINER" = "all" ]; then
      dc restart
    else
      dc restart "$CONTAINER"
    fi
    ;;

  logs)
    set -uo pipefail
    cd "$DOCKER_DIR"
    if [ -z "$CONTAINER" ] || [ "$CONTAINER" = "all" ]; then
      dc logs --tail="$TAIL_LINES"
    else
      dc logs --tail="$TAIL_LINES" "$CONTAINER"
    fi
    ;;

  pull)
    # Pull action no longer applies — files come from the workflow's scp on
    # every run. Re-dispatch the workflow to get the latest code on ECS.
    echo "NOTE: 'pull' is a no-op in scp-based flow. Re-dispatch the workflow"
    echo "      (any action) to scp the latest experiments/vm_per_account/docker/"
    echo "      files from the runner's actions/checkout snapshot."
    ;;

  status)
    set -uo pipefail
    echo "=== uptime ==="
    uptime
    echo "=== free -h ==="
    free -h
    echo "=== df -h / ==="
    df -h / | head -3
    echo "=== ufw status ==="
    sudo ufw status numbered || true
    echo "=== docker compose ps ==="
    cd "$DOCKER_DIR" 2>/dev/null && dc ps || echo "($DOCKER_DIR not present; run bootstrap first)"
    ;;

  destroy)
    set -euxo pipefail
    cd "$DOCKER_DIR"
    dc down -v
    sudo rm -rf ./data/profile-doubao-01 ./data/profile-doubao-02
    echo "=== profiles destroyed; next 'up' will need fresh login ==="
    ;;

  *)
    echo "Unknown ACTION: $ACTION"
    exit 2
    ;;
esac
