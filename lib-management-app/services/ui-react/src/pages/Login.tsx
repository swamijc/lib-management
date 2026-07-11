import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { Loader2, ShieldCheck, BarChart3, ClipboardCheck } from 'lucide-react'
import { parseApiError } from '../api/client'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login, token } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (token) return <Navigate to="/dashboard" replace />

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(username, password)
    } catch (err: unknown) {
      setError(parseApiError(err, 'Invalid credentials. Please try again.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4" style={{
      backgroundImage: 'radial-gradient(circle at 20% 10%, rgba(245,98,0,0.18), transparent 35%), linear-gradient(180deg, #0f172a 0%, #111827 100%)',
    }}>
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center h-14 px-4 rounded-2xl bg-white/95 mb-4 border border-slate-200 shadow-md">
            <img
              src="https://www.photon.com/themes/custom/photon/images/logo_photon.svg"
              alt="Photon Logo"
              className="h-8 w-auto object-contain"
            />
          </div>
          <h1 className="text-3xl font-bold text-white">SDK Management</h1>
          <p className="text-slate-400 mt-1">Enterprise Upgrade Platform</p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-2xl p-8">
          <h2 className="text-xl font-semibold text-slate-900 mb-6">Sign in to your account</h2>

          {error && (
            <div className="mb-4 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Username</label>
              <input
                className="input"
                type="text"
                placeholder="admin"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
              <input
                className="input"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full justify-center py-2.5 mt-2">
              {loading ? <Loader2 size={16} className="animate-spin" /> : null}
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <p className="mt-6 text-xs text-center text-slate-400">
            Default: <strong>admin</strong> / <strong>admin123</strong>
          </p>

          <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
            <p className="text-[11px] text-slate-600 font-medium">Business visibility after sign-in:</p>
            <p className="text-[11px] text-slate-500 mt-1">Executive KPIs, governance SLA watchlists, and portfolio-level risk controls.</p>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-2">
            <div className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-2.5 flex items-start gap-2">
              <ShieldCheck size={14} className="text-blue-600 mt-0.5" />
              <div>
                <p className="text-[11px] font-semibold text-blue-700">Enterprise Security Posture</p>
                <p className="text-[11px] text-blue-800 mt-0.5">Role-aware access, auditability, and governance-first controls are enabled.</p>
              </div>
            </div>
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2.5 flex items-start gap-2">
              <BarChart3 size={14} className="text-emerald-600 mt-0.5" />
              <div>
                <p className="text-[11px] font-semibold text-emerald-700">Business Insights</p>
                <p className="text-[11px] text-emerald-800 mt-0.5">Portfolio risk, SLA trends, and run reliability analytics are available on entry.</p>
              </div>
            </div>
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 flex items-start gap-2">
              <ClipboardCheck size={14} className="text-amber-600 mt-0.5" />
              <div>
                <p className="text-[11px] font-semibold text-amber-700">Compliance Visibility</p>
                <p className="text-[11px] text-amber-800 mt-0.5">Decision trails, approval evidence, and operational history are traceable end-to-end.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
