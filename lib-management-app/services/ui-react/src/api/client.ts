import axios from 'axios'

// In production the build sets VITE_API_BASE_URL to the Container Apps backend URL.
// In dev the Vite proxy handles routing so '/' works fine.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/'

const api = axios.create({ baseURL: API_BASE, timeout: 30000 })

type ApiErrorBody = {
  detail?: string | { msg?: string; loc?: unknown[] }[] | unknown
  message?: string
  error?: {
    code?: string
    message?: string
    detail?: string
  }
}

// Parse backend and gateway error shapes into one user-facing message.
export function parseApiError(err: unknown, fallback = 'Request failed'): string {
  const maybe = err as { message?: string; response?: { data?: ApiErrorBody } }
  const data = maybe?.response?.data

  // FastAPI validation errors return detail as an array of {loc, msg, type}
  const rawDetail = data?.detail
  const detail = Array.isArray(rawDetail)
    ? rawDetail.map((d) => (typeof d === 'object' && d !== null && 'msg' in d ? (d as { msg: string }).msg : String(d))).join('; ')
    : typeof rawDetail === 'string' ? rawDetail : undefined

  return (
    data?.error?.message
    ?? detail
    ?? data?.message
    ?? maybe?.message
    ?? fallback
  )
}

// Inject JWT on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Unwrap standard { success, data } envelope from all backend responses
api.interceptors.response.use(
  (r) => {
    if (r.data && typeof r.data === 'object' && 'success' in r.data && 'data' in r.data) {
      return { ...r, data: r.data.data }
    }
    return r
  },
  (err) => Promise.reject(err)
)

// Handle 401 → redirect to login
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (username: string, password: string) =>
    api.post('/auth/token', new URLSearchParams({ username, password }), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }),
  me: () => api.get('/auth/me'),
  getUsers: () => api.get('/auth/users'),
  createUser: (data: object) => api.post('/auth/users', data),
  updateUser: (id: number, data: object) => api.put(`/auth/users/${id}`, data),
  deactivateUser: (id: number) => api.delete(`/auth/users/${id}`),
  deleteUserPermanent: (id: number) => api.delete(`/auth/users/${id}/permanent`),
  changePassword: (oldPw: string, newPw: string) =>
    api.post('/auth/change-password', { old_password: oldPw, new_password: newPw }),
}

// ── Libraries ─────────────────────────────────────────────────────────────────
export const libraryApi = {
  list: (params?: object) => api.get('/api/v1/libraries', { params: { limit: 1000, ...params } }),
  get: (id: number) => api.get(`/api/v1/libraries/${id}`),
  create: (data: object) => api.post('/api/v1/libraries', data),
  update: (id: number, data: object) => api.put(`/api/v1/libraries/${id}`, data),
  delete: (id: number) => api.delete(`/api/v1/libraries/${id}`),
  critical: () => api.get('/api/v1/libraries/critical'),
  byPlatform: (platform: string) => api.get(`/api/v1/libraries/platform/${platform}`),
  versionHistory: (id: number) => api.get(`/api/v1/version-history/${id}`),
  // All historical versions from registry
  versions: (id: number) => api.get(`/api/v1/libraries/${id}/versions`),
  fetchVersions: (id: number) => api.post(`/api/v1/libraries/${id}/fetch-versions`),
  setCurrentVersion: (id: number, data: { version: string; updated_by: string; reason?: string }) =>
    api.post(`/api/v1/libraries/${id}/set-current-version`, data),
  // Bulk admin operations
  syncMavenUrls: () => api.post('/api/v1/libraries/sync-maven-urls'),
  bulkFetchVersions: () => api.post('/api/v1/libraries/bulk-fetch-versions'),
  bulkFetchStatus: () => api.get('/api/v1/libraries/bulk-fetch-versions/status'),
}

// ── Recommendations ───────────────────────────────────────────────────────────
export const recApi = {
  list: () => api.get('/api/v1/recommendations'),
  get: (libId: number) => api.get(`/api/v1/recommendations/${libId}`),
  chatAsk: (data: object) => api.post('/api/v1/recommendations/chat/ask', data),
  llmStatus: () => api.post('/api/v1/recommendations/test-llm', {}),
}

// ── Scheduler ─────────────────────────────────────────────────────────────────
export const schedulerApi = {
  getSchedule: () => api.get('/api/v1/schedule'),
  updateSchedule: (data: object) => api.put('/api/v1/schedule', data),
  triggerRun: () => api.post('/api/v1/run/now'),
  retryStage: (data: { source_run_id: string; step: string }) => api.post('/api/v1/run/retry', data),
  retryFromHere: (data: { source_run_id: string; step: string }) => api.post('/api/v1/run/retry-from-here', data),
  getRuns: () => api.get('/api/v1/runs'),
  getRun: (id: string) => api.get(`/api/v1/runs/${id}`),
  cleanupHistory: (params?: { retention_days?: number; include_partial?: boolean }) =>
    api.delete('/api/v1/pipeline-runs/history/cleanup', { params }),
}

