import React, { useEffect, useRef, useState } from 'react'
import { clearSession, followupChat, replyChat, startChat } from '../services/api'
import { TRANSLATIONS } from '../translations'

// ── Static data ──────────────────────────────────────────────────────────────

const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'हिंदी' },
  { code: 'bn', label: 'বাংলা' },
  { code: 'es', label: 'Español' },
  { code: 'fr', label: 'Français' },
]

const SYMPTOMS = [
  { label: 'Fever',                icon: '🌡' },
  { label: 'Cough',                icon: '🤧' },
  { label: 'Headache',             icon: '🤕' },
  { label: 'Stomach pain',         icon: '🤢' },
  { label: 'Diarrhoea',            icon: '🚽' },
  { label: 'Vomiting',             icon: '🤮' },
  { label: 'Chest pain',           icon: '💔' },
  { label: 'Difficulty breathing', icon: '😮' },
  { label: 'Rash / Skin problem',  icon: '🩹' },
  { label: 'Fatigue / Weakness',   icon: '😴' },
  { label: 'Dizziness',            icon: '💫' },
  { label: 'Wound / Bleeding',     icon: '🩸' },
  { label: 'Eye problem',          icon: '👁' },
  { label: 'Ear pain',             icon: '👂' },
  { label: 'Back / Joint pain',    icon: '🦴' },
  { label: 'Swelling',             icon: '🫸' },
]

const DURATIONS = [
  { value: 'started today',  label: 'Today',       sub: 'Just started'       },
  { value: '1 to 2 days',    label: '1–2 days',    sub: 'Couple of days'     },
  { value: '3 to 7 days',    label: '3–7 days',    sub: 'About a week'       },
  { value: 'over 1 week',    label: 'Over 1 week', sub: 'More than a week'   },
  { value: 'over 1 month',   label: '1+ month',    sub: 'A long time'        },
]

const CONDITIONS = [
  { label: 'Diabetes',             icon: '💉' },
  { label: 'High blood pressure',  icon: '❤️' },
  { label: 'Asthma',               icon: '🫁' },
  { label: 'Heart disease',        icon: '🫀' },
  { label: 'Pregnancy',            icon: '🤰' },
  { label: 'HIV / AIDS',           icon: '🔴' },
  { label: 'Tuberculosis',         icon: '🫁' },
  { label: 'Malaria',              icon: '🦟' },
]

const NO_CONDITION_KEY = '__no_condition__'
const KNOWN_CONDITION_LABELS = new Set(CONDITIONS.map(c => c.label))

const SEV = {
  low:    { emoji: '🟢', tKey: 'severityMild',     color: '#15803d', bg: '#f0fdf4', border: '#86efac' },
  medium: { emoji: '🟡', tKey: 'severityModerate', color: '#92400e', bg: '#fefce8', border: '#fde047' },
  high:   { emoji: '🔴', tKey: 'severityUrgent',   color: '#991b1b', bg: '#fff1f2', border: '#fca5a5' },
}

const KNOWN_SYMPTOM_LABELS = new Set(SYMPTOMS.map(s => s.label))
const TOTAL_STEPS = 4

// ── Sub-components ───────────────────────────────────────────────────────────

function Progress({ step }) {
  return (
    <div className="wiz-progress" aria-label={`Step ${step + 1} of ${TOTAL_STEPS}`}>
      {Array.from({ length: TOTAL_STEPS }, (_, i) => (
        <span
          key={i}
          className={`wiz-dot${i < step ? ' wiz-dot-done' : i === step ? ' wiz-dot-active' : ''}`}
        />
      ))}
    </div>
  )
}

// ── Chat view (clarifying questions) ────────────────────────────────────────

function ChatView({ messages, loading, onSend, t }) {
  const [input, setInput] = useState('')
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  function handleSend() {
    const text = input.trim()
    if (!text) return
    setInput('')
    onSend(text)
  }

  return (
    <div className="chat-view">
      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`chat-bubble chat-bubble-${msg.role}`}>
            {msg.role === 'assistant' && (
              <span className="chat-bubble-label">{t.clarifyingTitle}</span>
            )}
            <span>{msg.content}</span>
          </div>
        ))}
        {loading && (
          <div className="chat-bubble chat-bubble-assistant chat-bubble-thinking">
            <span className="chat-bubble-label">{t.clarifyingTitle}</span>
            <span className="thinking-dots"><span /><span /><span /></span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="chat-input-row">
        <input
          className="chat-input"
          type="text"
          placeholder={t.typeYourAnswer}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleSend() } }}
          disabled={loading}
          autoFocus
        />
        <button
          className="btn-send"
          type="button"
          onClick={handleSend}
          disabled={loading || !input.trim()}
        >
          {loading ? <span className="spinner" /> : t.sendBtn}
        </button>
      </div>
    </div>
  )
}

