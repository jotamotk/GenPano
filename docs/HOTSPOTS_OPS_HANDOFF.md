# Hotspots — Operations Handoff

This doc covers everything an operator needs to flip the hotspot pipeline from
"shipped but dormant" → "actually populating prompts with current events".

The schema, API, UI, prompt-injection, and collector code are all in main as of
PR #212 (Module D). The work below is **operational config only** — no code
changes required.

---

## Status of each piece

| Piece | State | Action needed |
|---|---|---|
| `hot_topics` table + `prompts.hotspot_id` FK | ✅ shipped (auto-migrated on boot) | none |
| `/api/admin/hot-topics` CRUD + `/collect` + `/archive-expired` | ✅ shipped | none |
| `planner-hotspots` admin UI | ✅ shipped | none |
| Prompt Matrix LLM injection (rules 24/25) | ✅ shipped | none |
| Public-source collectors (`baidu`, `zhihu`) | ✅ shipped & active | none |
| LLM-search collector (`llm_search`) | 🟡 placeholder | wire豆包 web_search (see §3) |
| Browser collectors (`weibo` / `douyin` / `xhs`) | 🟡 code shipped, gated off | provision accounts + flip env (see §1, §2) |
| Beat schedule (cron triggers) | 🟡 not configured | add to `backend/app/celery_app.py` (see §4) |
| Daily archive task | 🟡 not scheduled | add to Beat (see §4) |

---

## 1. Provision platform accounts

Browser collectors reuse the existing `AccountPool`. Each platform owns one
`llm_name` slot, the same way ChatGPT and Doubao do. Operators provision at
least one account per slot through the existing **账号池** admin UI (left nav →
**采集资源**), or directly via SQL:

```sql
INSERT INTO llm_accounts (llm_name, phone_number, email, status, daily_limit, ...)
VALUES
  ('weibo_hots',  '<phone>', '<phone>@weibo_hots.local',  'active', 24, ...),
  ('douyin_hots', '<phone>', '<phone>@douyin_hots.local', 'active', 24, ...),
  ('xhs_hots',    '<phone>', '<phone>@xhs_hots.local',    'active', 24, ...);
```

Then log in once via the SMS-login flow under each account so cookies are saved
to the `llm_accounts.cookies_json` column. The collector will restore those
cookies on every cycle and persist the refreshed jar back to the same field
(handled by `BrowserHotspotCollector` — see `geo_tracker/hotspots/browser.py`).

**Conservative quotas to start**:
- `weibo_hots` — `daily_limit = 24` (1 cycle / hour)
- `douyin_hots` — `daily_limit = 24`
- `xhs_hots` — `daily_limit = 12` (XHS has the strictest anti-bot, so half-rate)

Bind a residential proxy (CN geo) to each account. Reuse the existing proxy
pool and binding flow.

---

## 2. Flip the env flag

Browser collectors short-circuit to `[]` unless this env is set:

```bash
HOTSPOT_BROWSER_COLLECTORS=1
```

Set it on the same process that hosts the admin_console + worker stack
(typically the docker-compose service). Without this flag, `weibo` / `douyin` /
`xhs` are still listed in the registry and the UI dropdown — they just no-op.
This is intentional so the default boot in CI / sandbox / web-only doesn't
spin up Camoufox.

After setting the env, verify:

```bash
docker compose exec admin_console python -m geo_tracker.hotspots.pipeline \
  --sources weibo --industry 母婴个护
```

You should see something like `{"collected": 50, "inserted": 12, ...}` if
microsoft一切就绪. If the account isn't bound, the result is
`{"collected": 0, "inserted": 0, "by_source": {"weibo": 0}, "errors": {}}` —
not an error, just nothing collected.

---

## 3. Wire豆包 web_search (optional)

`geo_tracker/hotspots/llm_search.py` currently emits a placeholder. To make it
return real data:

