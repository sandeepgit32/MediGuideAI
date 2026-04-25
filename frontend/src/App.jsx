import React from 'react'
import Chat from './components/Chat'
import logo from '../logo.png'

export default function App() {
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
        <Chat />
      </main>

      <footer className="app-footer">
        <p>
          For guidance only · Not a replacement for a doctor ·
          In an emergency call your local emergency number immediately.
        </p>
      </footer>
    </div>
  )
}

