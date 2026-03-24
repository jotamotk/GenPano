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
  frontendUrl: string
): Promise<void> {
  const t = await getTransporter()
  const link = `${frontendUrl}/setup?token=${token}`

  const info = await t.sendMail({
    from: process.env.EMAIL_FROM || '"GenPano" <noreply@genpano.com>',
    to: email,
    subject: 'Verify your GenPano account / 验证您的 GenPano 账号',
    html: `
      <div style="font-family: Inter, system-ui, sans-serif; max-width: 520px; margin: 0 auto; padding: 32px 24px;">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 32px;">
          <div style="width: 32px; height: 32px; border-radius: 8px; background: linear-gradient(135deg, #C9A96E, #8B6914); display: flex; align-items: center; justify-content: center;">
            <span style="color: white; font-weight: bold; font-size: 12px;">GP</span>
          </div>
          <span style="font-weight: 600; color: #1f2937;">GenPano</span>
        </div>
        <h1 style="font-size: 20px; font-weight: 600; color: #111827; margin: 0 0 8px;">Verify your email</h1>
        <p style="color: #6b7280; font-size: 14px; margin: 0 0 24px;">Click the button below to verify your account and get started.</p>
        <a href="${link}" style="display: inline-block; background: #6366f1; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px;">Verify Email</a>
        <p style="color: #9ca3af; font-size: 12px; margin: 24px 0 0;">This link expires in 24 hours. If you did not create a GenPano account, you can safely ignore this email.</p>
      </div>
    `,
  })

  if (process.env.NODE_ENV !== 'production') {
    console.log('Verification email preview URL:', nodemailer.getTestMessageUrl(info))
  }
}

export async function sendPasswordResetEmail(
  email: string,
  token: string,
  frontendUrl: string
): Promise<void> {
  const t = await getTransporter()
  const link = `${frontendUrl}/reset-password?token=${token}`

  const info = await t.sendMail({
    from: process.env.EMAIL_FROM || '"GenPano" <noreply@genpano.com>',
    to: email,
    subject: 'Reset your GenPano password / 重置您的 GenPano 密码',
    html: `
      <div style="font-family: Inter, system-ui, sans-serif; max-width: 520px; margin: 0 auto; padding: 32px 24px;">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 32px;">
          <div style="width: 32px; height: 32px; border-radius: 8px; background: linear-gradient(135deg, #C9A96E, #8B6914); display: flex; align-items: center; justify-content: center;">
            <span style="color: white; font-weight: bold; font-size: 12px;">GP</span>
          </div>
          <span style="font-weight: 600; color: #1f2937;">GenPano</span>
        </div>
        <h1 style="font-size: 20px; font-weight: 600; color: #111827; margin: 0 0 8px;">Reset your password</h1>
        <p style="color: #6b7280; font-size: 14px; margin: 0 0 24px;">Click the button below to reset your password. This link expires in 1 hour.</p>
        <a href="${link}" style="display: inline-block; background: #6366f1; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px;">Reset Password</a>
        <p style="color: #9ca3af; font-size: 12px; margin: 24px 0 0;">If you did not request a password reset, you can safely ignore this email.</p>
      </div>
    `,
  })

  if (process.env.NODE_ENV !== 'production') {
    console.log('Password reset email preview URL:', nodemailer.getTestMessageUrl(info))
  }
}
