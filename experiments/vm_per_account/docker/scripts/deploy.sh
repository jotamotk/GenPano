#!/usr/bin/env bash
# Single deploy script invoked by .github/workflows/vm-docker-deploy.yml.
# Each "action" the workflow accepts maps to a case branch here.
#
# Call: ACTION=inspect bash deploy.sh
#       ACTION=bootstrap CONTAINER= TAIL_LINES=200 ECS_REPO_PATH=/opt/foo \
#                        VNC_PASSWORD_01=... VNC_PASSWORD_02=... bash deploy.sh
#
# This file is uploaded to the ECS via scp by the workflow; runs as the
# SSH user (root or ubuntu) with sudo NOPASSWD assumed.
set -uo pipefail

: "${ACTION:?must set ACTION env}"
ECS_REPO_PATH="${ECS_REPO_PATH:-/opt/trash_test}"
CONTAINER="${CONTAINER:-}"
TAIL_LINES="${TAIL_LINES:-200}"

# DOCKER_DIR resolution: prefer the existing $ECS_REPO_PATH if it has the
# docker subdir (user's existing repo, no mutation needed). Otherwise fall
# back to the suffix path that bootstrap clones fresh into.
PRIMARY_DOCKER_DIR="$ECS_REPO_PATH/experiments/vm_per_account/docker"
FORK_DOCKER_DIR="${ECS_REPO_PATH}-vm-deploy/experiments/vm_per_account/docker"
if [ -d "$PRIMARY_DOCKER_DIR" ]; then
  DOCKER_DIR="$PRIMARY_DOCKER_DIR"
elif [ -d "$FORK_DOCKER_DIR" ]; then
  DOCKER_DIR="$FORK_DOCKER_DIR"
else
  # Neither exists yet — bootstrap will create one. Use primary as default
  # for error messages.
  DOCKER_DIR="$PRIMARY_DOCKER_DIR"
fi

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
    # Allow the SSH port we connected via.
    local_ssh_port="${SSH_PORT:-22}"
    sudo ufw allow "${local_ssh_port}/tcp" comment 'ssh for vm-docker-deploy'
    # noVNC + CDP defence-in-depth (Docker loopback bind is primary).
    sudo ufw deny in proto tcp to any port 6080:6090 || true
    sudo ufw deny in proto tcp to any port 9222:9232 || true
    sudo ufw --force enable
    sudo ufw status numbered
    # repo — bootstrap is SAFE for production: never mutate the user's
    # primary $ECS_REPO_PATH checkout. Three cases:
    #   1. PRIMARY has our docker subdir → use as-is, NO git ops (prod safe)
    #   2. PRIMARY doesn't exist at all → clone fresh into PRIMARY
    #   3. PRIMARY exists but missing our subdir → use FORK suffix path
    #      (clone fresh OR pull --ff-only if already cloned) — FORK is
    #      always git-mutated since it's not the prod repo.
    FORK_PATH="${ECS_REPO_PATH}-vm-deploy"
    if [ -d "$PRIMARY_DOCKER_DIR" ]; then
      echo "Using PRIMARY $ECS_REPO_PATH (no git ops — prod repo state preserved)"
      WORK_DIR="$ECS_REPO_PATH"
      DOCKER_DIR="$PRIMARY_DOCKER_DIR"
    elif [ ! -e "$ECS_REPO_PATH" ]; then
      sudo mkdir -p "$(dirname "$ECS_REPO_PATH")"
      sudo chown -R "$(whoami):$(whoami)" "$(dirname "$ECS_REPO_PATH")"
      git clone https://github.com/jotamotk/trash_test.git "$ECS_REPO_PATH"
      WORK_DIR="$ECS_REPO_PATH"
      DOCKER_DIR="$PRIMARY_DOCKER_DIR"
    else
      # Path exists but missing docker subdir — use FORK suffix path.
      # FORK is always pulled fresh / cloned fresh: it's not the prod repo,
      # so re-bootstrap should always bring in latest deploy.sh + Dockerfile.
      echo "$ECS_REPO_PATH exists but missing experiments/vm_per_account/docker/"
      if [ ! -d "$FORK_PATH/.git" ]; then
        echo "Cloning fresh to $FORK_PATH (prod repo untouched)"
        sudo mkdir -p "$(dirname "$FORK_PATH")"
        sudo chown -R "$(whoami):$(whoami)" "$(dirname "$FORK_PATH")"
        git clone https://github.com/jotamotk/trash_test.git "$FORK_PATH"
      else
        echo "Refreshing existing FORK $FORK_PATH (git pull --ff-only)"
        cd "$FORK_PATH" && git fetch origin main && git checkout main && git pull --ff-only
      fi
      WORK_DIR="$FORK_PATH"
      DOCKER_DIR="$FORK_PATH/experiments/vm_per_account/docker"
      echo "NOTE: VM ops use $FORK_PATH ($ECS_REPO_PATH prod untouched)"
    fi
    # build images
    cd "$DOCKER_DIR"
    dc build
    echo "=== bootstrap complete ==="
    docker --version 2>/dev/null || sudo docker --version
    sudo ufw status
    df -h "$WORK_DIR"
    echo "VM ops path: $WORK_DIR"
    ;;

  up)
    set -euxo pipefail
    cd "$DOCKER_DIR"
    # Write .env atomically (mode 0600). Secrets piped in via env from workflow.
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
    set -euxo pipefail
    cd "$ECS_REPO_PATH"
    git fetch origin main
    git checkout main
    git pull
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
    cd "$DOCKER_DIR" 2>/dev/null && dc ps || echo "(docker dir not present; bootstrap first)"
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
