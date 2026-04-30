import axios from 'axios'

const client = axios.create({ baseURL: '/', timeout: 300000 })

// Attach the JWT token to every request when one is stored
client.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers['Authorization'] = `Bearer ${token}`
  return config
})

// ── Auth ─────────────────────────────────────────────────────────────────────

/**
 * Register a new account.
 * @param {string} email
 * @param {string} password
 * @returns {Promise<{id: string, email: string}>}
 */
export async function register(email, password) {
  const res = await client.post('/auth/register', { email, password })
  return res.data
}

/**
 * Log in and persist the JWT token to localStorage.
 * @param {string} email
 * @param {string} password
 * @returns {Promise<{access_token: string, token_type: string}>}
 */
export async function login(email, password) {
  const form = new URLSearchParams()
  form.append('username', email)
  form.append('password', password)
  const res = await client.post('/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  localStorage.setItem('token', res.data.access_token)
  localStorage.setItem('user_email', email)
  return res.data
}

/**
 * Remove the JWT token from localStorage (client-side logout).
 */
export function logout() {
  localStorage.removeItem('token')
  localStorage.removeItem('user_email')
}

/**
 * Return the stored user email, or empty string if not available.
 * @returns {string}
 */
export function getEmail() {
  return localStorage.getItem('user_email') || ''
}

/**
 * Return the stored token, or null if not logged in.
 * @returns {string|null}
 */
export function getToken() {
  return localStorage.getItem('token')
}

// ── Consultation ──────────────────────────────────────────────────────────────

/**
 * Start a new consultation session (initial message).
 * @param {object} payload - { age, symptoms, duration, language?, gender?, existing_conditions? }
 * @returns {Promise<ChatResponse>}
 */
export async function startChat(payload) {
  const res = await client.post('/chat', { type: 'initial', session_id: null, ...payload })
  return res.data
}

/**
 * Reply to a clarifying question.
 * @param {string} sessionId
 * @param {string} message
 * @returns {Promise<ChatResponse>}
 */
export async function replyChat(sessionId, message) {
  const res = await client.post('/chat', { type: 'answer', session_id: sessionId, message })
  return res.data
}

/**
 * Ask a follow-up "know more" question after receiving a triage result.
 * @param {string} sessionId
 * @param {string} message
 * @returns {Promise<ChatResponse>}
 */
export async function followupChat(sessionId, message) {
  const res = await client.post('/chat', { type: 'followup', session_id: sessionId, message })
  return res.data
}

/**
 * Explicitly clear a session.
 * Called when starting a new consultation.
 * @param {string} sessionId
 * @returns {Promise<{ok: boolean}>}
 */
export async function clearSession(sessionId) {
  if (!sessionId) return { ok: true }
  const res = await client.delete(`/session/${sessionId}`)
  return res.data
}

/**
 * Fetch all consultation history memories for the current user.
 * @returns {Promise<{memories: Array<{memory: string, created_at: string}>}>}
 */
export async function getHistory() {
  const res = await client.get('/auth/history')
  return res.data
}
