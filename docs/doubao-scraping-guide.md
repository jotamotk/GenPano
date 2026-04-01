# 豆包 (Doubao) 爬取经验总结

> 更新日期: 2026-04-01
> 状态: 已验证成功

---

## 一、核心架构

豆包爬取采用 **Cookie 注入 + 浏览器自动化** 方案：

```
用户手动登录 → EditThisCookie 导出 → Web UI 上传
     ↓
AccountPool 管理 → 注入到 Playwright/Camoufox → 访问 doubao.com/chat
     ↓
自动输入 query → 等待 AI 响应 → 提取文本 + 引用
```

## 二、踩坑与解决方案

### 1. 响应选择器：用 `data-testid` 而非 CSS class

**现象**: 响应提取为空或返回 SSR JSON 乱码

**根因**: 豆包的 CSS class 名是动态哈希（如 `css-1a2b3c`），每次构建都会变。用 `[class*='receive-message']` 之类的选择器无法稳定匹配。

**解决**:
```python
# ❌ 错误 - CSS class 是动态的
"response_selector": "[class*='receive-message'] [class*='content']"

# ✅ 正确 - data-testid 是稳定的
"response_selector": "[data-testid='receive_message'] [data-testid='message_text_content'], [data-testid='receive_message'] .flow-markdown-body"
```

**如何找到正确选择器**: 保存页面完整 HTML（`_save_html`），搜索 `data-testid` 属性，找到包裹 AI 回复的元素。

### 2. SSR JSON 污染：`textContent` vs `innerText`

**现象**: 提取到的文本是一大段 JSON（包含 `byteimg.com`、`conversation_id` 等字段）

**根因**: 豆包使用 SSR（服务端渲染），`<script>` 标签内嵌了大量 JSON 数据。`document.body.textContent` 会包含所有 `<script>` 标签内容，而 `document.body.innerText` 只返回可见文本。

**解决**:
```javascript
// ❌ 会包含 <script> 内容
const text = document.body.textContent;

// ✅ 只包含可见文本
const text = document.body.innerText;
```

### 3. 登录检测：豆包不跳转，而是原地渲染登录页

**现象**: URL 仍然是 `doubao.com/chat`，但页面是登录表单

**根因**: 豆包不像 Google 那样重定向到 `accounts.google.com`，而是在同一个 URL 下渲染登录页。传统的 URL 域名检测无法识别。

**解决**: 通过页面文本内容检测登录关键词：
```python
login_keywords = [
    "登录后免费使用", "用户协议", "隐私政策",
    "抖音一键登录", "豆包账号服务须知",
    "下载豆包电脑版", "你好，我是豆包",
]
matched = [kw for kw in login_keywords if kw in body_text]
if len(matched) >= 2:  # 匹配 2 个以上关键词才判定
    # cookies 过期，需要更新
```

**注意**: 使用 `>= 2` 阈值避免误判 — 正常对话中可能偶尔出现单个关键词。

### 4. Cookies 过期与管理

**现象**: 之前正常运行的 query 突然全部 fail

**关键认知**:
- 豆包 cookies（`sessionid`、`ttwid` 等）有效期通常 **7-30 天**
- 高频自动化访问可能加速 session 失效
- cookies 过期后不会报错，只是渲染出登录页

**管理方案**:
1. **Web UI 上传**: Accounts tab 支持 EditThisCookie JSON 格式，自动转换为 Playwright 格式
2. **保活任务**: Celery Beat 每 6 小时访问一次豆包页面，刷新 session cookies
3. **过期不封禁**: `cookies_expired` 类型的失败不计入 `consecutive_fails`，只设 12 小时 cooldown，避免误封账号

### 5. 反检测措施

**浏览器选择**:
- 海外 LLM（ChatGPT 等）: Camoufox（Firefox 内核，绕 Cloudflare）
- 国内 LLM（豆包等）: Camoufox 同样可用，提供反指纹保护

**关键配置**:
```python
# 国内 LLM 使用中文 locale
locale = "zh-CN"  # 不要用 en-US
timezone_id = "Asia/Shanghai"

# Playwright 隐藏自动化特征
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
```

**人类行为模拟**:
- 鼠标移动到输入框（随机轨迹，5-15 步）
- 打字延迟 50-120ms/字符（不是固定 30ms）
- 提交前随机等待 0.5-1.5 秒
- 页面加载后随机等待 0.8-2 秒

## 三、Cookie 上传流程

### 获取 Cookies

1. Chrome 安装 [EditThisCookie](https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfbg) 扩展
2. 打开 `https://www.doubao.com/chat` 并登录
3. 点击 EditThisCookie 图标 → 导出（复制到剪贴板）

### 上传 Cookies

1. 打开 Query Tool → Accounts tab → Upload Cookies
2. Platform 选择 `Doubao (豆包)`
3. Account Label 填手机号或标识
4. 粘贴 EditThisCookie 导出的 JSON（自动转换格式）
5. 点击 Import

### 格式转换

系统自动处理 EditThisCookie → Playwright 格式转换：
- `sameSite`: `unspecified` → `Lax`, `no_restriction` → `None`
- `expirationDate` → `expires`
- 移除 `storeId`、`hostOnly` 等非 Playwright 字段

## 四、问题排查清单

| 现象 | 可能原因 | 排查方式 |
|------|---------|---------|
| response 是 SSR JSON | fallback 用了 `textContent` | 检查 response_selector 是否匹配 |
| response 包含 "登录后免费使用" | cookies 过期 | 上传新 cookies |
| query 卡在 RUNNING | worker 崩溃或挂起 | `docker compose logs worker` |
| query 直接 FAILED | 无可用账号或 cooldown | Accounts tab 检查状态 |
| UniqueViolationError | 重试时未删除旧 response | 已修复（DELETE before INSERT） |
| PendingRollbackError | session rollback 后访问 lazy 属性 | 已修复（提前缓存 account_id） |

## 五、关键文件

| 文件 | 作用 |
|------|------|
| `geo_tracker/agent/guest_executor.py` | 浏览器自动化核心，cookie 注入、登录检测、响应提取 |
| `geo_tracker/pool/account_pool.py` | 账号轮换调度，失败处理，cookie 持久化 |
| `geo_tracker/tasks/celery_tasks.py` | Celery 任务定义，cookie 保活，每日重置 |
| `geo_tracker/db/models.py` | LLMAccount 模型定义 |
| `query_tool/app.py` | Web UI，Accounts 管理，cookie 上传 API |

## 六、Celery Beat 定时任务

| 任务 | 时间 | 作用 |
|------|------|------|
| `reset_daily_counts` | 每天 UTC 00:00 | 重置所有账号每日查询计数 |
| `cookie_keep_alive` | 每 6 小时 | 访问各平台页面刷新 session cookies |
