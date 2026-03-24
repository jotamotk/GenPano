# GenPano — GEO Monitoring Tool

A full-stack authentication system for GenPano, a GEO (Generative Engine Optimization) monitoring tool that tracks brand visibility in AI-generated content.

## Project Structure

```
genpano/
├── PRD.md                    # Product Requirements Document (Chinese/English)
├── README.md                 # This file
├── frontend/                 # React + TypeScript + Vite + Tailwind CSS
│   ├── src/
│   │   ├── api/auth.ts       # Axios API client
│   │   ├── components/
│   │   │   ├── AuthLayout.tsx      # Split-panel layout (beige left / white right)
│   │   │   ├── LanguageSwitcher.tsx
│   │   │   ├── ParticleArt.tsx     # CSS-animated 3D particle sculpture
│   │   │   └── Toast.tsx           # Toast notification system
│   │   ├── context/
│   │   │   ├── AuthContext.tsx     # JWT auth state
│   │   │   └── LanguageContext.tsx # i18n state (zh/en)
│   │   ├── hooks/
│   │   │   └── useEmailValidation.ts  # Work email validation hook
│   │   ├── i18n/
│   │   │   ├── zh.ts          # Chinese translations
│   │   │   ├── en.ts          # English translations
│   │   │   └── index.ts
│   │   ├── pages/
│   │   │   ├── LoginPage.tsx
│   │   │   ├── RegisterPage.tsx
│   │   │   ├── ForgotPasswordPage.tsx
│   │   │   └── DashboardPage.tsx
│   │   └── App.tsx            # Router + protected routes
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.ts         # Dev server on port 3000, proxies /api → 4000
└── backend/                  # Node.js + Express + TypeScript + SQLite
    ├── src/
    │   ├── db/
    │   │   ├── index.ts       # better-sqlite3 connection
    │   │   └── init.ts        # Schema creation
    │   ├── middleware/
    │   │   └── auth.ts        # JWT requireAuth middleware
    │   ├── routes/
    │   │   └── auth.ts        # All auth endpoints + Google OAuth
    │   ├── utils/
    │   │   ├── email.ts       # Nodemailer (Ethereal in dev / SMTP in prod)
    │   │   └── jwt.ts         # Sign/verify JWT tokens
    │   └── index.ts           # Express app entry point
    ├── .env.example
    └── package.json
```

## Prerequisites

- Node.js 18+ (20 LTS recommended)
- npm 9+

## Quick Start

### 1. Backend Setup

```bash
cd backend

# Install dependencies
npm install

# Copy and configure environment variables
cp .env.example .env
# Edit .env — at minimum set JWT_SECRET to a strong random string

# Start the development server (port 4000)
npm run dev
```

On first start, the SQLite database is automatically created at `./data/genpano.db`.

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start the development server (port 3000)
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

The Vite dev server proxies all `/api/*` requests to `http://localhost:4000`.

## Environment Variables (backend/.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `4000` | Backend server port |
| `NODE_ENV` | `development` | Environment |
| `FRONTEND_URL` | `http://localhost:3000` | Frontend URL for CORS and email links |
| `JWT_SECRET` | *(required in prod)* | Secret key for JWT signing (min 32 chars) |
| `JWT_EXPIRES_IN` | `7d` | Token expiry duration |
| `GOOGLE_CLIENT_ID` | — | Google OAuth client ID (optional) |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret (optional) |
| `GOOGLE_CALLBACK_URL` | `http://localhost:4000/api/auth/google/callback` | OAuth callback URL |
| `SMTP_HOST` | — | SMTP host (leave empty to use Ethereal in dev) |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | — | SMTP username |
| `SMTP_PASS` | — | SMTP password |
| `EMAIL_FROM` | `noreply@genpano.com` | Sender address |
| `DB_PATH` | `./data/genpano.db` | SQLite database path |

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/auth/register` | — | Register with work email |
| `POST` | `/api/auth/login` | — | Login, returns JWT |
| `POST` | `/api/auth/forgot-password` | — | Send password reset email |
| `POST` | `/api/auth/reset-password` | — | Reset password with token |
| `GET` | `/api/auth/me` | Bearer JWT | Get current user |
| `GET` | `/api/auth/google` | — | Start Google OAuth flow |
| `GET` | `/api/auth/google/callback` | — | Google OAuth callback |
| `GET` | `/health` | — | Health check |

## Google OAuth Setup (Optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select an existing one
3. Enable the **Google+ API** / **People API**
4. Create OAuth 2.0 credentials (Web application)
5. Add `http://localhost:4000/api/auth/google/callback` to **Authorized redirect URIs**
6. Copy the Client ID and Client Secret to your `backend/.env`

## Email in Development

When `SMTP_*` env vars are not set, the backend automatically creates an [Ethereal](https://ethereal.email) test account and logs preview URLs to the console:

```
Using Ethereal test account: xxxxx@ethereal.email
Preview emails at: https://ethereal.email
Verification email preview URL: https://ethereal.email/message/...
```

Visit the preview URL to view sent emails without a real inbox.

## Building for Production

```bash
# Frontend
cd frontend && npm run build
# Output: frontend/dist/

# Backend
cd backend && npm run build
# Output: backend/dist/
# Start: node dist/index.js
```

## Key Design Decisions

- **Work email enforcement**: Personal email domains (gmail, hotmail, qq, 163, etc.) are blocked at both frontend and backend layers.
- **JWT authentication**: Stateless tokens stored in `localStorage`. No cookie sessions.
- **SQLite**: Zero-config database suitable for MVP and small-to-medium deployments. Migrate to PostgreSQL for large scale.
- **Ethereal email**: Auto-configured in development — no SMTP setup required to test email flows.
- **Rate limiting**: 10 req/min on sensitive auth endpoints, 20 req/min on all auth routes.
- **Anti-enumeration**: The `/forgot-password` endpoint returns the same response whether or not the email exists.
- **i18n**: Chinese (default) and English, toggled client-side with `localStorage` persistence.
