import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from './contexts/ThemeContext'
import { LocaleProvider } from './contexts/LocaleContext'
import { ProjectProvider } from './contexts/ProjectContext'
import { AuthProvider } from './context/AuthContext'
import { LanguageProvider } from './context/LanguageContext'
import App from './App'
import './index.css'

// Router basename must match Vite's BASE_URL so routes work under /preview/.
// Strip trailing slash — BrowserRouter expects basename without one.
const routerBasename = import.meta.env.BASE_URL.replace(/\/$/, '')

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
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
  </React.StrictMode>
)
