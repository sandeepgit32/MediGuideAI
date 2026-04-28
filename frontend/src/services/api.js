import axios from 'axios'

const client = axios.create({ baseURL: '/', timeout: 60000 })

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
 * Explicitly clear a session and its mem0 memory.
 * Called when starting a new consultation.
 * @param {string} sessionId
 * @returns {Promise<{ok: boolean}>}
 */
export async function clearSession(sessionId) {
  if (!sessionId) return { ok: true }
  const res = await client.delete(`/session/${sessionId}`)
  return res.data
}
