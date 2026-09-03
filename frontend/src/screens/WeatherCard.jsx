/* PRAHARI · the weather card.

   It has its own request, and that is the point. The risk board runs infection
   models that accumulate over three weeks, so it needs three weeks of history
   and says so honestly when it cannot get them. A farmer asking what the
   weather is doing needs today and the week ahead. Tying the two together is
   what made a history limit render as a broken forecast, so this card asks
   `/api/fields/{id}/weather` for a short window and renders whatever tier
   answered — live, cached, or the generated fallback — with a label saying
   which.

   Nothing here is invented in the browser. Every value is a field the backend
   sent, and a field the source did not report is simply not drawn: no line is
   better than a confident "0 km/h". */
import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, bi } from '../ui'

const T = {
  title:    ['Weather', 'हवामान'],
  feels:    ['Feels like', 'जाणवते'],
  humidity: ['Humidity', 'आर्द्रता'],
  rain:     ['Rain', 'पाऊस'],
  wind:     ['Wind', 'वारा'],
  uv:       ['UV', 'अतिनील'],
  outlook:  ['Field outlook', 'शेतासाठी अंदाज'],
  retry:    ['Try again', 'पुन्हा'],
  live:     ['Live', 'थेट'],
  demo:     ['Demo weather • live provider unavailable', 'प्रात्यक्षिक हवामान • थेट सेवा उपलब्ध नाही'],
  cached:   ['Recent reading', 'अलीकडील नोंद'],
  none:     ['Weather update temporarily unavailable', 'हवामान माहिती सध्या मिळत नाही'],
}
const t = (lang, k) => bi(lang, T[k][0], T[k][1])
const deg = (v) => (v == null ? '—' : `${Math.round(v)}°`)

export default function WeatherCard({ lang, plot }) {
  const [w, setW] = useState(null)
  const [busy, setBusy] = useState(true)
  const [err, setErr] = useState(false)

  const load = () => {
    if (!plot) { setBusy(false); return }
    setBusy(true); setErr(false)
    api.fieldWeather(plot.id)
      .then(setW)
      .catch(() => setErr(true))
      .finally(() => setBusy(false))
  }
  useEffect(load, [plot?.id])

  if (!plot) return null
  if (busy && !w) {
    return <Card><div className="wx-skel"><i /><i /><i /></div></Card>
  }

  /* The only state that is genuinely an error: no live provider, no cached
     reading and no fallback. Everything else is weather, of one kind or
     another, and is drawn as weather. */
  if (err || !w?.available || !w?.current) {
    return (
      <Card>
        <div className="row between" style={{ marginBottom: 6 }}>
          <div className="card-title">{t(lang, 'title')}</div>
        </div>
        <p className="wx-none">
          🌦 {t(lang, 'none')}
          <button className="btn sm ghost" style={{ marginLeft: 8 }} onClick={load}>
            {t(lang, 'retry')}
          </button>
        </p>
      </Card>
    )
  }

  const c = w.current
  const code = w.status?.code
  const badge = w.generated
    ? { cls: 'demo', text: t(lang, 'demo') }
    : w.status?.stale
      ? { cls: 'cached', text: t(lang, 'cached') }
      : { cls: 'live', text: `${t(lang, 'live')} · ${w.source || ''}` }

  const chips = [
    c.humidity_pct != null && [t(lang, 'humidity'), `${Math.round(c.humidity_pct)}%`],
    c.rain_chance_pct != null && [t(lang, 'rain'), `${Math.round(c.rain_chance_pct)}%`],
    c.wind_kmh != null && [t(lang, 'wind'),
      `${Math.round(c.wind_kmh)} km/h${c.wind_dir ? ` ${c.wind_dir}` : ''}`],
    c.uv_index != null && [t(lang, 'uv'), Math.round(c.uv_index)],
  ].filter(Boolean)

  return (
    <Card className="wx">
      <div className="row between" style={{ marginBottom: 10 }}>
        <div className="card-title">{t(lang, 'title')}</div>
        <span className={`wx-badge ${badge.cls}`}>{badge.text}</span>
      </div>

      <div className="wx-now">
        <span className="wx-now__ic">{c.icon}</span>
        <span className="wx-now__t">
          <b>{deg(c.temp_c)}</b>
          <span className="wx-now__cond">{c.condition}</span>
          {c.feels_like_c != null && (
            <span className="tiny muted">
              {t(lang, 'feels')} {deg(c.feels_like_c)}
            </span>
          )}
        </span>
        <span className="wx-now__hl">
          <b>{deg(c.temp_max_c)}</b>
          <span>{deg(c.temp_min_c)}</span>
        </span>
      </div>

      {chips.length > 0 && (
        <div className="wx-chips">
          {chips.map(([k, v]) => (
            <span className="wx-chip" key={k}><em>{k}</em><b>{v}</b></span>
          ))}
        </div>
      )}

      {w.forecast?.length > 1 && (
        <div className="wx-days" role="list">
          {w.forecast.map((d, i) => (
            <div className="wx-day" role="listitem" key={d.date}
                 aria-current={i === 0 ? 'date' : undefined}>
              <span className="wx-day__n">
                {i === 0 ? bi(lang, 'Today', 'आज') : bi(lang, d.day, d.day_mr)}
              </span>
              <span className="wx-day__ic">{d.icon}</span>
              <span className="wx-day__hi">{deg(d.temp_max_c)}</span>
              <span className="wx-day__lo">{deg(d.temp_min_c)}</span>
              {d.rain_chance_pct != null && (
                <span className="wx-day__r">{Math.round(d.rain_chance_pct)}%</span>
              )}
            </div>
          ))}
        </div>
      )}

      {w.field_outlook?.length > 0 && (
        <div className="wx-outlook">
          <div className="tiny muted wx-outlook__h">{t(lang, 'outlook')}</div>
          {w.field_outlook.map((o, i) => (
            <div className="wx-out" key={i}>
              <span className="wx-out__ic">{o.icon}</span>
              <span className="wx-out__tx"><b>{o.title}</b>{o.body}</span>
            </div>
          ))}
        </div>
      )}

      {w.generated && (
        <p className="tiny faint wx-foot">
          {bi(lang,
            'These numbers are generated, not observed — the live weather service could not be reached. They are consistent and repeatable, and they are not a measurement of your field.',
            'हे आकडे तयार केलेले आहेत, प्रत्यक्ष मोजलेले नाहीत — थेट हवामान सेवा उपलब्ध नव्हती.')}
        </p>
      )}
      {code === 'insufficient_history' && !w.generated && (
        <p className="tiny faint wx-foot">
          {bi(lang,
            'The forecast is live. The risk board needs more past weather than this plan provides, so it is shown separately.',
            'अंदाज थेट आहे. धोक्याच्या फलकासाठी लागणारी जुनी नोंद कमी आहे, ती वेगळी दाखवली आहे.')}
        </p>
      )}
    </Card>
  )
}
