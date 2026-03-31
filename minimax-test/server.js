const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');

const app = express();
const PORT = 3099;

// cookies_store is the Docker volume mount; fall back to local dir for dev
const COOKIES_STORE = fs.existsSync('/app/cookies_store') ? '/app/cookies_store' : __dirname;
const COOKIES_FILE = path.join(COOKIES_STORE, 'cookies.json');
const UPLOADS_DIR = path.join(__dirname, 'uploads');
const SCREENSHOTS_DIR = path.join(__dirname, 'screenshots');

// 确保目录存在
[UPLOADS_DIR, SCREENSHOTS_DIR].forEach(dir => {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
});

// 文件上传配置
const upload = multer({
  dest: UPLOADS_DIR,
  limits: { fileSize: 500 * 1024 * 1024 }, // 500MB
});

// 中间件 - json 解析必须在 static 之前
app.use(express.json({ limit: '10mb' }));
app.use(express.static(__dirname));
app.use('/screenshots', express.static(SCREENSHOTS_DIR));

// 主页
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

// Cookie 状态查询
app.get('/api/cookies/status', (req, res) => {
  if (!fs.existsSync(COOKIES_FILE)) {
    return res.json({ exists: false });
  }
  try {
    const cookies = JSON.parse(fs.readFileSync(COOKIES_FILE, 'utf-8'));
    const saved = new Date(fs.statSync(COOKIES_FILE).mtime).toLocaleString('zh-CN');
    res.json({ exists: true, count: cookies.length, savedAt: saved });
  } catch {
    res.json({ exists: false, error: '文件损坏' });
  }
});

// Cookie 上传 - 粘贴 JSON
app.post('/api/cookies/paste', (req, res) => {
  try {
    if (!req.body || !req.body.cookies) {
      return res.json({ success: false, error: '未收到 cookies 数据' });
    }
    let raw = req.body.cookies;
    let cookies = typeof raw === 'string' ? JSON.parse(raw) : raw;
    if (!Array.isArray(cookies)) {
      return res.json({ success: false, error: 'Cookies 格式错误，需要是 JSON 数组' });
    }
    fs.writeFileSync(COOKIES_FILE, JSON.stringify(cookies, null, 2));
    res.json({ success: true, count: cookies.length });
  } catch (err) {
    res.json({ success: false, error: `解析失败: ${err.message}` });
  }
});

// Cookie 上传 - 文件
app.post('/api/cookies/upload', upload.single('cookieFile'), (req, res) => {
  try {
    if (!req.file) {
      return res.json({ success: false, error: '未收到文件' });
    }
    const cookies = JSON.parse(fs.readFileSync(req.file.path, 'utf-8'));
    fs.unlinkSync(req.file.path);
    if (!Array.isArray(cookies)) {
      return res.json({ success: false, error: 'Cookies 格式错误，需要是 JSON 数组' });
    }
    fs.writeFileSync(COOKIES_FILE, JSON.stringify(cookies, null, 2));
    res.json({ success: true, count: cookies.length });
  } catch (err) {
    res.json({ success: false, error: `解析失败: ${err.message}` });
  }
});

// 处理视频上传和 minimax 自动化
app.post('/api/process', upload.single('video'), async (req, res) => {
  if (!req.file) {
    return res.json({ success: false, error: '没有收到视频文件' });
  }

  if (!fs.existsSync(COOKIES_FILE)) {
    return res.json({ success: false, error: '未找到 cookies.json，请先通过页面上方的「Cookie 管理」上传 cookies' });
  }

  const prompt = req.body.prompt;
  if (!prompt) {
    return res.json({ success: false, error: '缺少 prompt' });
  }

  // 直接使用 multer 生成的临时文件路径，避免中文长文件名问题
  const videoPath = req.file.path;

  console.log(`收到视频: ${req.file.originalname} (${(req.file.size / 1024 / 1024).toFixed(1)} MB)`);
  console.log(`Prompt: ${prompt.substring(0, 100)}...`);

  try {
    const result = await processWithMinimax(videoPath, prompt);
    res.json({ success: true, result });
  } catch (err) {
    console.error('处理失败:', err.message);
    const screenshotName = `error-${Date.now()}.png`;
    res.json({
      success: false,
      error: err.message,
      screenshot: screenshotName,
    });
  } finally {
    // 清理上传的文件
    try { fs.unlinkSync(videoPath); } catch {}
  }
});

