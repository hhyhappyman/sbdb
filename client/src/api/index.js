import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// ── Auth ───────────────────────────────────────────────────────────────────
export const login = (username, password) =>
  api.post('/auth/login', { username, password }).then(r => r.data)

export const logout = () =>
  api.post('/auth/logout').then(r => r.data)

export const changePassword = (current_password, new_password) =>
  api.put('/auth/password', { current_password, new_password }).then(r => r.data)

export const workerLogin = (username, password) =>
  api.post('/auth/worker-login', { username, password }).then(r => r.data)

// ── Manual entry (근무자 수동 입력) ──────────────────────────────────────────
export const getClientIp = () =>
  api.get('/manual/client-ip').then(r => r.data)

export const createManualEntry = (data) =>
  api.post('/manual/entries', data).then(r => r.data)

export const listManualEntries = (date) =>
  api.get('/manual/entries', { params: { date } }).then(r => r.data)

export const deleteManualEntry = (id) =>
  api.delete(`/manual/entries/${id}`).then(r => r.data)

export const getCampaignWorker = (date) =>
  api.get('/manual/campaign-worker', { params: { date } }).then(r => r.data)

export const setCampaignWorker = (broadcast_date, worker_name) =>
  api.post('/manual/campaign-worker', { broadcast_date, worker_name }).then(r => r.data)

// ── Dashboard ──────────────────────────────────────────────────────────────
export const getDashboard = (year, month, type) =>
  api.get('/dashboard', { params: { year, month, type } }).then(r => r.data)

// ── Calendar ───────────────────────────────────────────────────────────────
export const getCalendar = (year, month, type) =>
  api.get('/calendar', { params: { year, month, type } }).then(r => r.data)

export const getDayDetail = (date, type) =>
  api.get('/calendar/day', { params: { date, type } }).then(r => r.data)

// ── Period ─────────────────────────────────────────────────────────────────
export const getPeriod = (params) =>
  api.get('/period', { params }).then(r => r.data)

// ── Items (소재 검색) ────────────────────────────────────────────────────────
export const searchItems = (q, limit = 30) =>
  api.get('/items', { params: { q, limit } }).then(r => r.data)

// ── Report ─────────────────────────────────────────────────────────────────
export const getMonthlyReport = (item, year, month) =>
  api.get('/report', { params: { item, year, month } }).then(r => r.data)

export const getMonthlyPdfUrl = (item, year, month) =>
  `/api/report/pdf?item=${encodeURIComponent(item)}&year=${year}&month=${month}`

export const getDailyReport = (date) =>
  api.get('/report/daily', { params: { date } }).then(r => r.data)

export const getDailyPdfUrl = (date) =>
  `/api/report/daily/pdf?date=${date}`

export const getDisasterReport = (date) =>
  api.get('/report/disaster', { params: { date } }).then(r => r.data)

export const getDisasterPdfUrl = (date) =>
  `/api/report/disaster/pdf?date=${date}`

export const getDailySummary = (date, type) =>
  api.get('/report/daily-summary', { params: { date, type } }).then(r => r.data)

// ── Ingest ─────────────────────────────────────────────────────────────────
export const ingestCml = (file) => {
  const fd = new FormData(); fd.append('file', file)
  return api.post('/ingest/cml', fd).then(r => r.data)
}

export const ingestApst = (file) => {
  const fd = new FormData(); fd.append('file', file)
  return api.post('/ingest/apst', fd).then(r => r.data)
}

export const ingestDdr1 = (file, broadcastDate) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('broadcast_date', broadcastDate)
  return api.post('/ingest/ddr1', fd).then(r => r.data)
}

// ── Advertisers ────────────────────────────────────────────────────────────
export const getAdvertisers = () =>
  api.get('/advertisers').then(r => r.data)

export const createAdvertiser = (data) =>
  api.post('/advertisers', data).then(r => r.data)

export const updateAdvertiser = (itemName, data) =>
  api.put(`/advertisers/${encodeURIComponent(itemName)}`, data).then(r => r.data)

export const deleteAdvertiser = (itemName) =>
  api.delete(`/advertisers/${encodeURIComponent(itemName)}`).then(r => r.data)

// ── FTP ────────────────────────────────────────────────────────────────────
export const ftpTest = () =>
  api.get('/ftp/test').then(r => r.data)

export const ftpFetch = (date) =>
  api.post('/ftp/fetch', null, { params: { date } }).then(r => r.data)

export const ftpFetchYesterday = () =>
  api.post('/ftp/fetch-yesterday').then(r => r.data)

// ── Settings ───────────────────────────────────────────────────────────────
export const getSettings = () =>
  api.get('/settings').then(r => r.data)

export const updateSettings = (data) =>
  api.put('/settings', data).then(r => r.data)

// ── Logs ───────────────────────────────────────────────────────────────────
export const getLogs = (limit = 200) =>
  api.get('/logs', { params: { limit } }).then(r => r.data)

export const clearLogs = () =>
  api.delete('/logs').then(r => r.data)
