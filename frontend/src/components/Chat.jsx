import React, { useState } from 'react'
import { consult } from '../services/api'

export default function Chat() {
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)

  async function send() {
    if (!text.trim()) return
    const userMsg = { role: 'user', text }
    setMessages((m) => [...m, userMsg])
    setLoading(true)
    try {
      // Minimal parsing: assume user enters symptoms as comma-separated list
      const payload = {
        age: 30,
        gender: 'unknown',
        symptoms: text.split(',').map((s) => s.trim()).filter(Boolean),
        duration: 'unspecified'
      }
      const res = await consult(payload)
      const botText = `Severity: ${res.severity}\nAction: ${res.recommended_action}\nPossible: ${res.possible_conditions.join(', ')}`
      setMessages((m) => [...m, { role: 'assistant', text: botText }])
    } catch (err) {
      setMessages((m) => [...m, { role: 'assistant', text: 'Error: could not reach server.' }])
    } finally {
      setLoading(false)
      setText('')
    }
  }

  return (
    <div className="chat">
      <div className="messages" aria-live="polite">
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role === 'user' ? 'from-user' : 'from-bot'}`}>
            <pre style={{margin:0,whiteSpace:'pre-wrap'}}>{m.text}</pre>
          </div>
        ))}
      </div>
      <div className="composer">
        <input placeholder="Describe symptoms (comma separated)" value={text} onChange={(e)=>setText(e.target.value)} />
        <button onClick={send} disabled={loading}>{loading ? '...' : 'Send'}</button>
      </div>
    </div>
  )
}