1. Pick the doubao tools=web_search API (see `admin_console/topic_plan.py
   :DoubaoTopicPlanClient` for the existing OpenAI-compatible call pattern).
2. Replace the placeholder block in `LLMSearchCollector.collect()` with the
   actual call. The prompt should be something like:

   ```
   List the 20 most-discussed Chinese-internet topics in the {industry}
   category over the last 48 hours. Return JSON [{title, summary, category}].
   ```

3. Parse JSON and return `[HotspotCandidate(...)]`.

This collector only matters when public sources (baidu / zhihu) miss your
industry. For 母婴个护 / 美妆个护 they usually catch the headlines fine.

---

## 4. Schedule the cron triggers

Add to `backend/app/celery_app.py` `beat_schedule` (or wherever your Beat
config lives):

```python
"hotspots-baidu":  {"task": "...collect_source", "args": ["baidu"],   "schedule": crontab(minute=20)},
"hotspots-zhihu":  {"task": "...collect_source", "args": ["zhihu"],   "schedule": crontab(minute=40)},
"hotspots-weibo":  {"task": "...collect_source", "args": ["weibo"],   "schedule": crontab(minute=15)},
"hotspots-douyin": {"task": "...collect_source", "args": ["douyin"],  "schedule": crontab(minute=25)},
"hotspots-xhs":    {"task": "...collect_source", "args": ["xhs"],     "schedule": crontab(minute=35, hour="*/2")},
"hotspots-archive":{"task": "...archive_expired_hotspots", "schedule": crontab(hour=3)},
```

Stagger the minutes so the platforms don't all fire at the same wall-clock and
trip rate-limits.

You'll need a thin Celery wrapper around the existing pipeline functions:

```python
# backend/app/tasks/hotspots.py
from celery import shared_task
from geo_tracker.hotspots.pipeline import (
    run_collection_cycle, archive_expired_hotspots,
)

@shared_task(name="hotspots.collect_source")
def collect_source(source: str):
    return run_collection_cycle(sources=[source])

@shared_task(name="hotspots.archive_expired")
def archive_expired():
    return archive_expired_hotspots()
```

Manual one-shot from admin: the **「立即采集」** button in the hotspots page
already calls `/api/admin/hot-topics/collect` — that's enough for ad-hoc
testing without beat.

---

## 5. Verify end-to-end

After §1–§2 are done:

1. Open admin → 左 nav → **热点 Hotspot**.
2. Click **🔄 立即采集**. Within ~30s a toast should report `本次采集 N 条 →
   入库 M 条 (待审区)`.
3. Switch the filter to `draft 待审`. New rows from each enabled source appear.
4. Approve a couple by clicking **✓ 通过**. They flip to `active`.
5. Run a Prompt Matrix generation in the same brand/industry. The
   「本次生成结果」 transparency card on completion should show similar
   acceptance rate as before (≥ 70%); the only visible change is that some
   prompts now mention the hotspot angle.
6. (Optional) `SELECT id, text, hotspot_id FROM prompts WHERE hotspot_id IS
   NOT NULL ORDER BY id DESC LIMIT 10` to confirm FK linkage.

---

## What's deliberately NOT shipped (future work)

- **Embedding-based dedupe (Module E-2)** — switch from 96% string similarity
  to pgvector ANN once the prompt library passes ~5k rows.
- **Coverage snapshot for prompt-matrix LLM (Module E-2.2)** — k-means on
  prompt embeddings, send LLM the cluster summary instead of the raw
  recent-300 list. Same trigger.
- **Per-collector toolbar in UI** — current UI batches all collectors into a
  single "立即采集" button. The plan §D-2.7 sketched a per-source on/off panel
  with last-run times; left for a follow-up.
- **Cross-batch query analytics for hotspot impact** — "did the hotspot
  actually move sentiment?" tracking. Out of scope for this module set.

If you want any of these next, the plan file at
`/root/.claude/plans/genpano-admin-1-rustling-naur.md` has §E and §D-2.6/2.7
written up in full.
