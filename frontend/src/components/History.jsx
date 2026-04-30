import React, { useState, useEffect } from 'react'
import { TRANSLATIONS } from '../translations'
import { getHistory } from '../services/api'

/**
 * History page — shows all Mem0 consultation memories grouped by date, newest first.
 *
 * @param {{ lang: string }} props
 */
export default function History({ lang }) {
  const t = TRANSLATIONS[lang] || TRANSLATIONS.en
  const [memories, setMemories] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function fetchHistory() {
      try {
        const data = await getHistory()
        if (!cancelled) {
          setMemories(data.memories || [])
        }
      } catch {
        if (!cancelled) setError(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    fetchHistory()
    return () => { cancelled = true }
  }, [])

  /**
   * Convert an ISO timestamp or date string to a locale date label.
   * Falls back to 'Unknown date' when the string is empty or unparseable.
   */
  function toDateLabel(isoStr) {
    if (!isoStr) return 'Unknown date'
    const d = new Date(isoStr)
    if (isNaN(d.getTime())) return 'Unknown date'
    return d.toLocaleDateString(lang === 'hi' ? 'hi-IN' : lang === 'bn' ? 'bn-BD' : lang === 'es' ? 'es' : lang === 'fr' ? 'fr-FR' : 'en-GB', {
      day: 'numeric', month: 'long', year: 'numeric',
    })
  }

  /**
   * Group memory entries by their calendar date label, preserving order.
   * Returns an array of [dateLabel, entries[]] tuples.
   */
  function groupByDate(entries) {
    const map = new Map()
    for (const entry of entries) {
      const label = toDateLabel(entry.created_at)
      if (!map.has(label)) map.set(label, [])
      map.get(label).push(entry)
    }
    return Array.from(map.entries())
  }

  if (loading) {
    return (
      <div className="history-page">
        <h2 className="history-page-title">{t.historyTitle}</h2>
        <p className="history-loading">{t.historyLoading}</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="history-page">
        <h2 className="history-page-title">{t.historyTitle}</h2>
        <p className="history-error">{t.historyError}</p>
      </div>
    )
  }

  if (memories.length === 0) {
    return (
      <div className="history-page">
        <h2 className="history-page-title">{t.historyTitle}</h2>
        <p className="history-empty">{t.historyEmpty}</p>
      </div>
    )
  }

  const groups = groupByDate(memories)

  return (
    <div className="history-page">
      <h2 className="history-page-title">{t.historyTitle}</h2>
      {groups.map(([dateLabel, entries]) => (
        <div key={dateLabel} className="history-day">
          <p className="history-date-label">{dateLabel}</p>
          {[...entries].reverse().map((entry, idx) => (
            <div key={idx} className="history-card">
              {entry.memory}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
