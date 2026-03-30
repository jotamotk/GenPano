import nodemailer from 'nodemailer'

// Personal email domains that are blocked for work registration
export const PERSONAL_DOMAINS = new Set([
  'gmail.com', 'googlemail.com',
  'hotmail.com', 'hotmail.cn', 'hotmail.co.uk',
  'outlook.com', 'outlook.cn',
  'yahoo.com', 'yahoo.cn', 'yahoo.com.cn',
  'qq.com', 'foxmail.com',
  '163.com', '126.com', '139.com',
  'sina.com', 'sina.cn',
  'sohu.com',
  'icloud.com', 'me.com', 'mac.com',
  'live.com', 'msn.com',
  'protonmail.com', 'proton.me',
  'yandex.com', 'yandex.ru',
  'mail.com', 'email.com',
  '21cn.com',
  'aliyun.com',
  'tom.com',
])

export function isPersonalEmail(email: string): boolean {
  const domain = email.split('@')[1]?.toLowerCase()
  if (!domain) return true
  return PERSONAL_DOMAINS.has(domain)
}

export function isValidEmailFormat(email: string): boolean {
  return /^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/.test(email)
}

// Create mail transporter — uses Ethereal in dev if no SMTP is configured
let transporter: nodemailer.Transporter | null = null

export async function getTransporter(): Promise<nodemailer.Transporter> {
  if (transporter) return transporter

  if (process.env.SMTP_HOST && process.env.SMTP_USER && process.env.SMTP_PASS) {
    transporter = nodemailer.createTransport({
      host: process.env.SMTP_HOST,
      port: Number(process.env.SMTP_PORT) || 587,
      secure: Number(process.env.SMTP_PORT) === 465,
      auth: {
        user: process.env.SMTP_USER,
        pass: process.env.SMTP_PASS,
      },
    })
  } else {
    // Use Ethereal test account for development
    const testAccount = await nodemailer.createTestAccount()
    transporter = nodemailer.createTransport({
      host: 'smtp.ethereal.email',
      port: 587,
      secure: false,
      auth: {
        user: testAccount.user,
        pass: testAccount.pass,
      },
    })
    console.log('Using Ethereal test account:', testAccount.user)
    console.log('Preview emails at: https://ethereal.email')
  }

  return transporter
}