// ── Lifecycle / HITL ──────────────────────────────────────────────────────────
export const lifecycleApi = {
  list: (params?: object) => api.get('/api/v1/lifecycle', { params }),
  get: (libId: number) => api.get(`/api/v1/lifecycle/${libId}`),
  init: (data: object) => api.post('/api/v1/lifecycle', data),
  update: (id: number, data: object) => api.put(`/api/v1/lifecycle/${id}`, data),
  complete: (id: number, data: object) => api.put(`/api/v1/lifecycle/${id}/complete`, data),
  reject: (id: number, data: object) => api.put(`/api/v1/lifecycle/${id}/reject`, data),
  approveNoAction: (id: number, data: object) => api.put(`/api/v1/lifecycle/${id}/approve-no-action`, data),
  pendingReview: () => api.get('/api/v1/lifecycle/pending/review'),
  /** Move to In Progress state */
  markInProgress: (id: number, data: { status?: string; actioned_by: string; skip_reason?: string; target_version?: string }) =>
    api.put(`/api/v1/lifecycle/${id}/in-progress`, { status: 'In Progress', ...data }),
  /** Decline from In Progress — rolls back to Acknowledged, clears target_version */
  decline: (id: number, data: { actioned_by: string }) =>
    api.put(`/api/v1/lifecycle/${id}/decline`, data),
  /** Set a version as Active — comment is mandatory */
  setActive: (id: number, data: { target_version: string; comment: string; actioned_by: string }) =>
    api.put(`/api/v1/lifecycle/${id}/set-active`, data),
}

// ── Audit ─────────────────────────────────────────────────────────────────────
export const auditApi = {
  list: (params?: object) => api.get('/api/v1/audit-log', { params }),
}

// ── LLM Analytics ─────────────────────────────────────────────────────────────
export const analyticsApi = {
  usage: () => api.get('/api/v1/llm/usage'),
}

// ── CVE ───────────────────────────────────────────────────────────────────────
export const cveApi = {
  scan: (libId: number, force = false) =>
    api.get(`/api/v1/cve/${libId}`, { params: { force_refresh: force } }),
  list: () => api.get('/api/v1/cve'),
}

// ── Teams ─────────────────────────────────────────────────────────────────────
export const teamsApi = {
  list: () => api.get('/api/v1/teams'),
  get: (id: number) => api.get(`/api/v1/teams/${id}`),
  create: (data: object) => api.post('/api/v1/teams', data),
  update: (id: number, data: object) => api.put(`/api/v1/teams/${id}`, data),
  delete: (id: number) => api.delete(`/api/v1/teams/${id}`),
  assign: (data: object) => api.post('/api/v1/teams/assign', data),
  libraryTeams: (libId: number) => api.get(`/api/v1/teams/library/${libId}`),
}

// ── Notifications ───────────────────────────────────────────────────────────
export const notificationsApi = {
  list: () => api.get('/api/v1/notifications'),
}

// ── SLA ───────────────────────────────────────────────────────────────────────
export const slaApi = {
  summary: () => api.get('/api/v1/sla/summary'),
  overdue: () => api.get('/api/v1/sla/overdue'),
  approaching: (days = 30) => api.get('/api/v1/sla/approaching', { params: { days_ahead: days } }),
  releaseNotes: (libId: number) => api.get(`/api/v1/sla/release-notes/${libId}`),
}

// ── Settings ──────────────────────────────────────────────────────────────────
export const settingsApi = {
  getLlm: () => api.get('/api/v1/settings/llm'),
  updateLlm: (data: object) => api.put('/api/v1/settings/llm', data),
  getPrompts: () => api.get('/api/v1/settings/prompts'),
  upsertPrompt: (key: string, data: object) => api.put(`/api/v1/settings/prompts/${key}`, data),
  getApp: () => api.get('/api/v1/settings/app'),
  updateApp: (key: string, data: { value: string; updated_by: string }) =>
    api.put(`/api/v1/settings/app/${key}`, data),
}

// ── Health ────────────────────────────────────────────────────────────────────
export const healthApi = {
  gateway: () => api.get('/health'),
  services: () => api.get('/health/services'),
  runtime: () => api.get('/health/runtime'),
}

// ── Business Analytics ───────────────────────────────────────────────────────
export const businessApi = {
  weeklyDigest: () => api.get('/api/v1/business/weekly-digest'),
}

export default api