async function processWithMinimax(videoPath, prompt) {
  const cookies = JSON.parse(fs.readFileSync(COOKIES_FILE, 'utf-8'));

  console.log('启动浏览器...');
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  try {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 900 },
    });

    // 注入 cookies
    await context.addCookies(cookies);
    const page = await context.newPage();

    console.log('打开 agent.minimaxi.com ...');
    await page.goto('https://agent.minimaxi.com/', {
      waitUntil: 'networkidle',
      timeout: 30000,
    });

    // 截图看当前状态
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'step1-loaded.png') });
    console.log('页面已加载，截图保存到 step1-loaded.png');

    // 等待页面加载完成 - 寻找输入框或上传区域
    // 注意：以下选择器可能需要根据 minimaxi.com 的实际 DOM 结构调整
    // 这里提供了多种可能的选择器

    // 尝试找到文件上传入口
    console.log('寻找上传入口...');

    // 方法1: 查找 file input
    const fileInput = await page.$('input[type="file"]');
    if (fileInput) {
      console.log('找到文件上传 input，上传视频...');
      await fileInput.setInputFiles(videoPath);
    } else {
      // 方法2: 查找上传按钮/附件按钮
      const uploadBtn = await page.$('[class*="upload"], [class*="attach"], [class*="file"], button[aria-label*="上传"], button[aria-label*="附件"]');
      if (uploadBtn) {
        console.log('找到上传按钮，点击...');
        await uploadBtn.click();
        await page.waitForTimeout(1000);
        // 等待 file input 出现
        const input = await page.$('input[type="file"]');
        if (input) {
          await input.setInputFiles(videoPath);
        }
      } else {
        console.log('未找到上传入口，尝试直接截图分析页面...');
        await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'no-upload-found.png'), fullPage: true });
        throw new Error('无法找到文件上传入口，请检查 screenshots/no-upload-found.png 并手动调整选择器');
      }
    }

    // 等待文件上传完成
    console.log('等待视频上传...');
    await page.waitForTimeout(5000);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'step2-uploaded.png') });

    // 输入 prompt
    console.log('输入 prompt...');
    const textarea = await page.$('textarea, [contenteditable="true"], input[type="text"][class*="input"], [class*="editor"]');
    if (textarea) {
      await textarea.click();
      await textarea.fill(prompt);
    } else {
      throw new Error('无法找到文本输入框');
    }

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'step3-prompt.png') });

    // 发送/提交
    console.log('提交请求...');
    const sendBtn = await page.$('button[class*="send"], button[class*="submit"], button[type="submit"], [class*="send-btn"]');
    if (sendBtn) {
      await sendBtn.click();
    } else {
      // 尝试按 Enter 发送
      await page.keyboard.press('Enter');
    }

    // 等待结果 - 轮询检测回复
    console.log('等待 Minimax 返回结果...');
    let result = '';
    let lastLength = 0;
    let stableCount = 0;
    const maxWait = 180000; // 最长等待 3 分钟
    const startTime = Date.now();

    while (Date.now() - startTime < maxWait) {
      await page.waitForTimeout(3000);

      // 尝试获取最新的回复内容
      // 这些选择器可能需要根据实际 DOM 调整
      const messages = await page.$$eval(
        '[class*="message"], [class*="response"], [class*="answer"], [class*="reply"], [class*="content"]',
        (els) => els.map(el => el.textContent?.trim()).filter(Boolean)
      );

      if (messages.length > 0) {
        result = messages[messages.length - 1];
      }

      // 检查内容是否稳定（不再变化 = 回复完成）
      if (result.length > 0 && result.length === lastLength) {
        stableCount++;
        if (stableCount >= 3) {
          console.log('回复已稳定，认为完成');
          break;
        }
      } else {
        stableCount = 0;
      }
      lastLength = result.length;

      // 检查是否有加载指示器消失
      const loading = await page.$('[class*="loading"], [class*="typing"], [class*="generating"]');
      if (!loading && result.length > 0 && stableCount >= 1) {
        console.log('加载指示器已消失');
        break;
      }
    }

    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, 'step4-result.png') });

    if (!result) {
      throw new Error('未能获取到回复内容，请检查 screenshots/step4-result.png');
    }

    console.log(`获取到结果 (${result.length} 字符)`);
    return result;

  } finally {
    await browser.close();
    console.log('浏览器已关闭');
  }
}

app.listen(PORT, () => {
  console.log(`\n========================================`);
  console.log(`Minimax 视频解析测试服务已启动`);
  console.log(`访问: http://localhost:${PORT}`);
  console.log(`========================================\n`);
  console.log(`使用前请确保:`);
  console.log(`1. 已运行 npm run collect-cookies 收集登录 cookies`);
  console.log(`2. cookies.json 文件存在于当前目录\n`);
});