export async function sendVerificationEmail(
  email: string,
  token: string,
  frontendUrl: string,
  userName?: string
): Promise<void> {
  const t = await getTransporter()
  const link = `${frontendUrl}/setup?token=${token}`
  const displayName = userName || email.split('@')[0]

  const info = await t.sendMail({
    from: process.env.EMAIL_FROM || '"GenPano" <noreply@genpano.com>',
    to: email,
    subject: 'Verify your GenPano account / 验证您的 GenPano 账号',
    html: `
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#F5F5F5;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#F5F5F5;padding:40px 20px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background-color:#FFFFFF;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

<!-- Header -->
<tr><td style="background:linear-gradient(135deg,#6C5CE7,#8B7CF7);padding:28px 40px;text-align:center;">
  <table cellpadding="0" cellspacing="0" style="margin:0 auto;">
  <tr>
    <td style="width:36px;height:36px;background:rgba(255,255,255,0.2);border-radius:10px;text-align:center;vertical-align:middle;">
      <span style="color:#FFFFFF;font-weight:700;font-size:14px;">&#9671;</span>
    </td>
    <td style="padding-left:10px;color:#FFFFFF;font-size:22px;font-weight:700;letter-spacing:-0.3px;">GenPano</td>
  </tr>
  </table>
</td></tr>

<!-- Body -->
<tr><td style="padding:40px;">
  <h1 style="margin:0 0 24px;font-size:24px;font-weight:700;color:#1A1A2E;">欢迎来到 GenPano</h1>
  <p style="margin:0 0 8px;font-size:15px;color:#4B5563;">尊敬的 ${displayName}，</p>
  <p style="margin:0 0 16px;font-size:15px;color:#4B5563;">感谢您注册 GenPano</p>
  <p style="margin:0 0 32px;font-size:15px;color:#4B5563;line-height:1.6;">为了确保您的帐户安全并开始使用我们的服务，请单击下面的按钮验证您的工作电子邮件。</p>

  <!-- CTA Button -->
  <table cellpadding="0" cellspacing="0">
  <tr><td style="background-color:#6C5CE7;border-radius:8px;">
    <a href="${link}" style="display:inline-block;padding:14px 32px;color:#FFFFFF;font-size:15px;font-weight:600;text-decoration:none;">
      验证邮箱&nbsp;&nbsp;&rarr;
    </a>
  </td></tr>
  </table>

  <!-- Guide Section -->
  <div style="margin-top:36px;padding-top:28px;border-top:1px solid #E5E7EB;">
    <p style="margin:0 0 16px;font-size:15px;font-weight:700;color:#1A1A2E;">您可以立即开始：</p>
    <table cellpadding="0" cellspacing="0" style="width:100%;">
    <tr>
      <td style="padding:8px 0;vertical-align:top;width:28px;">
        <span style="display:inline-block;width:22px;height:22px;border:2px solid #6C5CE7;border-radius:50%;text-align:center;line-height:22px;font-size:12px;color:#6C5CE7;">&#10003;</span>
      </td>
      <td style="padding:8px 0 8px 8px;">
        <p style="margin:0;font-size:14px;font-weight:600;color:#1A1A2E;">设置您的GEO品牌</p>
        <p style="margin:2px 0 0;font-size:13px;color:#6B7280;">设置您要检测的话题和提示</p>
      </td>
    </tr>
    <tr>
      <td style="padding:8px 0;vertical-align:top;width:28px;">
        <span style="display:inline-block;width:22px;height:22px;border:2px solid #6C5CE7;border-radius:50%;text-align:center;line-height:22px;font-size:12px;color:#6C5CE7;">&#10003;</span>
      </td>
      <td style="padding:8px 0 8px 8px;">
        <p style="margin:0;font-size:14px;font-weight:600;color:#1A1A2E;">探索核心GEO工具</p>
        <p style="margin:2px 0 0;font-size:13px;color:#6B7280;">查看您公司的GEO指标和仪表板</p>
      </td>
    </tr>
    </table>
  </div>
</td></tr>

<!-- Footer -->
<tr><td style="background-color:#F9FAFB;padding:24px 40px;text-align:center;">
  <p style="margin:0 0 12px;font-size:12px;color:#9CA3AF;line-height:1.5;">如果您没有请求此电子邮件，请忽略它。验证链接将在24小时后过期。</p>
  <p style="margin:0 0 8px;">
    <a href="#" style="font-size:12px;color:#6B7280;text-decoration:none;">帮助中心</a>
    <span style="color:#D1D5DB;margin:0 8px;">|</span>
    <a href="#" style="font-size:12px;color:#6B7280;text-decoration:none;">隐私政策</a>
  </p>
  <p style="margin:0;font-size:11px;color:#D1D5DB;">&copy; 2026 EnterpriseOS，版权所有。</p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>
    `,
  })

  if (process.env.NODE_ENV !== 'production') {
    console.log('Verification email preview URL:', nodemailer.getTestMessageUrl(info))
  }
}

