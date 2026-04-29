import { Router, Request, Response } from 'express'
import bcrypt from 'bcryptjs'
import { v4 as uuidv4 } from 'uuid'
import passport from 'passport'
import { Strategy as GoogleStrategy, Profile } from 'passport-google-oauth20'
import db, { UserRow } from '../db'
import { signToken } from '../utils/jwt'
import { requireAuth, AuthRequest } from '../middleware/auth'
import {
  isValidEmailFormat,
  isPersonalEmail,
  sendVerificationEmail,
  sendPasswordResetEmail,
} from '../utils/email'

const router = Router()

// ─── Passport Google OAuth ────────────────────────────────────────────────────

if (process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET) {
  passport.use(
    new GoogleStrategy(
      {
        clientID: process.env.GOOGLE_CLIENT_ID,
        clientSecret: process.env.GOOGLE_CLIENT_SECRET,
        callbackURL: process.env.GOOGLE_CALLBACK_URL || 'http://localhost:4000/api/auth/google/callback',
      },
      (_accessToken: string, _refreshToken: string, profile: Profile, done: (err: Error | null, user?: Express.User | false) => void) => {
        try {
          const email = profile.emails?.[0]?.value
          if (!email) return done(new Error('No email returned from Google'))
          if (isPersonalEmail(email)) return done(new Error('PERSONAL_EMAIL'))

          let user = db.getUserByEmail(email)
          if (!user) {
            user = db.createUser({
              email: email.toLowerCase(),
              password: null,
              name: profile.displayName || null,
              company: null,
              role: 'user',
              provider: 'google',
              google_id: profile.id,
              verified: 1,
            })
          } else if (!user.google_id) {
            db.updateUser(user.id, { google_id: profile.id, verified: 1 })
            user = db.getUserById(user.id)!
          }

          return done(null, user as unknown as Express.User)
        } catch (err) {
          return done(err as Error)
        }
      }
    )
  )
}

passport.serializeUser((user: Express.User, done) => done(null, (user as UserRow).id))
passport.deserializeUser((id: number, done) => {
  const user = db.getUserById(id)
  done(null, user as Express.User | undefined)
})

// ─── POST /register ────────────────────────────────────────────────────────────

router.post('/register', async (req: Request, res: Response): Promise<void> => {
  const { email } = req.body as { email?: string }

  if (!email || !isValidEmailFormat(email)) {
    res.status(400).json({ error: 'INVALID_EMAIL', message: '请输入有效的邮箱地址 / Please enter a valid email' })
    return
  }

  if (isPersonalEmail(email)) {
    res.status(400).json({ error: 'PERSONAL_EMAIL', message: '请输入有效的公司邮箱 / Please enter a valid work email' })
    return
  }

  if (db.getUserByEmail(email)) {
    res.status(409).json({ error: 'EMAIL_EXISTS', message: '该邮箱已注册 / Email already registered' })
    return
  }

  try {
    const user = db.createUser({
      email: email.toLowerCase(),
      password: null,
      name: null,
      company: null,
      role: 'user',
      provider: 'email',
      google_id: null,
      verified: 0,
    })

    const token = uuidv4()
    const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()
    db.createVerificationToken(user.id, token, expiresAt)

    const frontendUrl = process.env.FRONTEND_URL || 'http://localhost:5173'
    await sendVerificationEmail(email, token, frontendUrl)

    res.status(201).json({
      message: '验证邮件已发送，请查收 / Verification email sent',
      email: email.toLowerCase(),
    })
  } catch (err) {
    console.error('Register error:', err)
    res.status(500).json({ error: 'SERVER_ERROR', message: '服务器异常 / Server error' })
  }
})

// ─── POST /login ───────────────────────────────────────────────────────────────

