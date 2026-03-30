# LLM Web Scraping 经验总结与未来规划

> 更新日期: 2026-03-30
> 涉及 LLM: ChatGPT, Gemini, Perplexity 等

---

## 一、问题解决时间线

### 1. Clash 代理订阅（根因）

**现象**: Cloudflare 返回 "Unable to load site"
**原因**: `clash/config.yaml` 用 `type: file` 引用不存在的 `ninja.yaml`，代理节点为空
**修复**: 改为 `type: http` + 订阅 URL，自动拉取节点列表

### 2. Docker 容器 Page crashed

**现象**: worker 日志反复出现 `Page crashed`
**排查过程**:
1. 首先怀疑 `/dev/shm` 不足 — 加了 `shm_size: 2gb`，未解决
2. 二分法测试发现：设置 **任何** 自定义 `user_agent`（通过 `browser.new_context(user_agent=...)`）都会导致崩溃
3. 根因：Playwright 通过 CDP 协议设置 UA 时与 ChatGPT 页面的渲染机制冲突

**修复**: 移除 context 级 `user_agent`，改用 JS `Object.defineProperty(navigator, 'userAgent', ...)` 注入

**关键教训**: 不要加 `--disable-software-rasterizer`。和 `--disable-gpu` 同时使用会移除所有渲染后端，导致 GPU 密集页面（ChatGPT、Gemini）直接崩溃。必须保留 `--use-gl=swiftshader` 作为软件渲染后端。

### 3. Cloudflare 检测时序问题

**现象**: CF 检测逻辑被跳过，直接进入后续流程
**原因**: `domcontentloaded` 时 title 可能为空，CF 检测只匹配了特定标题关键词
**修复**: 空标题也视为 "未就绪"，等待最多 10 秒让 title 出现，然后再做 CF 匹配（最多 30 秒）

### 4. Camoufox 集成（核心突破）

**现象**: 普通 Playwright Chromium 始终触发 Cloudflare Turnstile 验证码
**方案**: 引入 Camoufox（基于 Firefox 的反指纹浏览器）

**踩过的坑**:
| 问题 | 错误信息 | 修复 |
|------|----------|------|
| `screen` 参数类型 | `'dict' object has no attribute 'is_set'` | 移除 `screen` 参数，让 Camoufox 自动生成指纹 |
| geoip 依赖缺失 | `NotInstalledGeoIPExtra` | 移除 `geoip=True`（已手动设 `locale`） |
| GTK3 库缺失 | `libgtk-3.so.0: cannot open shared object file` | Dockerfile 添加 `libgtk-3-0 libpango-1.0-0 libcairo2 libx11-xcb1` |

**最终生效的 Camoufox 参数**:
```python
camoufox_kwargs = {
    "headless": True,
    "humanize": True,      # 模拟人类行为
    "block_images": False,
    "os": "windows",       # 伪装 Windows 指纹
    "locale": "en-US",
}
```

### 5. 代理节点自动切换

**实现**: 通过 Clash REST API（port 9090）查询和切换 `🍃 Proxies` 组内的节点
**注意**: 最初错误地操作了 `🌏 Overseas LLM` 组（该组只含子组和 DIRECT），需要直接操作包含实际节点的 `🍃 Proxies` 组

### 6. retry_count 重复递增

**现象**: 前端点一次 retry，`retry_count` 增加近 10 次
**原因**: 内部节点切换重试(3次) × Celery 任务重试(3次) 每次都递增 `retry_count`
**修复**: 只在前端手动 retry 时递增，内部重试不改 `retry_count`

---

## 二、ChatGPT vs Gemini 架构对比

| 维度 | ChatGPT | Gemini |
|------|---------|--------|
| **浏览器引擎** | Camoufox (Firefox 反指纹) | Camoufox (同) |
| **反检测能力** | 内置指纹伪装 + humanize | 同上 |
| **认证方式** | 无需登录 (guest 模式) | 依赖 `GEMINI_COOKIES_JSON` |
| **防护类型** | Cloudflare Turnstile | Google 自有反爬 |
| **输入方式** | `keyboard.type()` + Enter | JS 注入 contenteditable (Quill 编辑器) |
| **提交后等待** | 25 秒固定 | 60 秒固定 |
| **数据质量** | 高（直接拿到完整 Markdown 响应） | 中（Angular 自定义元素，提取复杂） |
| **稳定性** | 高（无 cookie 过期问题） | 中（cookie 过期导致失败） |

### ChatGPT 成功的关键因素

1. **Camoufox 绕过 Cloudflare** — Firefox 内核 + 真实浏览器指纹 = Turnstile 完全不触发
2. **无需登录** — guest 模式直接可用，没有 cookie 管理成本
3. **自动节点切换** — 被拦截后立即换节点重试，3 次机会
4. **简洁的 DOM 结构** — `[data-message-author-role='assistant'] .markdown` 直接拿到格式化响应

