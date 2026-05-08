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
| Public-source collectors (`baidu`, `zhihu`, `weibo`) | ✅ shipped & active, no account needed | none |
| Browser collectors (`douyin` / `xhs`) | ✅ code + UI shipped | provision accounts + flip env (see §1, §2) |
| Beat schedule (cron triggers) | ✅ shipped | none — auto-fires once main worker has the latest image |
| Daily archive task | ✅ scheduled (03:00 UTC daily) | none |
| LLM-search collector (`llm_search`) | 🟡 placeholder | wire 豆包 web_search (see §3) — optional |

---

## 1. Provision platform accounts

**Weibo no longer needs an account** — the collector now uses the public
mobile JSON endpoint (`m.weibo.cn/api/container/getIndex`), which returns
the same ~50 trending list anonymously. If that endpoint is ever blocked
the collector falls back to scraping the desktop HTML; both paths are
no-account.

For **douyin** and **xhs** an authenticated browser session is still
required. Each platform owns one `llm_name` slot in the existing
`AccountPool`, the same way ChatGPT and Doubao do. Provision through the
existing **采集资源 → + 添加账号 → Cookies 导入** UI (the platform dropdown
now lists `douyin_hots` and `xhs_hots`).

**Conservative quotas to start**:
- `douyin_hots` — `daily_limit = 24` (1 cycle / hour)
- `xhs_hots` — `daily_limit = 12` (XHS has the strictest anti-bot, so half-rate)

Bind a residential proxy (CN geo) to each account. Reuse the existing proxy
pool and binding flow.

---

## 2. Flip the env flag (douyin / xhs only)

The two remaining browser collectors short-circuit to `[]` unless this env
is set on the worker:

```bash
HOTSPOT_BROWSER_COLLECTORS=1
```

Set it on the docker-compose service that runs the Celery worker (the
`beat` queue). Without this flag, `douyin` / `xhs` are still listed in
the registry and the Beat schedule — they just no-op. Default boots in
CI / sandbox / web-only don't spin up Camoufox.

`weibo` / `baidu` / `zhihu` are unaffected by this flag — they're plain
HTTP and always run.

After setting the env, verify:

```bash
docker compose exec backend python -m geo_tracker.hotspots.pipeline \
  --sources weibo,baidu --industry 母婴个护
```

You should see something like `{"collected": 50, "inserted": 12, ...}`.
If an account isn't bound for a browser source, the result is
`{"collected": 0, "inserted": 0, "by_source": {"douyin": 0}, "errors": {}}` —
not an error, just nothing collected.

---

## 3. Wire豆包 web_search (optional)

`geo_tracker/hotspots/llm_search.py` currently emits a placeholder. To make it
return real data:

1. Pick the doubao tools=web_search API (see
   `backend/app/services/topic_plan.py :DoubaoTopicPlanClient` for the
   existing OpenAI-compatible call pattern).
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

## 4. Beat schedule (already shipped)

`backend/app/celery_app.py` now declares the full set of hotspot Beat
entries (staggered minutes per source, one nightly archive at 03:00 UTC).
The thin Celery wrappers live in `geo_tracker/tasks/hotspots.py`.
Once the worker pulls the latest image the cron fires automatically;
no extra ops work needed beyond §1-§2.

Manual one-shot from admin: the **「立即采集」** button in the hotspots page
calls `/api/admin/hot-topics/collect` synchronously — useful for ad-hoc
testing or fresh installs that don't want to wait for the next cron tick.

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