// ── Result + follow-up view ──────────────────────────────────────────────────

function ResultScreen({ result, onRestart, t, sessionId }) {
  const sev = SEV[result.severity] || SEV.low
  const emergency = result.severity === 'high' ||
    (result.safety?.risk_flags || []).includes('missing_emergency_escalation')

  const [followups, setFollowups]       = useState([])  // [{question, answer}]
  const [followupInput, setFollowupInput] = useState('')
  const [followupLoading, setFollowupLoading] = useState(false)
  const [followupError, setFollowupError]   = useState(null)
  const [showFollowup, setShowFollowup] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    if (followups.length > 0) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [followups, followupLoading])

  async function handleFollowup() {
    const text = followupInput.trim()
    if (!text) return
    setFollowupInput('')
    setFollowupLoading(true)
    setFollowupError(null)
    try {
      const res = await followupChat(sessionId, text)
      setFollowups(prev => [...prev, { question: text, answer: res.answer }])
    } catch (err) {
      const detail = err?.response?.data?.detail
      setFollowupError(
        Array.isArray(detail) ? detail.map(d => d.msg).join('. ') : detail || t.errorNetwork
      )
    } finally {
      setFollowupLoading(false)
    }
  }

  return (
    <div className="result-screen">
      {emergency && (
        <div className="emergency-alert" role="alert">
          <span className="emergency-icon-lg" aria-hidden="true">🚨</span>
          <div>
            <strong>{t.emergencyTitle}</strong>
            <p>{t.emergencyText}</p>
          </div>
        </div>
      )}

      <div className="sev-card" style={{ background: sev.bg, borderColor: sev.border }}>
        <span className="sev-emoji" aria-hidden="true">{sev.emoji}</span>
        <span className="sev-label" style={{ color: sev.color }}>{t[sev.tKey]}</span>
      </div>

      <div className="result-block">
        <p className="result-block-title">{t.whatToDo}</p>
        <p className="result-block-text">{result.recommended_action}</p>
      </div>

      {result.possible_conditions && result.possible_conditions.length > 0 && (
        <div className="result-block">
          <p className="result-block-title">{t.possibleCauses}</p>
          <ul className="result-list">
            {result.possible_conditions.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </div>
      )}

      {result.urgency && (
        <div className="urgency-row">
          <span aria-hidden="true">⏱</span>
          <span>{t.urgency}: <strong>{result.urgency}</strong></span>
        </div>
      )}

      <p className="result-disclaimer">{t.resultDisclaimer}</p>

      {/* ── Follow-up section ── */}
      {followups.length > 0 && (
        <div className="followup-section">
          {followups.map((fq, i) => (
            <div key={i} className="followup-qa">
              <div className="followup-question">
                <span className="followup-q-icon">❓</span>
                <span>{fq.question}</span>
              </div>
              <div className="followup-answer">
                <span className="followup-a-icon">💬</span>
                <span>{fq.answer}</span>
              </div>
            </div>
          ))}
          {followupLoading && (
            <div className="followup-qa">
              <div className="followup-answer followup-thinking">
                <span className="thinking-dots"><span /><span /><span /></span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      )}

      {followupError && (
        <p className="wiz-error" role="alert">{followupError}</p>
      )}

      {/* ── Ask more / follow-up input ── */}
      {showFollowup ? (
        <div className="chat-input-row">
          <input
            className="chat-input"
            type="text"
            placeholder={t.followupPlaceholder}
            value={followupInput}
            onChange={e => setFollowupInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleFollowup() } }}
            disabled={followupLoading}
            autoFocus
          />
          <button
            className="btn-send"
            type="button"
            onClick={handleFollowup}
            disabled={followupLoading || !followupInput.trim()}
          >
            {followupLoading ? <span className="spinner" /> : t.sendBtn}
          </button>
        </div>
      ) : (
        <button
          className="btn-askmore"
          type="button"
          onClick={() => setShowFollowup(true)}
        >
          {t.askMoreBtn}
        </button>
      )}

      <button className="btn-restart" type="button" onClick={onRestart}>
        {t.startNew}
      </button>
    </div>
  )
}

