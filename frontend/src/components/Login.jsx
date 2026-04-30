import React, { useEffect, useState } from 'react'
import { login, register } from '../services/api'
import logo from '../../logo.png'

export default function Login({ onLogin }) {
  const [mode, setMode]         = useState('login')   // 'login' | 'register'
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm]   = useState('')
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState('')
  const [toast, setToast]       = useState('')   // auto-dismissing success toast

  // Auto-dismiss toast after 4 seconds
  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(''), 4000)
    return () => clearTimeout(timer)
  }, [toast])

  function resetForm() {
    setEmail(''); setPassword(''); setConfirm(''); setError('')
  }

  function switchMode(m) { setMode(m); resetForm() }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')

    if (!email.trim() || !password) { setError('Please enter your email and password.'); return }

    if (mode === 'register') {
      if (password !== confirm) { setError('Passwords do not match.'); return }
      if (password.length < 6)  { setError('Password must be at least 6 characters.'); return }
    }

    setLoading(true)
    try {
      if (mode === 'register') {
        await register(email.trim(), password)
        switchMode('login') // switch first so form fields reset
        setToast('✅ Account created successfully! Please sign in.')
      } else {
        await login(email.trim(), password)
        onLogin()
      }
    } catch (err) {
      const detail = err?.response?.data?.detail
      if (typeof detail === 'string') {
        setError(detail)
      } else if (Array.isArray(detail)) {
        setError(detail.map(d => d.msg).join(', '))
      } else {
        setError(
          mode === 'login'
            ? 'Invalid email or password.'
            : 'Could not create account. The email may already be registered.'
        )
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        {/* Logo */}
        <div className="auth-logo">
          <img src={logo} alt="MediGuideAI logo" className="auth-logo-img" />
          <div>
            <div className="auth-app-name">MediGuideAI</div>
            <div className="auth-app-tagline">Free Health Guidance. Powered by AI.</div>
          </div>
        </div>

        {/* Tabs */}
        <div className="auth-tabs">
          <button
            type="button"
            className={`auth-tab${mode === 'login' ? ' auth-tab-active' : ''}`}
            onClick={() => switchMode('login')}
          >
            Sign In
          </button>
          <button
            type="button"
            className={`auth-tab${mode === 'register' ? ' auth-tab-active' : ''}`}
            onClick={() => switchMode('register')}
          >
            Create Account
          </button>
        </div>

        {/* Form */}
        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="auth-field">
            <label htmlFor="auth-email">Email address</label>
            <input
              id="auth-email"
              type="email"
              autoComplete={mode === 'login' ? 'username' : 'email'}
              placeholder="you@example.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          <div className="auth-field">
            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              placeholder={mode === 'register' ? 'At least 6 characters' : '••••••••'}
              value={password}
              onChange={e => setPassword(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          {mode === 'register' && (
            <div className="auth-field">
              <label htmlFor="auth-confirm">Confirm password</label>
              <input
                id="auth-confirm"
                type="password"
                autoComplete="new-password"
                placeholder="Re-enter your password"
                value={confirm}
                onChange={e => setConfirm(e.target.value)}
                disabled={loading}
                required
              />
            </div>
          )}

          {error && <div className="auth-error" role="alert">{error}</div>}

          <button type="submit" className="auth-submit" disabled={loading}>
            {loading
              ? <span className="spinner" />
              : mode === 'login' ? 'Sign In' : 'Create Account'}
          </button>
        </form>

        <p className="auth-footer">
          For guidance only · Not a replacement for a doctor ·{' '}
          In an emergency call your local emergency number immediately.
        </p>
      </div>
      {toast && (
        <div className="auth-toast" role="status">
          {toast}
        </div>
      )}
    </div>
  )
}
