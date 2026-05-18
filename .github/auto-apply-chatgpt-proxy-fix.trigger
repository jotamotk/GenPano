# Auto-apply trigger for .github/workflows/chatgpt-proxy-hotfix.yml
#
# Committing this file with a new timestamp causes the hotfix workflow
# to fire via its push trigger. The workflow still runs:
#   1. Guard (event-type aware, push allowed)
#   2. Route-policy preflight (asserts 豆包/deepseek direct, chatgpt proxy
#      against production env — aborts if drift detected)
#   3. Apply UFW allow rules (9098 + 6789, scoped to 172.16.0.0/12)
#   4. Replace /usr/local/bin/vninja-allow-lan.sh
#   5. Verify worker -> :9098 returns 200/401 and worker -> :6789
#      returns non-000 (else fail the run)
#
# Refs PR #1209. User authorized via "按照你的计划执行" + "通过cicd去访问服务器".

trigger_at: 2026-05-18T07:00:00Z
reason: First production deploy of UFW :9098 + :6789 allow rules
user_constraint: 豆包/deepseek direct-connect, chatgpt via proxy