router.post('/login', async (req: Request, res: Response): Promise<void> => {
  const { email, password } = req.body as { email?: string; password?: string }

  if (!email || !isValidEmailFormat(email)) {
    res.status(400).json({ error: 'INVALID_EMAIL', message: '请输入有效的邮箱地址 / Please enter a valid email' })
    return
  }

  if (isPersonalEmail(email)) {
    res.status(400).json({ error: 'PERSONAL_EMAIL', message: '请输入有效的公司邮箱 / Please enter a valid work email' })
    return
  }

  const user = db.getUserByEmail(email)

  if (!user) {
    res.status(404).json({ error: 'NOT_FOUND', message: '该邮箱未注册 / Email not registered' })
    return
  }

  if (user.password) {
    if (!password) {
      res.status(400).json({ error: 'PASSWORD_REQUIRED', message: '请输入密码 / Password required' })
      return
    }
    const valid = await bcrypt.compare(password, user.password)
    if (!valid) {
      res.status(401).json({ error: 'INVALID_CREDENTIALS', message: '邮箱或密码错误 / Invalid credentials' })
      return
    }
  }

  const token = signToken({ userId: user.id, email: user.email })
  res.json({ token, user: { id: user.id, email: user.email, name: user.name, company: user.company } })
})

// ─── POST /forgot-password ─────────────────────────────────────────────────────

router.post('/forgot-password', async (req: Request, res: Response): Promise<void> => {
  const { email } = req.body as { email?: string }

  if (!email || !isValidEmailFormat(email)) {
    res.status(400).json({ error: 'INVALID_EMAIL', message: '请输入有效的邮箱地址' })
    return
  }

  const user = db.getUserByEmail(email)
  if (user) {
    try {
      const token = uuidv4()
      const expiresAt = new Date(Date.now() + 60 * 60 * 1000).toISOString()
      db.createResetToken(user.id, token, expiresAt)
      const frontendUrl = process.env.FRONTEND_URL || 'http://localhost:5173'
      await sendPasswordResetEmail(email, token, frontendUrl)
    } catch (err) {
      console.error('Forgot password error:', err)
    }
  }

  res.json({ message: '如果该邮箱已注册，重置链接已发送 / If registered, reset link has been sent' })
})

// ─── POST /reset-password ──────────────────────────────────────────────────────

router.post('/reset-password', async (req: Request, res: Response): Promise<void> => {
  const { token, password } = req.body as { token?: string; password?: string }

  if (!token || !password) {
    res.status(400).json({ error: 'MISSING_FIELDS', message: 'Token and password are required' })
    return
  }

  if (password.length < 8) {
    res.status(400).json({ error: 'WEAK_PASSWORD', message: '密码至少8位 / Password must be at least 8 characters' })
    return
  }

  const resetToken = db.getResetToken(token)
  if (!resetToken || resetToken.used || new Date(resetToken.expires_at) < new Date()) {
    res.status(400).json({ error: 'INVALID_TOKEN', message: '链接已失效或过期 / Link is invalid or expired' })
    return
  }

  try {
    const hashed = await bcrypt.hash(password, 12)
    db.updateUser(resetToken.user_id, { password: hashed, verified: 1 })
    db.markResetTokenUsed(token)
    res.json({ message: '密码重置成功 / Password reset successfully' })
  } catch (err) {
    console.error('Reset password error:', err)
    res.status(500).json({ error: 'SERVER_ERROR', message: '服务器异常 / Server error' })
  }
})

// ─── GET /check-email ──────────────────────────────────────────────────────────

router.get('/check-email', (req: Request, res: Response) => {
  const email = req.query.email as string
  if (!email || !isValidEmailFormat(email) || isPersonalEmail(email)) {
    res.json({ exists: false })
    return
  }
  const user = db.getUserByEmail(email)
  res.json({ exists: !!user })
})

// ─── POST /resend-verification ─────────────────────────────────────────────────

router.post('/resend-verification', async (req: Request, res: Response): Promise<void> => {
  const { email } = req.body as { email?: string }
  if (!email) { res.status(400).json({ error: 'MISSING_EMAIL' }); return }

  const user = db.getUserByEmail(email)
  if (user && !user.verified) {
    try {
      const token = uuidv4()
      const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()
      db.createVerificationToken(user.id, token, expiresAt)
      const frontendUrl = process.env.FRONTEND_URL || 'http://localhost:5173'
      await sendVerificationEmail(email, token, frontendUrl)
    } catch (err) {
      console.error('Resend verification error:', err)
    }
  }
  res.json({ message: 'If the email exists and is unverified, a new verification email was sent.' })
})

