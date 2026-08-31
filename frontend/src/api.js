/* ═══════════════════════════════════════════════════════════════════════════
   PRAHARI · API client

   Four things this does that a generated client would not:

   1. Every failure comes back as a readable sentence in the farmer's language.
      Someone standing in a field must be told what is wrong, not shown a
      spinner forever.

   2. GET responses are cached under their own URL, so the app opens with the
      last known state when there is no signal. The cache is stamped and the UI
      shows how old it is rather than pretending it is live.

   3. Writes made offline go into a durable queue with a client_ref. Re-sending
      an item the server already accepted returns the original result instead of
      creating a second row — a flaky connection cannot double-count a trap.

   4. The bearer token lives in one place. A 401 clears it and the app returns
      to the sign-in screen rather than rendering half-empty screens.
   ═══════════════════════════════════════════════════════════════════════════ */

const BASE = import.meta.env.VITE_API || ''
const TOKEN_KEY = 'prahari.token.v2'
const CACHE_KEY = 'prahari.cache.v2'
const QUEUE_KEY = 'prahari.queue.v2'
const LANG_KEY = 'prahari.lang'

/* ── token ─────────────────────────────────────────────────────────────── */
let token = null
try { token = localStorage.getItem(TOKEN_KEY) } catch { /* private mode */ }
const listeners = new Set()

export const auth = {
  get token() { return token },
  get signedIn() { return !!token },
  set(t) {
    token = t
    try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch {}
    listeners.forEach(fn => fn(t))
  },
  clear() { auth.set(null); clearCache() },
  onChange(fn) { listeners.add(fn); return () => listeners.delete(fn) },
}

/* ── language ──────────────────────────────────────────────────────────── */
export function getLang() {
  try { return localStorage.getItem(LANG_KEY) || 'mr' } catch { return 'mr' }
}
export function setLang(l) { try { localStorage.setItem(LANG_KEY, l) } catch {} }

/* ── cache ─────────────────────────────────────────────────────────────── */
function readCache() { try { return JSON.parse(localStorage.getItem(CACHE_KEY) || '{}') } catch { return {} } }
function writeCache(o) {
  try { localStorage.setItem(CACHE_KEY, JSON.stringify(o)) }
  catch { try { localStorage.removeItem(CACHE_KEY) } catch {} }
}
export function clearCache() { try { localStorage.removeItem(CACHE_KEY) } catch {} }
export function cachedAt(path) { return readCache()[path]?.at || null }

/* ── errors ────────────────────────────────────────────────────────────── */
export class ApiError extends Error {
  constructor(body, status) {
    super(body?.message || `Server returned ${status}`)
    this.code = body?.error || 'error'
    this.messageMr = body?.message_mr
    this.retryable = !!body?.retryable
    this.status = status
    this.detail = body?.detail
    this.problems = body?.problems
    this.requestId = body?.request_id
  }
  say(lang) { return (lang === 'mr' && this.messageMr) || this.message }
}

const OFFLINE = {
  message: 'No internet connection, and nothing saved on this device for this screen yet.',
  message_mr: 'इंटरनेट नाही, आणि या स्क्रीनसाठी या फोनवर काहीही साठवलेले नाही.',
  error: 'offline', retryable: true,
}

async function parse(r) {
  let body = null
  try { body = await r.json() } catch { /* not json */ }
  if (!r.ok) {
    if (r.status === 401 && token) auth.clear()
    throw new ApiError(body || { message: `Server returned ${r.status}` }, r.status)
  }
  return body
}

function headers(extra = {}) {
  const h = { ...extra }
  if (token) h.Authorization = `Bearer ${token}`
  return h
}

