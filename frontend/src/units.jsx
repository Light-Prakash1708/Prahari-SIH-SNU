/* PRAHARI · the administrative units a farmer can choose.

   The list used to be hard-coded in two screens as ten Nashik talukas, so a
   Bengal farmer could only register by picking a Maharashtra taluka — which
   then put their field in the wrong officer's queue and the wrong outbreak
   cluster. It now comes from the server's reference data (`/api/reference`,
   public and cached), grouped by state and district. The Nashik list below is
   only the offline fallback for a phone that has never reached the server. */
import React, { useEffect, useState } from 'react'
import { api } from './api'

const FALLBACK = [
  ['pimpalgaon', 'Pimpalgaon Baswant', 'पिंपळगाव बसवंत'], ['niphad', 'Niphad', 'निफाड'],
  ['dindori', 'Dindori', 'दिंडोरी'], ['lasalgaon', 'Lasalgaon', 'लासलगाव'], ['nashik', 'Nashik', 'नाशिक'],
  ['sinnar', 'Sinnar', 'सिन्नर'], ['igatpuri', 'Igatpuri', 'इगतपुरी'], ['yeola', 'Yeola', 'येवला'],
  ['chandvad', 'Chandvad', 'चांदवड'], ['malegaon', 'Malegaon', 'मालेगाव'],
].map(([id, name, mr]) => ({ id, name, mr, state: 'Maharashtra', district: 'Nashik' }))

let cached = null

export function useUnits() {
  const [units, setUnits] = useState(cached || FALLBACK)
  useEffect(() => {
    if (cached) return
    let live = true
    api.reference()
      .then(r => { if (live && Array.isArray(r?.talukas) && r.talukas.length) { cached = r.talukas; setUnits(r.talukas) } })
      .catch(() => {})
    return () => { live = false }
  }, [])
  return units
}

export const unitName = (u, lang) =>
  (lang === 'mr' && u.mr) || (lang === 'bn' && u.bn) || u.name

/* <option>s grouped by state · district, Bengal first for a Bengali reader. */
export function UnitOptions({ units, lang }) {
  const groups = {}
  for (const u of units) {
    const g = `${u.state || ''} · ${u.district || ''}`
    ;(groups[g] = groups[g] || []).push(u)
  }
  const order = Object.keys(groups).sort((a, b) => {
    const wb = (k) => (k.startsWith('West Bengal') ? 0 : 1)
    return lang === 'bn' ? wb(a) - wb(b) || a.localeCompare(b) : a.localeCompare(b)
  })
  return order.map(g => (
    <optgroup key={g} label={g}>
      {groups[g].map(u => <option key={u.id} value={u.id}>{unitName(u, lang)}</option>)}
    </optgroup>
  ))
}
