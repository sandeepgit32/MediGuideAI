import React, { useState } from 'react'
import Chat from './components/Chat'
import Login from './components/Login'
import logo from '../logo.png'
import { TRANSLATIONS } from './translations'
import { getToken, logout } from './services/api'

export default function App() {
  const [lang, setLang] = useState('en')
  const [token, setToken] = useState(() => getToken())
  const t = TRANSLATIONS[lang] || TRANSLATIONS.en

  function handleLogin() {
    setToken(getToken())
  }

  function handleLogout() {
    logout()
    setToken(null)
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-inner">
          <img src={logo} alt="MediGuideAI logo" className="header-icon" />
          <div className="header-text">
            <h1 className="header-title">MediGuideAI</h1>
            <p className="header-subtitle">Free health guidance</p>
          </div>
          {token && (
            <div className="header-user">
              <button type="button" className="btn-logout" onClick={handleLogout}>
                Sign Out
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="app-main">
        {token
          ? <Chat lang={lang} setLang={setLang} />
          : <Login onLogin={handleLogin} />
        }
      </main>

      <footer className="app-footer">
        <p>{t.footer}</p>
      </footer>
    </div>
  )
}