/* ── verbs ─────────────────────────────────────────────────────────────── */
async function get(path, { cache = true } = {}) {
  try {
    const r = await fetch(BASE + path, { headers: headers() })
    const data = await parse(r)
    if (cache) { const c = readCache(); c[path] = { at: Date.now(), data }; writeCache(c) }
    return data
  } catch (e) {
    if (e instanceof ApiError) {
      // A real server answer is never replaced by a cached one — a 403 is a
      // fact about permission, not a network problem.
      if (e.status !== 503 || !cache) throw e
    }
    const hit = cache && readCache()[path]
    if (hit) return { ...hit.data, _stale: true, _cachedAt: hit.at }
    if (e instanceof ApiError) throw e
    throw new ApiError(OFFLINE, 0)
  }
}

async function send(path, body, method = 'POST') {
  const opts = { method, headers: headers() }
  if (body instanceof FormData) opts.body = body
  else if (body !== undefined) {
    opts.headers['content-type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  try {
    return await parse(await fetch(BASE + path, opts))
  } catch (e) {
    if (e instanceof ApiError) throw e
    throw new ApiError({
      ...OFFLINE,
      message: 'You are offline. This has been saved on your phone and will be sent when you reconnect.',
      message_mr: 'तुम्ही ऑफलाइन आहात. ही नोंद फोनवर साठवली आहे आणि इंटरनेट आल्यावर पाठवली जाईल.',
    }, 0)
  }
}

const fd = (o) => {
  const f = new FormData()
  Object.entries(o).forEach(([k, v]) => { if (v !== null && v !== undefined) f.append(k, v) })
  return f
}

/* ── the offline queue ─────────────────────────────────────────────────── */
export const queue = {
  read() { try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]') } catch { return [] } },
  write(items) { try { localStorage.setItem(QUEUE_KEY, JSON.stringify(items)) } catch {} },
  add(item) {
    const items = queue.read()
    // A client_ref makes the item idempotent end to end. The server returns
    // "duplicate" rather than creating a second row if this arrives twice.
    items.push({ client_ref: item.client_ref || newRef(), captured_at: new Date().toISOString(), ...item })
    queue.write(items)
    return items.length
  },
  get size() { return queue.read().length },
  clear() { queue.write([]) },
  async flush() {
    const items = queue.read()
    if (!items.length || !navigator.onLine || !token) return { flushed: 0, results: [] }
    const payload = items.map(i => ({
      client_ref: i.client_ref, kind: i.kind, plot_id: i.plot_id,
      payload: i.payload, captured_at: i.captured_at,
    }))
    const out = await send('/api/sync', { items: payload })
    const settled = new Set(out.results
      .filter(r => ['accepted', 'duplicate', 'rejected'].includes(r.state))
      .map(r => r.client_ref))
    queue.write(items.filter(i => !settled.has(i.client_ref)))
    return { flushed: settled.size, results: out.results }
  },
}

export function newRef() {
  return 'q-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8)
}

/* ── the surface ───────────────────────────────────────────────────────── */
export const api = {
  // meta
  health: () => get('/api/health'),
  ready: () => get('/api/ready', { cache: false }),
  reference: () => get('/api/reference'),

  // auth
  register: (body) => send('/api/auth/register', body),
  login: (identifier, password) => send('/api/auth/login', { identifier, password }),
  logout: () => send('/api/auth/logout'),
  me: () => get('/api/auth/me', { cache: true }),
  resetRequest: (identifier) => send('/api/auth/password/reset-request', { identifier }),
  resetPassword: (token_, new_password) => send('/api/auth/password/reset', { token: token_, new_password }),
  changePassword: (current_password, new_password) =>
    send('/api/auth/password/change', { current_password, new_password }),

  // fields
  plots: () => get('/api/plots'),
  plot: (id) => get(`/api/plots/${id}`),
  createPlot: (body) => send('/api/plots', body),
  patchPlot: (id, body) => send(`/api/plots/${id}`, body, 'PATCH'),
  newCycle: (id, body) => send(`/api/plots/${id}/cycles`, body),
  history: (id) => get(`/api/plots/${id}/history`),

  // the crop journey — one request for the whole calendar screen
  cropCalendar: (id, lang) =>
    get(`/api/crop-calendar/${id}${lang ? `?lang=${lang}` : ''}`),

  // risk
  risk: (id) => get(`/api/risk/${id}`),
  forecast: (id) => get(`/api/risk/${id}/forecast`),
  fieldHealth: (id) => get(`/api/fields/${id}/health`),
  today: (id) => get(`/api/fields/${id}/today`, { cache: true }),
  nearby: (id, problem) => get(`/api/fields/${id}/nearby${problem ? `?problem=${problem}` : ''}`),

  // observations
  scan: (plot_id, file, extra = {}) =>
    send('/api/observations', fd({ plot_id, image: file, ...extra })),
  observation: (id) => get(`/api/observations/${id}`, { cache: false }),
  observations: (plot_id) => get(`/api/observations?plot_id=${plot_id}`),
  questions: (id) => get(`/api/observations/${id}/questions`, { cache: false }),
  answer: (id, answers) => send(`/api/observations/${id}/answers`, { answers }),
  askExpert: (id, body) => send(`/api/observations/${id}/expert-review`, body),

  // traps
  traps: (plot_id) => get(`/api/traps?plot_id=${plot_id}`),
  createTrap: (body) => send('/api/traps', body),
  trapCount: (trap_id, body) => send(`/api/traps/${trap_id}/counts`, body),
  trapScan: (trap_id, file, manual_count) =>
    send(`/api/traps/${trap_id}/scan`, fd({ image: file, manual_count })),
  trapSeries: (trap_id) => get(`/api/traps/${trap_id}/series`),

  // decisions
  threshold: (body) => send('/api/threshold', body),
  shouldISpray: (plot_id, target) =>
    get(`/api/decisions/${plot_id}/should-i-spray?target=${target}`, { cache: false }),
  recommendations: (plot_id, target) =>
    get(`/api/recommendations/${plot_id}?target=${target}`, { cache: false }),
  apply: (body) => send('/api/applications', body),
  ledger: (plot_id) => get(`/api/ledger${plot_id ? `?plot_id=${plot_id}` : ''}`),

  // follow-up
  followups: (plot_id) => get(`/api/followups${plot_id ? `?plot_id=${plot_id}` : ''}`),
  rescan: (id, file) => send(`/api/followups/${id}/rescan`, fd({ image: file })),

  // advisory
  advisory: (plot_id, target, lang) =>
    get(`/api/advisory?plot_id=${plot_id}&target=${target}&lang=${lang || 'mr'}`, { cache: false }),

  // saathi — the grounded assistant
  saathiAsk: (question, plot_id, lang) =>
    send('/api/saathi/ask', { question, plot_id: plot_id || undefined, lang: lang || 'mr' }),
  saathiSuggestions: (lang) => get(`/api/saathi/suggestions?lang=${lang || 'mr'}`),

  // agronomy — soil, water, weeds
  soilReference: () => get('/api/agronomy/soil/reference'),
  soilSelfTest: (body) => send('/api/agronomy/soil/self-test', body),
  soilLab: (body) => send('/api/agronomy/soil/lab', body),
  soilHistory: (plot_id) => get(`/api/agronomy/soil/${plot_id}`, { cache: false }),
  irrigation: (plot_id) => get(`/api/agronomy/irrigation/${plot_id}`, { cache: true }),
  logIrrigation: (plot_id, body) => send(`/api/agronomy/irrigation/${plot_id}`, body),
  weedCheck: (plot_id, file) => send('/api/agronomy/weeds', fd({ plot_id, image: file })),
  weedSeries: (plot_id) => get(`/api/agronomy/weeds/${plot_id}`, { cache: false }),

  // community — the feed, the thread, and the signal it produces
  communityMeta: () => get('/api/community/meta'),
  community: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ).toString()
    return get(`/api/community${q ? `?${q}` : ''}`, { cache: true })
  },
  communityPost: (id) => get(`/api/community/${id}`, { cache: false }),
  communityCreate: (body) => send('/api/community', body),
  communityImage: (postId, file) => send(`/api/community/${postId}/images`, fd({ image: file })),
  communityComment: (id, body, parent_id) =>
    send(`/api/community/${id}/comments`, { body, parent_id }),
  communityReact: (id, kind, on = true, target_type = 'post') =>
    send(`/api/community/${id}/reactions`, { kind, on, target_type }),
  communityReactComment: (id, kind, on = true) =>
    send(`/api/community/comments/${id}/reactions`, { kind, on, target_type: 'comment' }),
  communityReport: (id, reason, note, target_type = 'post') =>
    send(`/api/community/${id}/report`, { reason, note, target_type }),
  communityBlock: (id, on = true) => send(`/api/community/${id}/block?on=${on}`),
  communityWithdraw: (id) => send(`/api/community/${id}`, undefined, 'DELETE'),
  communitySearch: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ).toString()
    return get(`/api/community/search?${q}`, { cache: false })
  },
  communitySaved: () => get('/api/community/me/saved', { cache: false }),
  communityFollow: (topicId, on = true) =>
    send(`/api/community/topics/${encodeURIComponent(topicId)}/follow?on=${on}`),
  mySignals: () => get('/api/community/signals/mine', { cache: true }),
  expertInbox: () => get('/api/community/expert/inbox', { cache: false }),
  expertRespond: (postId, body) => send(`/api/community/${postId}/expert-response`, body),
  officerSignals: (refresh) => get(`/api/community/signals${refresh ? '?refresh=true' : ''}`,
    { cache: false }),
  officerSignal: (id) => get(`/api/community/signals/${id}`, { cache: false }),
  confirmSignal: (id, body) => send(`/api/community/signals/${id}/confirm`, body),
  moderationQueue: () => get('/api/community/moderation/queue', { cache: false }),
  moderate: (id, body) => send(`/api/community/moderation/${id}`, body),

  // notifications
  notifications: (plot_id) => get(`/api/notifications${plot_id ? `?plot_id=${plot_id}` : ''}`),
  markRead: (plot_id) => send(`/api/notifications/read${plot_id ? `?plot_id=${plot_id}` : ''}`),

  // expert
  expertCases: (status) => get(`/api/expert/cases${status ? `?status=${status}` : ''}`, { cache: false }),
  expertCase: (id) => get(`/api/expert/cases/${id}`, { cache: false }),
  expertReview: (id, body) => send(`/api/expert/cases/${id}/review`, body),
  modelAgreement: () => get('/api/expert/model-agreement'),

  // officer
  officerSummary: (days) => get(`/api/officer/summary${days ? `?days=${days}` : ''}`),
  hotspots: (problem, crop) =>
    get(`/api/officer/hotspots?problem=${problem || 'late_blight'}${crop ? `&crop=${crop}` : ''}`),
  outbreaks: (problem) => get(`/api/officer/outbreaks${problem ? `?problem=${problem}` : ''}`),
  queue: (capacity) => get(`/api/officer/queue?capacity=${capacity || 5}`),
  route: (capacity) => get(`/api/officer/route?capacity=${capacity || 5}`),
  assign: (body) => send('/api/officer/assignments', body),
  assignments: (status) => get(`/api/officer/assignments${status ? `?status=${status}` : ''}`),
  closeAssignment: (id, body) => send(`/api/officer/assignments/${id}/close`, body),
  audit: () => get('/api/officer/audit'),

  // admin
  claims: (q = '') => get(`/api/admin/claims${q}`, { cache: false }),
  verifyClaim: (id, body) => send(`/api/admin/claims/${id}/verify`, body),
  claimStatus: (id, body) => send(`/api/admin/claims/${id}/status`, body),
  auditLog: () => get('/api/admin/audit-log', { cache: false }),

  // demo (only mounted when DEMO_MODE=true)
  scenarios: () => get('/api/demo/scenarios', { cache: false }),
  setScenario: (key, plot_id) =>
    send(`/api/demo/scenario?key=${key}${plot_id ? `&plot_id=${plot_id}` : ''}`),
}
