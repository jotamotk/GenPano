/**
 * Cookie 收集脚本
 *
 * 运行此脚本会打开一个浏览器窗口，你手动登录 agent.minimaxi.com，
 * 登录成功后按 Enter 键，脚本会自动保存 cookies 到 cookies.json。
 *
 * 使用方法: npm run collect-cookies
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const readline = require('readline');

const COOKIES_FILE = path.join(__dirname, 'cookies.json');
const TARGET_URL = 'https://agent.minimaxi.com/';

async function main() {
  console.log('正在启动浏览器...');

  const browser = await chromium.launch({
    headless: false, // 需要可视化窗口来手动登录
  });

  const context = await browser.newContext();
  const page = await context.newPage();

  console.log(`正在打开 ${TARGET_URL} ...`);
  await page.goto(TARGET_URL, { waitUntil: 'networkidle' });

  console.log('\n========================================');
  console.log('请在浏览器窗口中登录你的账号');
  console.log('登录完成后，回到终端按 Enter 键保存 cookies');
  console.log('========================================\n');

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  await new Promise((resolve) => rl.question('登录完成后按 Enter 继续...', resolve));
  rl.close();

  // 保存 cookies
  const cookies = await context.cookies();
  fs.writeFileSync(COOKIES_FILE, JSON.stringify(cookies, null, 2));
  console.log(`\nCookies 已保存到 ${COOKIES_FILE} (共 ${cookies.length} 个)`);

  await browser.close();
  console.log('浏览器已关闭');
}

main().catch(console.error);
