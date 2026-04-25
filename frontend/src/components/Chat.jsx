import React, { useState } from 'react'
import { consult } from '../services/api'
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

const SEV = {
  low:    { emoji: '🟢', tKey: 'severityMild',     color: '#15803d', bg: '#f0fdf4', border: '#86efac' },
  medium: { emoji: '🟡', tKey: 'severityModerate', color: '#92400e', bg: '#fefce8', border: '#fde047' },
  high:   { emoji: '🔴', tKey: 'severityUrgent',   color: '#991b1b', bg: '#fff1f2', border: '#fca5a5' },
}

const KNOWN_SYMPTOM_LABELS = new Set(SYMPTOMS.map(s => s.label))
const TOTAL_STEPS = 4

// ── Progress indicator ───────────────────────────────────────────────────────

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

// ── Results screen ───────────────────────────────────────────────────────────

function ResultScreen({ result, onRestart, t }) {
  const sev = SEV[result.severity] || SEV.low
  const emergency =
    result.severity === 'high' ||
    (result.emergency_flags && result.emergency_flags.length > 0)

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

      <button className="btn-restart" type="button" onClick={onRestart}>
        {t.startNew}
      </button>
    </div>
  )
}

// ── Main wizard ──────────────────────────────────────────────────────────────

export default function Chat({ lang, setLang }) {
  const t = TRANSLATIONS[lang] || TRANSLATIONS.en

  const [step, setStep]               = useState(0)
  const [symptoms, setSymptoms]       = useState([])
  const [customInput, setCustomInput] = useState('')
  const [age, setAge]                 = useState('')
  const [gender, setGender]           = useState('')
  const [duration, setDuration]       = useState('')
  const [conditions, setConditions]   = useState([])
  const [result, setResult]           = useState(null)
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState(null)

  function toggleSymptom(s) {
    setSymptoms(p => p.includes(s) ? p.filter(x => x !== s) : [...p, s])
  }

  function toggleCondition(c) {
    setConditions(p => p.includes(c) ? p.filter(x => x !== c) : [...p, c])
  }

  function addCustom() {
    const t = customInput.trim()
    if (t && !symptoms.includes(t)) setSymptoms(p => [...p, t])
    setCustomInput('')
  }

  function adjustAge(delta) {
    setAge(a => String(Math.min(120, Math.max(0, (parseInt(a, 10) || 0) + delta))))
  }

  function goNext() {
    if (step === 1 && symptoms.length === 0) {
      setError(t.errorNoSymptom)
      return
    }
    if (step === 2) {
      const n = parseInt(age, 10)
      if (!age || isNaN(n) || n < 0 || n > 120) {
        setError(t.errorAge)
        return
      }
      if (!duration) {
        setError(t.errorDuration)
        return
      }
    }
    setError(null)
    setStep(s => s + 1)
  }

  function goBack() { setError(null); setStep(s => s - 1) }

  async function submit(conditionsOverride) {
    const finalConditions = conditionsOverride !== undefined ? conditionsOverride : conditions
    setLoading(true)
    setError(null)
    try {
      const payload = {
        age: parseInt(age, 10),
        symptoms,
        duration,
        language: lang,
        ...(gender && { gender }),
        ...(finalConditions.length > 0 && { existing_conditions: finalConditions }),
      }
      const res = await consult(payload)
      setResult(res)
      setStep(TOTAL_STEPS)
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(
        Array.isArray(detail)
          ? detail.map(d => d.msg).join('. ')
          : detail || t.errorNetwork
      )
    } finally {
      setLoading(false)
    }
  }

  function restart() {
    setStep(0); setLang('en'); setSymptoms([]); setCustomInput('')
    setAge(''); setGender(''); setDuration(''); setConditions([])
    setResult(null); setError(null)
  }

  // Results
  if (step === TOTAL_STEPS && result) {
    return <ResultScreen result={result} onRestart={restart} t={t} />
  }

  const customSymptoms = symptoms.filter(s => !KNOWN_SYMPTOM_LABELS.has(s))

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
                  <button
                    type="button"
                    onClick={() => toggleSymptom(s)}
                    aria-label={`Remove ${s}`}
                  >×</button>
                </span>
              ))}
            </div>
          )}

          {error && <p className="wiz-error" role="alert">{error}</p>}
          <div className="wiz-nav">
            <button type="button" className="btn-back" onClick={goBack}>{t.backBtn}</button>
            <button type="button" className="btn-primary" onClick={goNext}>{t.nextBtn}</button>
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
              <button
                type="button"
                className="age-btn"
                onClick={() => adjustAge(-1)}
                aria-label="Decrease age"
              >−</button>
              <input
                type="number"
                className="age-field"
                min="0"
                max="120"
                value={age}
                onChange={e => setAge(e.target.value)}
                placeholder="0–120"
                inputMode="numeric"
              />
              <button
                type="button"
                className="age-btn"
                onClick={() => adjustAge(1)}
                aria-label="Increase age"
              >+</button>
            </div>
          </div>

          <div className="field-group">
            <label>{t.genderLbl} <span className="opt">{t.optional}</span></label>
            <div className="choice-row">
              {['male', 'female', 'other'].map(g => (
                <button
                  key={g}
                  type="button"
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
                  key={d.value}
                  type="button"
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
            <button type="button" className="btn-primary" onClick={goNext}>{t.nextBtn}</button>
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
                key={c.label}
                type="button"
                className={`chip${conditions.includes(c.label) ? ' sel' : ''}`}
                onClick={() => toggleCondition(c.label)}
              >
                <span aria-hidden="true">{c.icon}</span> {t.conditions[c.label] || c.label}
              </button>
            ))}
          </div>

          {error && <p className="wiz-error" role="alert">{error}</p>}
          <div className="wiz-nav">
            <button type="button" className="btn-back" onClick={goBack}>{t.backBtn}</button>
            <button
              type="button"
              className="btn-primary"
              onClick={() => submit()}
              disabled={loading}
            >
              {loading
                ? <><span className="spinner" aria-hidden="true" /> {t.checking}</>
                : t.getAssessment}
            </button>
          </div>
          <button
            type="button"
            className="btn-skip"
            onClick={() => submit([])}
            disabled={loading}
          >
            {t.skipConditions}
          </button>
        </div>
      )}
    </div>
  )
}
