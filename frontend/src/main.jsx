import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from './contexts/ThemeContext'
import { LocaleProvider } from './contexts/LocaleContext'
import { ProjectProvider } from './contexts/ProjectContext'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <LocaleProvider>
          <ProjectProvider>
            <App />
          </ProjectProvider>
        </LocaleProvider>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>
)