export async function sendPasswordResetEmail(
  email: string,
  token: string,
  frontendUrl: string,
  userName?: string
): Promise<void> {
  const t = await getTransporter()
  const link = `${frontendUrl}/reset-password?token=${token}`
  const displayName = userName || email.split('@')[0]

  const info = await t.sendMail({
    from: process.env.EMAIL_FROM || '"GenPano" <noreply@genpano.com>',
    to: email,
    subject: 'Reset your GenPano password / 重置您的 GenPano 密码',
    html: `
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#F5F5F5;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#F5F5F5;padding:40px 20px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background-color:#FFFFFF;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

<!-- Header -->
<tr><td style="background:linear-gradient(135deg,#6C5CE7,#8B7CF7);padding:28px 40px;text-align:center;">
  <table cellpadding="0" cellspacing="0" style="margin:0 auto;">
  <tr>
    <td style="width:36px;height:36px;background:rgba(255,255,255,0.2);border-radius:10px;text-align:center;vertical-align:middle;">
      <span style="color:#FFFFFF;font-weight:700;font-size:14px;">&#9671;</span>
    </td>
    <td style="padding-left:10px;color:#FFFFFF;font-size:22px;font-weight:700;letter-spacing:-0.3px;">GenPano</td>
  </tr>
  </table>
</td></tr>

<!-- Body -->
<tr><td style="padding:40px;">
  <h1 style="margin:0 0 24px;font-size:24px;font-weight:700;color:#1A1A2E;">重置密码</h1>
  <p style="margin:0 0 16px;font-size:15px;color:#4B5563;">尊敬的 ${displayName}：</p>
  <p style="margin:0 0 16px;font-size:15px;color:#4B5563;line-height:1.6;">我们收到了您重置创全景账户密码的请求。</p>
  <p style="margin:0 0 32px;font-size:15px;color:#4B5563;line-height:1.6;">为确保您账户的安全，请点击下方按钮设置新密码。如果这不是您的操作，请忽略此邮件。</p>

  <!-- CTA Button -->
  <table cellpadding="0" cellspacing="0">
  <tr><td style="background-color:#6C5CE7;border-radius:8px;">
    <a href="${link}" style="display:inline-block;padding:14px 32px;color:#FFFFFF;font-size:15px;font-weight:600;text-decoration:none;">
      重置密码&nbsp;&nbsp;&rarr;
    </a>
  </td></tr>
  </table>

  <!-- Security Tips -->
  <div style="margin-top:36px;padding-top:28px;border-top:1px solid #E5E7EB;">
    <p style="margin:0 0 16px;font-size:15px;font-weight:700;color:#1A1A2E;">安全提示：</p>
    <table cellpadding="0" cellspacing="0" style="width:100%;">
    <tr>
      <td style="padding:6px 0;vertical-align:middle;width:28px;">
        <span style="font-size:16px;">&#9200;</span>
      </td>
      <td style="padding:6px 0 6px 8px;font-size:14px;color:#4B5563;">此重置链接将在 1 小时后过期</td>
    </tr>
    <tr>
      <td style="padding:6px 0;vertical-align:middle;width:28px;">
        <span style="font-size:16px;">&#128274;</span>
      </td>
      <td style="padding:6px 0 6px 8px;font-size:14px;color:#4B5563;">如果您没有要求重置密码，请立即联系我们的支持团队</td>
    </tr>
    </table>
  </div>
</td></tr>

<!-- Footer -->
<tr><td style="background-color:#F9FAFB;padding:24px 40px;text-align:center;">
  <p style="margin:0 0 12px;font-size:12px;color:#9CA3AF;line-height:1.5;">如果您没有要求发送此邮件，请忽略它。密码重置链接将在 1 小时后过期。</p>
  <p style="margin:0 0 8px;">
    <a href="#" style="font-size:12px;color:#6B7280;text-decoration:none;">帮助中心</a>
    <span style="color:#D1D5DB;margin:0 8px;">|</span>
    <a href="#" style="font-size:12px;color:#6B7280;text-decoration:none;">隐私政策</a>
  </p>
  <p style="margin:0;font-size:11px;color:#D1D5DB;">&copy; 2026 EnterpriseOS，保留所有权利。</p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>
    `,
  })

  if (process.env.NODE_ENV !== 'production') {
    console.log('Password reset email preview URL:', nodemailer.getTestMessageUrl(info))
  }
}
