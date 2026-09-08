import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { LanguageProvider } from './contexts/LanguageContext'
import { PageContextProvider } from './contexts/PageContext'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      {/* LanguageProvider wraps the router so Login and Register — which render
          before any auth token exists — can still read and set the language. */}
      <LanguageProvider>
        {/* PageContextProvider lets whatever page is on screen tell the
            floating AI advisor what it's actually showing, so "what is
            happening here?" works everywhere, not just generically. */}
        <PageContextProvider>
          <App />
        </PageContextProvider>
      </LanguageProvider>
    </BrowserRouter>
  </React.StrictMode>
)
