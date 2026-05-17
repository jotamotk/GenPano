# LLM Token / Cookies 上传指南

本文档总结 GenPano 支持的所有 LLM 的认证方式和 Token 上传流程。

---

## 总览

| LLM | 认证方式 | 需要 Cookies | 需要 localStorage | AccountPool | 免登录可用 |
|-----|---------|-------------|-------------------|-------------|-----------|
| **DeepSeek** | Cookies + localStorage | ✅ | ✅ `userToken` | ✅ | ❌ |
| **Doubao (豆包)** | Cookies 或环境变量 | ✅ | ❌ | ✅ | ❌ |
| **ChatGPT** | Cookies 或环境变量 | ✅ | ❌ | ❌ (环境变量) | ✅ (免登可用，但无引用) |
| **Gemini** | Cookies 或环境变量 | ✅ | ❌ | ❌ (环境变量) | ✅ (免登可用，但无引用) |
| **Perplexity** | 无需认证 | ❌ | ❌ | ❌ | ✅ |
| **Kimi** | 无需认证 | ❌ | ❌ | ❌ | ✅ |
| **Claude** | Cookies | ✅ | ❌ | ✅ | ❌ |
| **Grok** | Cookies (X/Twitter) | ✅ | ❌ | ✅ | ❌ |
| **智谱 (ChatGLM)** | Cookies | ✅ | ❌ | ✅ | ❌ |

---

## 各 LLM 详细上传流程

### 1. DeepSeek

**认证机制**: Cookies + `localStorage.userToken`（缺一不可）

**获取步骤**:

1. 浏览器登录 https://chat.deepseek.com
2. **获取 Cookies**: 安装 [EditThisCookie](https://www.editthiscookie.com/) 扩展 → 点击导出 → 复制 JSON
3. **获取 localStorage**: F12 打开 Console，执行：
   ```js
   JSON.stringify({userToken: localStorage.getItem("userToken")})
   ```
   复制输出结果

**上传方式**: 管理后台 → Accounts → Import Cookies
- Platform: `deepseek`
- Cookies JSON: 粘贴 EditThisCookie 导出的 JSON
- localStorage JSON: 粘贴 Console 输出的 JSON

**注意事项**:
- `userToken` 是 DeepSeek 身份验证的核心，仅有 Cookies 无法通过认证
- `userToken` 的值本身是一个 JSON 字符串，格式如：`{"value":"xxx","__version":"0"}`
- 建议 Cookie Keep-Alive 间隔不超过 2 小时
- Session cookies（如 `ds_session_id`）导入时系统会自动添加 30 天有效期

---

### 2. Doubao (豆包)

**认证机制**: Cookies

**获取步骤**:

1. 浏览器登录 https://www.doubao.com/chat
2. EditThisCookie 导出 → 复制 JSON

**上传方式**:
- **方式 A（AccountPool）**: 管理后台 → Accounts → Import Cookies
  - Platform: `doubao`
  - Cookies JSON: 粘贴 EditThisCookie JSON
- ~~**方式 B（环境变量）**: 设置 `DOUBAO_COOKIES_JSON` 环境变量（适合单账号部署）~~
  - **DEPRECATED** (Phase 3 cleanup, Refs #1118 / Epic #1110): 已移除。
    豆包/DeepSeek 现统一走 vm_session 执行模式 (ADR-016)，cookies 仅从
    AccountPool + vm_side runner 加载。

**注意事项**:
- 登录跳转域名检测: `passport.volcengine.com`, `sso.volcengine.com`, `passport.douyin.com`
- 支持 SMS 自动登录（需要 LubanSMS 接码）

---

### 3. ChatGPT

**认证机制**: Cookies（可选，提升功能）

**获取步骤**:

1. 浏览器登录 https://chatgpt.com
2. EditThisCookie 导出 → 复制 JSON

**上传方式**: 设置环境变量 `CHATGPT_COOKIES_JSON`

```bash
# .env 文件
CHATGPT_COOKIES_JSON='[{"name":"__Secure-next-auth.session-token","value":"...","domain":".chatgpt.com",...}]'
```

**注意事项**:
- 无 Cookies 也能用（Guest 模式），但没有 Web Browsing 和引用功能
- 有 Cookies 时自动切换为登录态

---

### 4. Gemini

**认证机制**: Google Cookies（可选）

**获取步骤**:

1. 浏览器登录 https://gemini.google.com/app
2. EditThisCookie 导出 → 复制 JSON（需要包含 Google 域名的 cookies）

**上传方式**: 设置环境变量 `GEMINI_COOKIES_JSON`

```bash
# .env 文件
GEMINI_COOKIES_JSON='[{"name":"__Secure-1PSID","value":"...","domain":".google.com",...}]'
```

**注意事项**:
- 无 Cookies 也能用，但可能遇到地区限制
- 登录跳转域名检测: `accounts.google.com`, `signin.google.com`

---

### 5. Perplexity

**认证机制**: 无需认证

直接使用，无需上传任何 Token。

---

### 6. Kimi

**认证机制**: 无需认证

直接使用，无需上传任何 Token。

---

### 7. Claude

**认证机制**: Cookies

**获取步骤**:

1. 浏览器登录 https://claude.ai
2. EditThisCookie 导出 → 复制 JSON

**上传方式**: 管理后台 → Accounts → Import Cookies
- Platform: `claude`
- Cookies JSON: 粘贴 EditThisCookie JSON

---

### 8. Grok

**认证机制**: X (Twitter) Cookies

**获取步骤**:

1. 浏览器登录 https://x.com，然后访问 https://x.com/i/grok
2. EditThisCookie 导出 → 复制 JSON（需要 x.com 域名的 cookies）

**上传方式**: 管理后台 → Accounts → Import Cookies
- Platform: `grok`
- Cookies JSON: 粘贴 EditThisCookie JSON

---

### 9. 智谱 (ChatGLM)

**认证机制**: Cookies

**获取步骤**:

1. 浏览器登录 https://chatglm.cn
2. EditThisCookie 导出 → 复制 JSON

**上传方式**: 管理后台 → Accounts → Import Cookies
- Platform: `zhipu`
- Cookies JSON: 粘贴 EditThisCookie JSON

---

## 通用操作参考

### EditThisCookie 导出 Cookies

1. Chrome 安装 [EditThisCookie](https://www.editthiscookie.com/) 扩展
2. 访问目标 LLM 网站并登录
3. 点击 EditThisCookie 图标 → 点击"导出"按钮（剪贴板图标）
4. 粘贴到管理后台的 Cookies JSON 输入框

### Console 获取 localStorage

```js
// DeepSeek userToken
JSON.stringify({userToken: localStorage.getItem("userToken")})

// 查看所有 localStorage keys（调试用）
Object.keys(localStorage)
```

> **提示**: `document.cookie` 无法获取 `httpOnly` 的 cookies，必须用 EditThisCookie 扩展导出。

### 允许粘贴（部分网站禁止粘贴）

如果 Console 不让粘贴，输入以下内容后回车，再粘贴命令：

```
allow pasting
```

---

## Cookie 保活策略

系统通过 Celery Beat 定时任务 `cookie_keep_alive` 自动刷新 Cookies：
- 执行频率: 每 **2 小时**
- 刷新方式: 用已有 Cookies 访问 LLM 页面，获取更新后的 Cookies 回写数据库
- localStorage 数据在刷新时会被保留，不会丢失
