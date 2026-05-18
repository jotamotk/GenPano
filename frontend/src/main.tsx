import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from './contexts/ThemeContext'
import { LocaleProvider } from './contexts/LocaleContext'
import { ProjectProvider } from './contexts/ProjectContext'
import { AuthProvider } from './contexts/AuthContext'
import { LanguageProvider } from './contexts/LanguageContext'
import ErrorBoundary from './components/ErrorBoundary'
import { queryClient } from './lib/queryClient'
import { hydrateDemoMode } from './lib/demoMode'
import App from './App'
import './index.css'

// Reflect ?demo=1 URL param into sessionStorage before any component
// mounts so the first React Query fetch already sees demo state.
hydrateDemoMode()

// Router basename must match Vite's BASE_URL so routes work under /preview/.
// Strip trailing slash — BrowserRouter expects basename without one.
const routerBasename = import.meta.env.BASE_URL.replace(/\/$/, '')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
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
    </ErrorBoundary>
  </React.StrictMode>
)
