import React, { useState, useEffect, useRef } from 'react'
import Chat from './components/Chat'
import History from './components/History'
import Login from './components/Login'
import logo from '../logo.png'
import { TRANSLATIONS } from './translations'
import { getToken, getEmail, logout } from './services/api'

export default function App() {
  const [lang, setLang] = useState('en')
  const [token, setToken] = useState(() => getToken())
  const [userEmail, setUserEmail] = useState(() => getEmail())
  const [page, setPage] = useState('chat')
  const [accountOpen, setAccountOpen] = useState(false)
  const accountRef = useRef(null)
  const t = TRANSLATIONS[lang] || TRANSLATIONS.en

  function handleLogin() {
    setToken(getToken())
    setUserEmail(getEmail())
  }

  function handleLogout() {
    logout()
    setToken(null)
    setUserEmail('')
    setPage('chat')
    setAccountOpen(false)
  }

  // Close popup when clicking outside
  useEffect(() => {
    if (!accountOpen) return
    function handleOutsideClick(e) {
      if (accountRef.current && !accountRef.current.contains(e.target)) {
        setAccountOpen(false)
      }
    }
    document.addEventListener('mousedown', handleOutsideClick)
    return () => document.removeEventListener('mousedown', handleOutsideClick)
  }, [accountOpen])

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-inner">
          <button
            type="button"
            className="header-logo-btn"
            onClick={() => setPage('chat')}
            aria-label="Go to home"
          >
            <img src={logo} alt="MediGuideAI logo" className="header-icon" />
          </button>
          <div className="header-text">
            <h1 className="header-title">MediGuideAI</h1>
            <p className="header-subtitle">Free health guidance</p>
          </div>
          {token && (
            <div className="header-user" ref={accountRef}>
              <button
                type="button"
                className="btn-account"
                onClick={() => setAccountOpen(o => !o)}
                aria-haspopup="true"
                aria-expanded={accountOpen}
              >
                {t.account}
              </button>
              {accountOpen && (
                <div className="account-popup" role="dialog" aria-label="Account menu">
                  <p className="account-popup-email">{userEmail}</p>
                  <button
                    type="button"
                    className="btn-history"
                    onClick={() => { setPage('history'); setAccountOpen(false) }}
                  >
                    {t.historyBtn}
                  </button>
                </div>
              )}
              <button type="button" className="btn-logout" onClick={handleLogout}>
                {t.signOut}
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="app-main">
        {token
          ? page === 'history'
            ? <History lang={lang} />
            : <Chat lang={lang} setLang={setLang} />
          : <Login onLogin={handleLogin} />
        }
      </main>

      <footer className="app-footer">
        <p>{t.footer}</p>
      </footer>
    </div>
  )
}

