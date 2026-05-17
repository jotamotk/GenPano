# experiments/vm_per_account — M1 PoC

## What this is

This experiment validates that a VM-resident, **manually logged-in** Chrome,
driven from a local Playwright script over CDP via Tailscale, can extract a
real Doubao response without hitting any of the three failure modes documented
in [#963](https://github.com/genpano/genpano/issues/963):

1. cookie-injection auth-fail (`doubao_not_logged_in` after `context.add_cookies()`)
2. page-load failure (blank title, `Target page, context or browser has been closed`)
3. frequent captcha during the auto-registration ricochet

The architecture decision being tested is **persistent VM browser session**
(one cloud VM per account, login state lives in the on-disk Chrome profile)
rather than injecting cookies into a fresh headless browser per run.

**M1 binary success criterion**: 1 cloud VM, 1 real Doubao query,
`rawText` length >= 200 chars, zero failure signals. See section
[**M1 GREEN definition**](#m1-green-definition) below for the full checklist.

This is M1 only — M2 (full GO/NO-GO matrix of N=15) is out of scope; see
[**What's next**](#whats-next-m2).

## Prereqs

- Aliyun (or equivalent) ECS account with billing enabled
- Tailscale account (free tier is sufficient for 1 VM + 1 laptop)
- Local laptop with Python 3.11+ and Playwright installed:

  ```bash
  pip install playwright
  playwright install chromium
  ```

## Step-by-step (M1, ~1 hour)

### Step 1 — Provision the Aliyun ECS

- Region: Beijing zone-c (matches the geo of doubao.com so anti-fraud sees a
  Beijing residential-class egress IP)
- Instance: `ecs.g7.large` (2 vCPU, 8 GB) — enough for Chrome + xfce
- Image: Ubuntu 22.04 LTS x86_64
- Storage: 40 GB ESSD
- Network: VPC with public IPv4 (for initial SSH and apt; Tailscale takes over
  after step 3)
- Security group:
  - inbound: allow `22/tcp` from your IP only
  - inbound: deny everything else (the bootstrap script also configures UFW
    locally as defense-in-depth)
  - outbound: allow all

### Step 2 — Run the bootstrap script

```bash
# From your laptop
scp experiments/vm_per_account/vm_bootstrap.sh root@<ecs-public-ip>:/root/
ssh root@<ecs-public-ip>
sudo bash /root/vm_bootstrap.sh
```

The script will:

- install xfce4 minimal, x11vnc, novnc, Tailscale, google-chrome-stable,
  xdotool, xvfb
- create user `ops` with passwordless sudo
- write systemd units for `xvfb`, `xfce`, `x11vnc`, `websockify`,
  `chrome-doubao`, `chrome-deepseek`
- enable the display stack (Xvfb + xfce + VNC) at boot
- intentionally **NOT** start the two Chrome services (operator does this
  after first manual login)
- print the generated VNC password — copy it down now (also kept at
  `/home/ops/.vncpasswd`)
- configure UFW to allow only SSH + Tailscale, blocking public 5900/6080/9222/9223

### Step 3 — Bring up Tailscale on the VM

```bash
sudo tailscale up
# Open the printed URL on your laptop, authenticate.
tailscale ip --4   # note the 100.x.x.x address
hostname           # note the machine name, e.g. vm-doubao-01
```

The Tailscale magic-DNS hostname for the VM will be something like
`vm-doubao-01.tail-xxxxx.ts.net`. Use it everywhere below.

### Step 4 — Install Tailscale on your laptop

Follow https://tailscale.com/download — log in with the same account so the
laptop joins the same tailnet as the VM.

Verify reachability:

```bash
ping vm-doubao-01.tail-xxxxx.ts.net    # should answer
```

### Step 5 — Start the two Chrome services on the VM

SSH in (or use the VNC terminal in step 6) and run:

```bash
sudo systemctl start chrome-doubao chrome-deepseek
sudo systemctl status chrome-doubao chrome-deepseek
```

Both should be `active (running)`. Each owns its own persistent profile:
`/home/ops/profile-doubao` and `/home/ops/profile-deepseek`.

### Step 6 — VNC in and manually log in

On your laptop, open in a browser:

```
http://vm-doubao-01.tail-xxxxx.ts.net:6080/vnc.html
```

Connect with the VNC password from step 2. You should see an xfce desktop with
two Chrome windows — one for each engine.

- In the Doubao Chrome window: navigate to https://www.doubao.com/chat and
  log in (扫码 with the 豆包/抖音 app or SMS code). Confirm you land on the
  chat UI and `passport.volcengine.com` does NOT appear in the URL bar.
- In the DeepSeek Chrome window: navigate to https://chat.deepseek.com and
  log in. Confirm you can see the chat UI.

The login state is now persisted in the on-disk Chrome profile. It survives
Chrome restarts. It survives VM reboots. It does **not** survive
`rm -rf /home/ops/profile-doubao`.

### Step 7 — Verify CDP reachability from your laptop

```bash
curl http://vm-doubao-01.tail-xxxxx.ts.net:9222/json/version
curl http://vm-doubao-01.tail-xxxxx.ts.net:9223/json/version
```

Both should return JSON with `"Browser": "Chrome/<version>"`. If you get
connection refused, see [**Troubleshooting**](#troubleshooting).

### Step 8 — Run the M1 binary test

From the repo root on your laptop:

```bash
python experiments/vm_per_account/poc_runner.py \
  --cdp-endpoint http://vm-doubao-01.tail-xxxxx.ts.net:9222 \
  --engine doubao \
  --prompt-text "推荐一个性价比高的国产手机品牌" \
  --prompt-id m1_smoke
```

The script will print one line per rep to stderr and a final summary to stdout:

```
M1 result: 1/1 succeeded, artifact dir: .../experiments/vm_per_account/runs/doubao/m1_smoke
```

Exit code is `0` only if all reps succeeded.

### Step 9 — Inspect the artifacts

```
experiments/vm_per_account/runs/doubao/m1_smoke/1/
  result.json     # success: true, failure_signals: [], rawText_len, latency_ms
  rawText.txt     # the extracted Doubao reply (should be >= 200 chars)
  screenshot.png  # full-page screenshot at end of run
  trace.zip       # Playwright trace (open with `playwright show-trace trace.zip`)
```

Open `rawText.txt` and confirm it contains a meaningful Doubao reply about
domestic phone brands. If yes, **M1 is GREEN**.

## M1 GREEN definition

All six must be true (copy from the approved plan at
`/root/.claude/plans/fancy-snuggling-treehouse.md`):

- [ ] `result.json.success == true`
- [ ] `result.json.failure_signals == []`
- [ ] `len(rawText.txt) >= 200`
- [ ] `rawText.txt` contains semantic content about the prompted topic
      (not a login wall, not a captcha screen)
- [ ] `screenshot.png` shows the Doubao chat UI with the AI reply rendered
- [ ] No URL in the trace contains `passport.volcengine.com`,
      `sso.volcengine.com`, or `passport.douyin.com`

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `rawText.txt` is empty or `< 30 chars` | Chrome session logged out, or Doubao selectors drifted | VNC in, re-login; if still empty, update `ENGINE_CONFIG` in `poc_runner.py` against the current Doubao DOM |
| `failure_signals` contains `page_lifecycle_error: ... Target ... has been closed` | Chrome crashed mid-run | `sudo systemctl restart chrome-doubao`; check `journalctl -u chrome-doubao --since "10 min ago"` |
| `failure_signals` contains `login_redirect_url: ...passport.volcengine.com...` | session lost (cookies expired, IP changed, anti-fraud kicked you out) | VNC in, re-login; if recurring, escalate (the architecture assumes the session survives — recurring drops invalidate M1) |
| `curl http://...:9222/json/version` connection refused | Chrome service not started, or you're not on Tailscale | `sudo systemctl status chrome-doubao`; `tailscale status` on both sides |
| `failure_signals` contains `captcha_widget_detected` | Doubao showed a verification challenge | VNC in, solve it once manually, re-run; if it keeps recurring this is a finding against the architecture |
| `submit_click_failed_fallback_to_enter` in signals but `rawText` is still good | the click selector missed but Enter worked | non-fatal; consider updating the `submit_button` selector |

## What's next (M2)

After M1 is GREEN, M2 expands to the full Phase 0 GO/NO-GO matrix:

1. Pull the real prompt text for query IDs `184968`, `184971`, `184974` from
   the production DB (use the existing
   `app-analytics-readonly-evidence.yml` workflow, or ask the team for an
   ad-hoc readback). Paste each into `replay_inputs.json` in place of the
   `TODO:` placeholders.
2. Run `poc_runner.py --reps 5` for each of the three queries on Doubao.
3. Repeat for DeepSeek (the second Chrome instance on port `9223`) once at
   least one DeepSeek control prompt is in `replay_inputs.json`.
4. Score the N=15 matrix (3 queries x 5 reps) against the GO/NO-GO criteria
   in the plan's `Phase 0 GO/NO-GO` section.

When M2 is GREEN, escalate to PRD-side scope expansion (multi-VM,
per-account billing, scheduler integration).

## Stop / cleanup

While iterating (keep the VM around for re-runs):

```bash
sudo systemctl stop chrome-doubao chrome-deepseek
# leave the display stack running so you can VNC back in cheaply
```

When fully done with M1 (stop billing):

```bash
# From inside the VM:
sudo poweroff

# Then in the Aliyun console: release the ECS instance (not just stop —
# stopped instances still bill for the system disk).
```

Note: releasing the ECS destroys `/home/ops/profile-doubao` and the login
state with it. Snapshot the disk first if you want to preserve the logged-in
profile for re-use.

## Files in this directory

| File | Purpose |
| --- | --- |
| `vm_bootstrap.sh` | Idempotent VM provisioning script (Ubuntu 22.04) |
| `poc_runner.py` | Local CDP driver — runs one prompt, captures artifacts |
| `replay_inputs.json` | M2 prompt corpus (operator fills `TODO:` slots from prod DB) |
| `README.md` | This file |
| `runs/` | Per-run artifacts (created by `poc_runner.py`, gitignored at the repo level) |