// ─── POST /setup ───────────────────────────────────────────────────────────────

router.post('/setup', async (req: Request, res: Response): Promise<void> => {
  const { token, email, password, name, company, newsletter } = req.body as {
    token?: string
    email?: string
    password?: string
    name?: string
    company?: string
    newsletter?: boolean
  }

  if (!token || !email || !password || !name || !company) {
    res.status(400).json({ error: 'MISSING_FIELDS', message: '请填写所有必填字段 / Please fill all required fields' })
    return
  }

  if (password.length < 8) {
    res.status(400).json({ error: 'WEAK_PASSWORD', message: '密码至少8位 / Password must be at least 8 characters' })
    return
  }

  const verToken = db.getVerificationToken(token)
  if (!verToken || new Date(verToken.expires_at) < new Date()) {
    res.status(400).json({ error: 'INVALID_TOKEN', message: '链接已失效或过期 / Link is invalid or expired' })
    return
  }

  const user = db.getUserById(verToken.user_id)
  if (!user) {
    res.status(404).json({ error: 'NOT_FOUND', message: 'User not found' })
    return
  }

  try {
    const hashed = await bcrypt.hash(password, 12)
    db.updateUser(user.id, { password: hashed, name, company, verified: 1 })
    const jwtToken = signToken({ userId: user.id, email: user.email })
    const updatedUser = db.getUserById(user.id)!
    res.json({
      token: jwtToken,
      user: { id: updatedUser.id, email: updatedUser.email, name: updatedUser.name, company: updatedUser.company }
    })
  } catch (err) {
    console.error('Setup error:', err)
    res.status(500).json({ error: 'SERVER_ERROR', message: '服务器异常 / Server error' })
  }
})

// ─── GET /me ───────────────────────────────────────────────────────────────────

router.get('/me', requireAuth, (req: AuthRequest, res: Response): void => {
  const user = db.getUserById(req.userId!)
  if (!user) {
    res.status(404).json({ error: 'NOT_FOUND', message: 'User not found' })
    return
  }
  res.json({ id: user.id, email: user.email, name: user.name, company: user.company, createdAt: user.created_at })
})

// ─── Google OAuth routes ───────────────────────────────────────────────────────

router.get('/google', passport.authenticate('google', { scope: ['profile', 'email'], session: false }))

router.get(
  '/google/callback',
  (req: Request, res: Response, next: (err?: unknown) => void) => {
    passport.authenticate('google', { session: false }, (err: Error | null, user: UserRow | false) => {
      const frontendUrl = process.env.FRONTEND_URL || 'http://localhost:5173'
      if (err) {
        const msg = err.message === 'PERSONAL_EMAIL' ? 'personal_email' : 'oauth_failed'
        return res.redirect(`${frontendUrl}/login?error=${msg}`)
      }
      if (!user) return res.redirect(`${frontendUrl}/login?error=oauth_failed`)
      const token = signToken({ userId: user.id, email: user.email })
      return res.redirect(`${frontendUrl}/dashboard?token=${token}`)
    })(req, res, next)
  }
)

// ─── POST /dev-seed (dev only) ────────────────────────────────────────────────

if (process.env.NODE_ENV !== 'production') {
  router.post('/dev-seed', async (req: Request, res: Response): Promise<void> => {
    const { email, password, name, company } = req.body as {
      email?: string; password?: string; name?: string; company?: string
    }

    const e = email || 'test@lianwei.com'
    const p = password || 'Test1234!'
    const n = name || 'Test User'
    const c = company || 'Lianwei'

    let user = db.getUserByEmail(e)
    if (user) {
      const token = signToken({ userId: user.id, email: user.email })
      res.json({ message: 'User already exists', token, user: { id: user.id, email: user.email, name: user.name, company: user.company } })
      return
    }

    const hashed = await bcrypt.hash(p, 12)
    user = db.createUser({ email: e, password: hashed, name: n, company: c, role: 'user', provider: 'email', google_id: null, verified: 1 })
    const token = signToken({ userId: user.id, email: user.email })
    res.json({ message: 'Test user created', token, user: { id: user.id, email: user.email, name: user.name, company: user.company } })
  })
}

export default router
