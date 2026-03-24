import 'dotenv/config'
import express from 'express'
import cors from 'cors'
import passport from 'passport'
import rateLimit from 'express-rate-limit'
import authRouter from './routes/auth'

const app = express()
const PORT = Number(process.env.PORT) || 4000
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3000'

// ─── Middleware ────────────────────────────────────────────────────────────────

app.use(cors({
  origin: FRONTEND_URL,
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization'],
}))

app.use(express.json({ limit: '1mb' }))
app.use(express.urlencoded({ extended: true }))

// Initialize Passport (no sessions — JWT only)
app.use(passport.initialize())

// ─── Rate limiting ─────────────────────────────────────────────────────────────

const authLimiter = rateLimit({
  windowMs: 60 * 1000,       // 1 minute
  max: 20,                    // max 20 requests per minute per IP
  message: { error: 'RATE_LIMITED', message: 'Too many requests, please try again later' },
  standardHeaders: true,
  legacyHeaders: false,
})

// Stricter limiter for sensitive endpoints
const sensitiveAuthLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 10,
  message: { error: 'RATE_LIMITED', message: 'Too many attempts, please try again in 1 minute' },
  standardHeaders: true,
  legacyHeaders: false,
})

// ─── Routes ────────────────────────────────────────────────────────────────────

app.use('/api/auth/login', sensitiveAuthLimiter)
app.use('/api/auth/register', sensitiveAuthLimiter)
app.use('/api/auth/forgot-password', sensitiveAuthLimiter)
app.use('/api/auth', authLimiter, authRouter)

// Health check
app.get('/health', (_req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() })
})

// 404 handler
app.use((_req, res) => {
  res.status(404).json({ error: 'NOT_FOUND', message: 'Route not found' })
})

// Global error handler
app.use((err: Error, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  console.error('Unhandled error:', err)
  res.status(500).json({ error: 'SERVER_ERROR', message: 'Internal server error' })
})

// ─── Start ─────────────────────────────────────────────────────────────────────

app.listen(PORT, () => {
  console.log(`GenPano API server running on http://localhost:${PORT}`)
  console.log(`Environment: ${process.env.NODE_ENV || 'development'}`)
  console.log(`CORS origin: ${FRONTEND_URL}`)
  if (!process.env.GOOGLE_CLIENT_ID) {
    console.warn('GOOGLE_CLIENT_ID not set — Google OAuth is disabled')
  }
})

export default app
