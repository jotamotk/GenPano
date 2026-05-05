import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from './contexts/ThemeContext'
import { LocaleProvider } from './contexts/LocaleContext'
import { ProjectProvider } from './contexts/ProjectContext'
import { AuthProvider } from './contexts/AuthContext'
import { LanguageProvider } from './contexts/LanguageContext'
import App from './App'
import './index.css'

// Router basename must match Vite's BASE_URL so routes work under /preview/.
// Strip trailing slash — BrowserRouter expects basename without one.
const routerBasename = import.meta.env.BASE_URL.replace(/\/$/, '')

// Phase 0: TanStack Query for server state (replaces ad-hoc useEffect+fetch).
// Defaults per ADR — staleTime 60s avoids refetch storm; retry: 1 keeps UX
// responsive on flaky network; refetchOnWindowFocus off matches Stripe-style
// dashboard preference.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={routerBasename}>
        <ThemeProvider>
          <LocaleProvider>
            <LanguageProvider>
              <AuthProvider>
                <ProjectProvider>
                  <App />
                </ProjectProvider>
              </AuthProvider>
            </LanguageProvider>
          </LocaleProvider>
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
)