### Gemini 的痛点

1. **Cookie 依赖** — `GEMINI_COOKIES_JSON` 会过期，过期后所有查询静默失败
2. **复杂的输入逻辑** — Quill 编辑器需要 3 种 JS 注入方法兜底（execCommand → paste 事件 → innerHTML）
3. **响应提取困难** — Angular 自定义元素（`model-response`、`message-content`）层级深，选择器需要多级 fallback
4. **固定 60 秒等待** — 不区分短回答和长回答，浪费大量时间

---

## 三、可借鉴到 Gemini 的改进 (TODO)

### P0: 确认 Camoufox 对 Google 的效果

- [ ] 检查 Gemini 查询日志，确认走的是 Camoufox 还是 Playwright 路径（看 `llm_version` 前缀）
- [ ] 对比 Camoufox 和 Playwright 模式下 Gemini 的成功率
- [ ] 如果 Google 不依赖 Cloudflare 风控，Camoufox 的反指纹对 Google 自有检测效果可能有限，需实测

### P1: 动态响应完成检测（替代固定等待）

当前 Gemini `wait_after_submit = 60000` 是固定等待，浪费时间。可以改为：

```
思路:
1. 监测 DOM 变化速率 — streaming 输出时 DOM 频繁变化，停止后稳定
2. 检测 "停止生成" / "Stop generating" 按钮的出现和消失
3. 设最大超时 60s 作为兜底，但大部分查询应在 10-30s 内完成
```

ChatGPT 也可以用同样的策略，从 25s 固定等待改为动态检测。

### P2: Cookie 生命周期管理

- [ ] 查询前先验证 cookie 有效性（轻量 HEAD 请求检查是否 302 到登录页）
- [ ] Cookie 失效时自动标记 Gemini 为不可用，跳过后续查询
- [ ] 添加告警机制（日志 + 可选 webhook），cookie 过期时通知运维
- [ ] 探索自动刷新 cookie 的可行性（headful 浏览器 + Google 登录流程）

### P3: 探索 Gemini guest 模式

- [ ] 测试 `https://gemini.google.com/app` 在无 cookie 状态下是否有 guest 对话能力
- [ ] 如果不行，测试 Google AI Studio (`https://aistudio.google.com`) 是否有免登录入口
- [ ] 评估 Gemini API free tier 作为 web scraping 的替代方案

### P4: 响应提取质量优化

- [ ] 对比 ChatGPT 和 Gemini 的 `raw_text` 输出格式差异
- [ ] Gemini 响应可能包含 Angular 模板残留（如 `<!---->` 注释、空 span），需要后处理清洗
- [ ] 考虑统一的 Markdown 后处理管道：HTML → clean text → structured Markdown

### P5: 通用改进

- [ ] 所有 LLM 的 `wait_after_submit` 改为动态检测 + 最大超时
- [ ] 添加响应质量评分（长度、是否包含有意义内容、是否为错误页面）
- [ ] 截图对比：自动对比当次截图与历史截图，检测页面结构变化（LLM 改版预警）
- [ ] Perplexity 也无需登录，可以参考 ChatGPT 的模式确认其稳定性

---

## 四、Dockerfile 依赖清单

Camoufox (Firefox) 和 Playwright (Chromium) 共存所需的系统库：

```dockerfile
RUN apt-get update && apt-get install -y \
    # 通用
    wget curl gnupg ca-certificates \
    # Chromium (Playwright)
    libglib2.0-0 libnss3 libnspr4 libdbus-1-3 \
    libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    # Firefox (Camoufox) — 额外需要
    libgtk-3-0 libpango-1.0-0 libcairo2 libx11-xcb1 \
    && rm -rf /var/lib/apt/lists/*
```

---

## 五、关键配置参考

### Clash 代理订阅 (`clash/config.yaml`)

```yaml
proxy-providers:
  ninja-sub:
    type: http
    url: "<订阅URL>?clash=1"
    path: ./proxies/ninja.yaml
    interval: 3600
    health-check:
      enable: true
      interval: 300
      url: "http://www.gstatic.com/generate_204"
```

### Docker Compose worker 配置

```yaml
worker:
  shm_size: '2gb'          # 防止 Chromium Page crashed
  # volumes 中 clash 目录不能加 :ro，否则 Mihomo 无法写入节点缓存
```

### Camoufox 参数（生产验证通过）

```python
{
    "headless": True,
    "humanize": True,
    "block_images": False,
    "os": "windows",
    "locale": "en-US",
    "proxy": {"server": proxy_url},  # 可选
}
```

**不要使用的参数**:
- `screen`: 传 dict 会导致 browserforge 崩溃，需要 `Screen` 对象或不传（自动生成）
- `geoip`: 需要 `camoufox[geoip]` extra，安装不稳定，手动设 `locale` 即可
