import React, { useState } from 'react'
import Chat from './components/Chat'
import logo from '../logo.png'
import { TRANSLATIONS } from './translations'

export default function App() {
  const [lang, setLang] = useState('en')
  const t = TRANSLATIONS[lang] || TRANSLATIONS.en

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-inner">
          <img src={logo} alt="MediGuideAI logo" className="header-icon" />
          <div className="header-text">
            <h1 className="header-title">MediGuideAI</h1>
            <p className="header-subtitle">Free health guidance</p>
          </div>
        </div>
      </header>

      <main className="app-main">
        <Chat lang={lang} setLang={setLang} />
      </main>

      <footer className="app-footer">
        <p>{t.footer}</p>
      </footer>
    </div>
  )
}