// ── Main wizard ──────────────────────────────────────────────────────────────

export default function Chat({ lang, setLang }) {
  const t = TRANSLATIONS[lang] || TRANSLATIONS.en

  // Wizard state
  const [step, setStep]               = useState(0)
  const [symptoms, setSymptoms]       = useState([])
  const [customInput, setCustomInput] = useState('')
  const [age, setAge]                 = useState('')
  const [gender, setGender]           = useState('')
  const [duration, setDuration]       = useState('')
  const [conditions, setConditions]   = useState([])
  const [customConditionInput, setCustomConditionInput] = useState('')
  const [error, setError]             = useState(null)
  const [loading, setLoading]         = useState(false)

  // Session / chat state
  const [sessionId, setSessionId]   = useState(null)
  const [chatPhase, setChatPhase]   = useState('wizard')   // 'wizard' | 'chat' | 'result'
  const [chatMessages, setChatMessages] = useState([])     // [{role, content}] for chat view
  const [result, setResult]         = useState(null)

  const ageNum = parseInt(age, 10)
  const isValidAge = age !== '' && !isNaN(ageNum) && ageNum >= 0 && ageNum <= 120
  const canProceedStep1 = symptoms.length > 0
  const canProceedStep2 = isValidAge && !!gender && !!duration
  const customConditionText = customConditionInput.trim()
  const canSubmitStep3 = conditions.length > 0 || customConditionText.length > 0

  function toggleSymptom(s) {
    setSymptoms(p => p.includes(s) ? p.filter(x => x !== s) : [...p, s])
  }

  function toggleCondition(c) {
    setConditions(prev => {
      // "No condition" is mutually exclusive with all specific conditions.
      if (c === NO_CONDITION_KEY) {
        return prev.includes(NO_CONDITION_KEY) ? [] : [NO_CONDITION_KEY]
      }

      const withoutNoCondition = prev.filter(x => x !== NO_CONDITION_KEY)
      return withoutNoCondition.includes(c)
        ? withoutNoCondition.filter(x => x !== c)
        : [...withoutNoCondition, c]
    })
  }

  function addCustom() {
    const text = customInput.trim()
    if (text && !symptoms.includes(text)) setSymptoms(p => [...p, text])
    setCustomInput('')
  }

  function addCustomCondition() {
    const text = customConditionInput.trim()
    if (!text) return

    setConditions(prev => {
      const withoutNoCondition = prev.filter(x => x !== NO_CONDITION_KEY)
      return withoutNoCondition.includes(text) ? withoutNoCondition : [...withoutNoCondition, text]
    })
    setCustomConditionInput('')
  }

  function adjustAge(delta) {
    setAge(a => String(Math.min(120, Math.max(0, (parseInt(a, 10) || 0) + delta))))
  }

  function goNext() {
    if (step === 1 && symptoms.length === 0) { setError(t.errorNoSymptom); return }
    if (step === 2) {
      const n = parseInt(age, 10)
      if (!age || isNaN(n) || n < 0 || n > 120) { setError(t.errorAge); return }
      if (!gender) { setError(t.errorGender || 'Please select a gender.'); return }
      if (!duration) { setError(t.errorDuration); return }
    }
    setError(null)
    setStep(s => s + 1)
  }

  function goBack() { setError(null); setStep(s => s - 1) }

  // Handle a ChatResponse (type="question" | "result") from any chat API call
  function handleChatResponse(res, newSessionId) {
    const sid = newSessionId || sessionId
    if (res.type === 'question') {
      setChatMessages(prev => [...prev, { role: 'assistant', content: res.question }])
      setSessionId(sid)
      setChatPhase('chat')
    } else if (res.type === 'result') {
      setResult(res)
      setSessionId(sid)
      setChatPhase('result')
    }
  }

  // Submit from wizard step 3 (conditions step)
  async function submit(conditionsOverride) {
    const selectedConditions = conditionsOverride !== undefined ? conditionsOverride : conditions
    const pendingCustomCondition = customConditionInput.trim()
    const selectedWithPending = pendingCustomCondition
      ? [...selectedConditions, pendingCustomCondition]
      : selectedConditions
    const normalizedFinalConditions = [...new Set(selectedWithPending.filter(c => c !== NO_CONDITION_KEY))]
    setLoading(true)
    setError(null)
    try {
      const payload = {
        age: parseInt(age, 10),
        symptoms,
        duration,
        language: lang,
        ...(gender && { gender }),
        ...(normalizedFinalConditions.length > 0 && { existing_conditions: normalizedFinalConditions }),
      }
      const res = await startChat(payload)
      handleChatResponse(res, res.session_id)
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(
        Array.isArray(detail) ? detail.map(d => d.msg).join('. ') : detail || t.errorNetwork
      )
    } finally {
      setLoading(false)
    }
  }

  // Send a reply to a clarifying question
  async function sendReply(message) {
    setChatMessages(prev => [...prev, { role: 'user', content: message }])
    setLoading(true)
    setError(null)
    try {
      const res = await replyChat(sessionId, message)
      handleChatResponse(res)
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(
        Array.isArray(detail) ? detail.map(d => d.msg).join('. ') : detail || t.errorNetwork
      )
      // Remove the optimistically-added user message on error
      setChatMessages(prev => prev.slice(0, -1))
    } finally {
      setLoading(false)
    }
  }

  // Start a new consultation: clear session, reset all state
  async function restart() {
    try { await clearSession(sessionId) } catch (_) { /* best-effort */ }
    setStep(0); setLang('en'); setSymptoms([]); setCustomInput('')
    setAge(''); setGender(''); setDuration(''); setConditions([]); setCustomConditionInput('')
    setError(null); setLoading(false)
    setSessionId(null); setChatPhase('wizard'); setChatMessages([]); setResult(null)
  }

  // ── Chat phase (clarifying questions) ──
  if (chatPhase === 'chat') {
    return (
      <div className="wizard">
        {error && <p className="wiz-error" role="alert">{error}</p>}
        <ChatView
          messages={chatMessages}
          loading={loading}
          onSend={sendReply}
          t={t}
        />
      </div>
    )
  }

  // ── Result phase ──
  if (chatPhase === 'result' && result) {
    return (
      <ResultScreen
        result={result}
        onRestart={restart}
        t={t}
        sessionId={sessionId}
      />
    )
  }

  // ── Wizard phase ──
  const customSymptoms = symptoms.filter(s => !KNOWN_SYMPTOM_LABELS.has(s))
  const customConditions = conditions.filter(
    c => c !== NO_CONDITION_KEY && !KNOWN_CONDITION_LABELS.has(c)
  )

  return (
    <div className="wizard">
      <Progress step={step} />

      {/* ── Step 0: Language ── */}
      {step === 0 && (
        <div className="wiz-step">
          <h2 className="wiz-title">{t.chooseLanguage}</h2>
          <p className="wiz-sub">{t.selectLanguage}</p>
          <div className="lang-grid">
            {LANGUAGES.map(l => (
              <button
                key={l.code}
                type="button"
                className={`lang-btn${lang === l.code ? ' sel' : ''}`}
                onClick={() => setLang(l.code)}
              >
                {l.label}
              </button>
            ))}
          </div>
          <button className="btn-primary" type="button" onClick={goNext}>
            {t.continueBtn}
          </button>
        </div>
      )}

      {/* ── Step 1: Symptoms ── */}
      {step === 1 && (
        <div className="wiz-step">
          <h2 className="wiz-title">{t.whatSymptoms}</h2>
          <p className="wiz-sub">{t.tapSymptoms}</p>
          <div className="chip-grid">
            {SYMPTOMS.map(s => (
              <button
                key={s.label}
                type="button"
                className={`chip${symptoms.includes(s.label) ? ' sel' : ''}`}
                onClick={() => toggleSymptom(s.label)}
              >
                <span aria-hidden="true">{s.icon}</span> {t.symptoms[s.label] || s.label}
              </button>
            ))}
          </div>
          <div className="custom-row">
            <input
              type="text"
              className="custom-input"
              placeholder={t.otherSymptomPlaceholder}
              value={customInput}
              onChange={e => setCustomInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addCustom() } }}
            />
            <button type="button" className="btn-add" onClick={addCustom}>{t.addBtn}</button>
          </div>
          {customSymptoms.length > 0 && (
            <div className="custom-tags">
              {customSymptoms.map(s => (
                <span key={s} className="custom-tag">
                  {s}
                  <button type="button" onClick={() => toggleSymptom(s)} aria-label={`Remove ${s}`}>×</button>
                </span>
              ))}
            </div>
          )}
          {error && <p className="wiz-error" role="alert">{error}</p>}
          <div className="wiz-nav">
            <button type="button" className="btn-back" onClick={goBack}>{t.backBtn}</button>
            <button type="button" className="btn-primary" onClick={goNext} disabled={!canProceedStep1}>{t.nextBtn}</button>
          </div>
        </div>
      )}

      {/* ── Step 2: Patient details ── */}
      {step === 2 && (
        <div className="wiz-step">
          <h2 className="wiz-title">{t.aboutPatient}</h2>
          <p className="wiz-sub">{t.betterGuidance}</p>
          <div className="field-group">
            <label>{t.ageLbl} <span className="req">*</span></label>
            <div className="age-row">
              <button type="button" className="age-btn" onClick={() => adjustAge(-1)} aria-label="Decrease age">−</button>
              <input
                type="number" className="age-field" min="0" max="120"
                value={age} onChange={e => setAge(e.target.value)}
                placeholder="0–120" inputMode="numeric"
              />
              <button type="button" className="age-btn" onClick={() => adjustAge(1)} aria-label="Increase age">+</button>
            </div>
          </div>
          <div className="field-group">
            <label>{t.genderLbl} <span className="req">*</span></label>
            <div className="choice-row">
              {['male', 'female', 'other'].map(g => (
                <button
                  key={g} type="button"
                  className={`choice-btn${gender === g ? ' sel' : ''}`}
                  onClick={() => setGender(prev => prev === g ? '' : g)}
                >
                  {t.genderOptions[g]}
                </button>
              ))}
            </div>
          </div>
          <div className="field-group">
            <label>{t.howLong} <span className="req">*</span></label>
            <div className="dur-grid">
              {DURATIONS.map(d => (
                <button
                  key={d.value} type="button"
                  className={`dur-btn${duration === d.value ? ' sel' : ''}`}
                  onClick={() => setDuration(d.value)}
                >
                  <span className="dur-label">{t.durations[d.value]?.label || d.label}</span>
                  <span className="dur-sub">{t.durations[d.value]?.sub || d.sub}</span>
                </button>
              ))}
            </div>
          </div>
          {error && <p className="wiz-error" role="alert">{error}</p>}
          <div className="wiz-nav">
            <button type="button" className="btn-back" onClick={goBack}>{t.backBtn}</button>
            <button type="button" className="btn-primary" onClick={goNext} disabled={!canProceedStep2}>{t.nextBtn}</button>
          </div>
        </div>
      )}

      {/* ── Step 3: Existing conditions ── */}
      {step === 3 && (
        <div className="wiz-step">
          <h2 className="wiz-title">{t.existingConditions}</h2>
          <p className="wiz-sub">{t.selectConditions}</p>
          <div className="chip-grid">
            {CONDITIONS.map(c => (
              <button
                key={c.label} type="button"
                className={`chip${conditions.includes(c.label) ? ' sel' : ''}`}
                onClick={() => toggleCondition(c.label)}
              >
                <span aria-hidden="true">{c.icon}</span> {t.conditions[c.label] || c.label}
              </button>
            ))}
            <button
              type="button"
              className={`chip${conditions.includes(NO_CONDITION_KEY) ? ' sel' : ''}`}
              onClick={() => toggleCondition(NO_CONDITION_KEY)}
            >
              <span aria-hidden="true">❔</span> {t.noConditionsCard || t.skipConditions || "No condition / I don't know"}
            </button>
          </div>
          <div className="custom-row">
            <input
              type="text"
              className="custom-input"
              placeholder={t.otherConditionPlaceholder || 'Any other condition to share...'}
              value={customConditionInput}
              onChange={e => setCustomConditionInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addCustomCondition() } }}
            />
            <button type="button" className="btn-add" onClick={addCustomCondition}>{t.addBtn}</button>
          </div>
          {customConditions.length > 0 && (
            <div className="custom-tags">
              {customConditions.map(c => (
                <span key={c} className="custom-tag">
                  {c}
                  <button type="button" onClick={() => toggleCondition(c)} aria-label={`Remove ${c}`}>×</button>
                </span>
              ))}
            </div>
          )}
          {error && <p className="wiz-error" role="alert">{error}</p>}
          <div className="wiz-nav">
            <button type="button" className="btn-back" onClick={goBack}>{t.backBtn}</button>
            <button
              className="btn-primary"
              type="button"
              disabled={loading || !canSubmitStep3}
              onClick={() => submit()}
            >
              {loading
                ? <><span className="spinner" /> {t.checking}</>
                : t.getAssessment}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
