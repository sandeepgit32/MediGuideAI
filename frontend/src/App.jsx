import React from 'react'
import Chat from './components/Chat'

export default function App() {
  return (
    <div className="app-container">
      <header className="app-header">MediGuideAI — Symptom Triage</header>
      <main>
        <Chat />
      </main>
    </div>
  )
}
