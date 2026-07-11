import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { UserPlus, Trash2, Shield, Eye, RefreshCw, Loader2, X, User, Key, Pencil } from 'lucide-react'
import ExecutiveTriad from '../components/ExecutiveTriad'
import { PaginatedSectionFooter, PaginatedSectionHeader } from '../components/PaginatedSectionControls'
import SectionBand from '../components/SectionBand'
import SectionCard from '../components/SectionCard'
import { authApi, parseApiError } from '../api/client'
import { useAuth } from '../context/AuthContext'

interface AppUser {
  id: number
  username: string
  email?: string
  full_name?: string | null
  role: 'admin' | 'viewer'
  is_active: boolean
  created_at?: string
}

// ── Delete Confirm Modal ───────────────────────────────────────────────────────
function DeleteUserModal({
  user, isPending, onConfirm, onCancel,
}: { user: AppUser; isPending: boolean; onConfirm: () => void; onCancel: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onCancel}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
            <Trash2 size={18} className="text-red-600" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-slate-800">Deactivate User</h2>
            <p className="text-xs text-slate-500">The user will be locked out immediately</p>
          </div>
        </div>
        <p className="text-sm text-slate-600 mb-5">
          Are you sure you want to deactivate{' '}
          <span className="font-semibold text-slate-800">@{user.username}</span>?
          They will no longer be able to log in.
        </p>
        <div className="flex gap-3 justify-end">
          <button className="btn-secondary" onClick={onCancel} disabled={isPending}>Cancel</button>
          <button
            className="px-4 py-2 text-sm font-semibold bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors flex items-center gap-2 disabled:opacity-60"
            onClick={onConfirm}
            disabled={isPending}
          >
            {isPending
              ? <><Loader2 size={13} className="animate-spin" /> Deactivating…</>
              : <><Trash2 size={13} /> Deactivate</>}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Edit User Modal ───────────────────────────────────────────────────────────
function EditUserModal({
  user, onClose, onSuccess,
}: { user: AppUser; onClose: () => void; onSuccess: () => void }) {
  const [form, setForm] = useState({
    full_name: user.full_name ?? '',
    email:     user.email ?? '',
    role:      user.role,
  })
  const [error, setError] = useState('')
  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const editMut = useMutation({
    mutationFn: () => authApi.updateUser(user.id, {
      full_name: form.full_name.trim() || null,
      email:     form.email.trim() || undefined,
      role:      form.role,
    }),
    onSuccess: () => { onSuccess(); onClose() },
    onError: (e: unknown) => setError(parseApiError(e, 'Failed to update user')),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <Pencil size={15} className="text-primary-600" />
            <h2 className="text-base font-semibold text-slate-800">Edit User — @{user.username}</h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>

        <div className="px-6 py-5 space-y-4">
          {/* Read-only username */}
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-slate-50 border border-slate-200">
            <div className="w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0">
              <span className="text-sm font-bold text-primary-700 uppercase">{user.username.charAt(0)}</span>
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-800">@{user.username}</p>
              <p className="text-[10px] text-slate-400">Username cannot be changed</p>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Full Name</label>
            <div className="relative">
              <User size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                className="input pl-8 text-sm"
                placeholder="e.g. John Doe"
                value={form.full_name}
                onChange={(e) => set('full_name', e.target.value)}
                autoFocus
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Email</label>
            <input
              type="email"
              className="input text-sm"
              placeholder="user@example.com"
              value={form.email}
              onChange={(e) => set('email', e.target.value)}
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Role</label>
            <div className="grid grid-cols-2 gap-3">
              {(['viewer', 'admin'] as const).map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => set('role', r)}
                  className={`flex items-center gap-2.5 p-3 rounded-xl border-2 transition-all text-left ${
                    form.role === r
                      ? r === 'admin'
                        ? 'border-primary-500 bg-primary-50'
                        : 'border-slate-400 bg-slate-50'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  {r === 'admin'
                    ? <Shield size={16} className={form.role === 'admin' ? 'text-primary-600' : 'text-slate-400'} />
                    : <Eye    size={16} className={form.role === 'viewer' ? 'text-slate-600' : 'text-slate-400'} />
                  }
                  <div>
                    <p className="text-xs font-semibold capitalize text-slate-800">{r}</p>
                    <p className="text-[10px] text-slate-400">{r === 'admin' ? 'Full access' : 'Read only'}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700">❌ {error}</div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-slate-200 flex justify-end gap-3">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary flex items-center gap-2"
            onClick={() => { setError(''); editMut.mutate() }}
            disabled={editMut.isPending}
          >
            {editMut.isPending
              ? <><Loader2 size={14} className="animate-spin" /> Saving…</>
              : <><Pencil size={14} /> Save Changes</>}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Create User Modal ──────────────────────────────────────────────────────────
function CreateUserModal({
  onClose, onSuccess,
}: { onClose: () => void; onSuccess: () => void }) {
  const [form, setForm] = useState({ username: '', password: '', email: '', role: 'viewer' as 'admin' | 'viewer' })
  const [error, setError] = useState('')

  const createMut = useMutation({
    mutationFn: () => authApi.createUser({
        username: form.username,
        password: form.password,
        email: form.email || `${form.username}@lib-mgmt.local`,
        role: form.role,
      }),
    onSuccess: () => { onSuccess(); onClose() },
    onError: (e: unknown) => setError(parseApiError(e, 'Failed to create user')),
  })

  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <div className="flex items-center gap-2">
            <UserPlus size={16} className="text-primary-600" />
            <h2 className="text-base font-semibold text-slate-800">Create New User</h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X size={18} /></button>
        </div>

        <div className="px-6 py-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Username <span className="text-red-500">*</span>
            </label>
            <div className="relative">
              <User size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                className="input pl-8 text-sm"
                placeholder="e.g. john.doe"
                value={form.username}
                onChange={(e) => set('username', e.target.value.toLowerCase().replace(/\s/g, ''))}
                autoFocus
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Email</label>
            <input
              type="email"
              className="input text-sm"
              placeholder={form.username ? `${form.username}@lib-mgmt.local` : 'user@example.com'}
              value={form.email}
              onChange={(e) => set('email', e.target.value)}
            />
            <p className="text-[10px] text-slate-400 mt-0.5">Leave blank to auto-generate from username</p>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Password <span className="text-red-500">*</span>
            </label>
            <div className="relative">
              <Key size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="password"
                className="input pl-8 text-sm"
                placeholder="Minimum 8 characters"
                value={form.password}
                onChange={(e) => set('password', e.target.value)}
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Role</label>
            <div className="grid grid-cols-2 gap-3">
              {(['viewer', 'admin'] as const).map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => set('role', r)}
                  className={`flex items-center gap-2.5 p-3 rounded-xl border-2 transition-all text-left ${
                    form.role === r
                      ? r === 'admin'
                        ? 'border-primary-500 bg-primary-50'
                        : 'border-slate-400 bg-slate-50'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  {r === 'admin'
                    ? <Shield size={16} className={form.role === 'admin' ? 'text-primary-600' : 'text-slate-400'} />
                    : <Eye size={16} className={form.role === 'viewer' ? 'text-slate-600' : 'text-slate-400'} />
                  }
                  <div>
                    <p className="text-xs font-semibold capitalize text-slate-800">{r}</p>
                    <p className="text-[10px] text-slate-400">
                      {r === 'admin' ? 'Full access' : 'Read only'}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700">
              ❌ {error}
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-slate-200 flex justify-end gap-3">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary flex items-center gap-2"
            onClick={() => { setError(''); createMut.mutate() }}
            disabled={!form.username.trim() || form.password.length < 8 || createMut.isPending}
          >
            {createMut.isPending
              ? <><Loader2 size={14} className="animate-spin" /> Creating…</>
              : <><UserPlus size={14} /> Create User</>}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main Users Page ────────────────────────────────────────────────────────────
export default function Users() {
  const qc = useQueryClient()
  const { user: currentUser } = useAuth()
  const [activePage, setActivePage] = useState(1)
  const [activePageSize, setActivePageSize] = useState(10)
  const [inactivePage, setInactivePage] = useState(1)
  const [inactivePageSize, setInactivePageSize] = useState(10)
  const [showCreate, setShowCreate] = useState(false)
  const [deleteUser, setDeleteUser] = useState<AppUser | null>(null)
  const [permanentDeleteUser, setPermanentDeleteUser] = useState<AppUser | null>(null)
  const [editUser,   setEditUser]   = useState<AppUser | null>(null)
  const [pendingDeactivateId, setPendingDeactivateId] = useState<number | null>(null)
  const [pendingReactivateId, setPendingReactivateId] = useState<number | null>(null)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['users'],
    queryFn: () => authApi.getUsers(),
  })

  // API returns { users: [...] } (not the standard { data: [...] } wrapper)
  const usersRaw = (data?.data as { users?: AppUser[] } | undefined)
  const users: AppUser[] = usersRaw?.users ?? []
  const active   = users.filter((u) => u.is_active)
  const inactive = users.filter((u) => !u.is_active)
  const activeTotalPages = Math.max(1, Math.ceil(active.length / activePageSize))
  const safeActivePage = Math.min(activePage, activeTotalPages)
  const activeStart = (safeActivePage - 1) * activePageSize
  const activeEnd = Math.min(activeStart + activePageSize, active.length)
  const pagedActive = useMemo(() => active.slice(activeStart, activeEnd), [active, activeStart, activeEnd])

  const inactiveTotalPages = Math.max(1, Math.ceil(inactive.length / inactivePageSize))
  const safeInactivePage = Math.min(inactivePage, inactiveTotalPages)
  const inactiveStart = (safeInactivePage - 1) * inactivePageSize
  const inactiveEnd = Math.min(inactiveStart + inactivePageSize, inactive.length)
  const pagedInactive = useMemo(() => inactive.slice(inactiveStart, inactiveEnd), [inactive, inactiveStart, inactiveEnd])

  const deactivateMut = useMutation({
    mutationFn: (id: number) => authApi.deactivateUser(id),
    onMutate: (id: number) => setPendingDeactivateId(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] })
      setDeleteUser(null)
    },
    onSettled: () => setPendingDeactivateId(null),
  })

  const reactivateMut = useMutation({
    mutationFn: (id: number) => authApi.updateUser(id, { is_active: true }),
    onMutate: (id: number) => setPendingReactivateId(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
    onSettled: () => setPendingReactivateId(null),
  })

  const permanentDeleteMut = useMutation({
    mutationFn: (id: number) => authApi.deleteUserPermanent(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] })
      setPermanentDeleteUser(null)
    },
    onError: () => setPermanentDeleteUser(null),
  })

  const roleColor = (role: string) =>
    role === 'admin'
      ? 'bg-primary-100 text-primary-700 border-primary-200'
      : 'bg-slate-100 text-slate-600 border-slate-200'

  // Protection: cannot deactivate root admin or yourself
  const isProtected = (u: AppUser) => {
    if (u.username === 'admin') return { protected: true, reason: 'Root admin cannot be deactivated' }
    if (u.username === currentUser?.username) return { protected: true, reason: 'You cannot deactivate your own account' }
    return { protected: false, reason: 'Deactivate user' }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">Access Management</h1>
          <p className="page-subtitle">
            {active.length} active user{active.length !== 1 ? 's' : ''} · {inactive.length} inactive
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <button className="btn-secondary py-1.5 text-xs" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw size={12} className={isLoading ? 'animate-spin' : ''} /> Refresh
          </button>
          <button className="btn-primary py-1.5 px-3 text-xs sm:text-sm whitespace-nowrap" onClick={() => setShowCreate(true)}>
            <UserPlus size={14} /> New User
          </button>
        </div>
      </div>

      <ExecutiveTriad
        impact={`${active.length} active users and ${inactive.length} inactive users are currently under governance.`}
        owner="Access Governance Administrator"
        nextAction={inactive.length > 0 ? `Review ${inactive.length} inactive account${inactive.length === 1 ? '' : 's'} and confirm reactivation/deprovision decisions.` : 'Validate role assignments and maintain least-privilege access posture.'}
        tone={inactive.length > 0 ? 'warning' : 'positive'}
      />

      {/* Stats strip */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Total Users',   value: users.length,                           color: 'text-slate-800' },
          { label: 'Active',        value: active.length,                          color: 'text-green-700' },
          { label: 'Administrators',value: users.filter(u => u.role==='admin').length, color: 'text-primary-700' },
        ].map(({ label, value, color }) => (
          <div key={label} className="card p-4 text-center">
            <p className={`text-3xl font-bold ${color}`}>{value}</p>
            <p className="text-xs text-slate-500 mt-1">{label}</p>
          </div>
        ))}
      </div>

      {/* Active users */}
      <SectionCard
        bandTitle="Access Operations"
        bandSubtitle="Govern identity lifecycle through paged active/inactive user ledgers and role controls."
        cardClassName="card overflow-hidden"
        header={{
          title: 'Active Users',
          totalItems: active.length,
          startIndex: activeStart,
          endIndex: activeEnd,
          pageSize: activePageSize,
          pageSizeOptions: [5, 10, 20, 50],
          onPageSizeChange: (value) => {
            setActivePageSize(value)
            setActivePage(1)
          },
          recordLabel: 'users',
        }}
        footer={active.length > 0 ? {
          page: safeActivePage,
          totalPages: activeTotalPages,
          onPrev: () => setActivePage((p) => Math.max(1, p - 1)),
          onNext: () => setActivePage((p) => Math.min(activeTotalPages, p + 1)),
        } : undefined}
      >
        {isLoading ? (
          <div className="p-8 text-center text-slate-400 text-sm flex items-center justify-center gap-2">
            <Loader2 size={14} className="animate-spin" /> Loading users…
          </div>
        ) : (
          <table className="w-full table-base">
            <thead>
              <tr>
                <th>#</th>
                <th>Username</th>
                <th>Role</th>
                <th>Status</th>
                <th>Created</th>
                <th className="w-32"></th>
              </tr>
            </thead>
            <tbody>
              {pagedActive.map((u, i) => (
                <tr key={u.id}>
                  <td className="text-slate-400 text-xs">{activeStart + i + 1}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0">
                        <span className="text-xs font-bold text-primary-700 uppercase">
                          {u.username.charAt(0)}
                        </span>
                      </div>
                      <span className="font-medium text-slate-800 text-sm">@{u.username}</span>
                    </div>
                  </td>
                  <td>
                    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border capitalize ${roleColor(u.role)}`}>
                      {u.role === 'admin' ? '🛡 Admin' : '👁 Viewer'}
                    </span>
                  </td>
                  <td>
                    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-green-100 text-green-700 border border-green-200">
                      ● Active
                    </span>
                  </td>
                  <td className="text-xs text-slate-400">
                    {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                  </td>
                  <td>
                    <div className="flex items-center gap-2">
                      <button
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
                        onClick={() => setEditUser(u)}
                        title="Edit user"
                      >
                        <Pencil size={12} /> Edit
                      </button>
                    {(() => {
                      const { protected: prot, reason } = isProtected(u)
                      return prot ? (
                        <span
                          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-400 border border-slate-200 rounded-lg cursor-not-allowed select-none"
                          title={reason}
                        >
                          <Shield size={12} className="text-slate-300" /> Protected
                        </span>
                      ) : (
                        <button
                          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-600 border border-red-200 rounded-lg hover:bg-red-50 transition-colors"
                          onClick={() => setDeleteUser(u)}
                          title={reason}
                        >
                          <Trash2 size={12} /> Deactivate
                        </button>
                      )
                    })()}
                    </div>
                  </td>
                </tr>
              ))}
              {active.length === 0 && (
                <tr><td colSpan={6} className="text-center text-slate-400 text-sm py-6">No active users</td></tr>
              )}
            </tbody>
          </table>
        )}
      </SectionCard>

      {/* Inactive users */}
      {inactive.length > 0 && (
        <SectionCard
          cardClassName="card overflow-hidden"
          header={{
            title: 'Inactive / Deactivated',
            totalItems: inactive.length,
            startIndex: inactiveStart,
            endIndex: inactiveEnd,
            pageSize: inactivePageSize,
            pageSizeOptions: [5, 10, 20, 50],
            onPageSizeChange: (value) => {
              setInactivePageSize(value)
              setInactivePage(1)
            },
            recordLabel: 'users',
            titleClassName: 'text-sm font-semibold text-slate-500',
          }}
          footer={{
            page: safeInactivePage,
            totalPages: inactiveTotalPages,
            onPrev: () => setInactivePage((p) => Math.max(1, p - 1)),
            onNext: () => setInactivePage((p) => Math.min(inactiveTotalPages, p + 1)),
          }}
        >
          <table className="w-full table-base opacity-75">
            <thead>
              <tr>
                <th>#</th>
                <th>Username</th>
                <th>Role</th>
                <th>Status</th>
                <th>Created</th>
                <th className="w-32"></th>
              </tr>
            </thead>
            <tbody>
              {pagedInactive.map((u, i) => (
                <tr key={u.id} className="bg-slate-50">
                  <td className="text-slate-400 text-xs">{inactiveStart + i + 1}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full bg-slate-200 flex items-center justify-center flex-shrink-0">
                        <span className="text-xs font-bold text-slate-500 uppercase">
                          {u.username.charAt(0)}
                        </span>
                      </div>
                      <span className="font-medium text-slate-500 text-sm line-through">@{u.username}</span>
                    </div>
                  </td>
                  <td>
                    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full border capitalize bg-slate-100 text-slate-500 border-slate-200">
                      {u.role}
                    </span>
                  </td>
                  <td>
                    <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 border border-slate-200">
                      ○ Inactive
                    </span>
                  </td>
                  <td className="text-xs text-slate-400">
                    {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                  </td>
                  <td>
                    <button
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-green-700 border border-green-200 rounded-lg hover:bg-green-50 transition-colors disabled:opacity-40"
                      onClick={() => reactivateMut.mutate(u.id)}
                      disabled={reactivateMut.isPending && pendingReactivateId === u.id}
                    >
                      {reactivateMut.isPending && pendingReactivateId === u.id
                        ? <Loader2 size={12} className="animate-spin" />
                        : <RefreshCw size={12} />}
                      Reactivate
                    </button>
                    <button
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-700 border border-red-200 rounded-lg hover:bg-red-50 transition-colors"
                      onClick={() => setPermanentDeleteUser(u)}
                      title="Permanently delete this user — cannot be undone"
                    >
                      <Trash2 size={12} /> Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </SectionCard>
      )}

      {/* Role legend */}
      <div className="card p-4">
        <h3 className="text-xs font-semibold text-slate-600 mb-3 uppercase tracking-wide">Role Permissions</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {[
            { role: 'Admin', icon: '🛡', color: 'border-primary-200 bg-primary-50', perms: ['Full read + write access', 'Add / edit / delete SDKs', 'Run & manage pipeline', 'Manage users', 'Configure settings'] },
            { role: 'Viewer', icon: '👁', color: 'border-slate-200 bg-slate-50', perms: ['Read-only access', 'View SDKs & recommendations', 'View pipeline runs', 'Cannot modify data'] },
          ].map(({ role, icon, color, perms }) => (
            <div key={role} className={`rounded-xl border p-4 ${color}`}>
              <p className="text-sm font-semibold text-slate-800 mb-2">{icon} {role}</p>
              <ul className="space-y-1">
                {perms.map((p) => (
                  <li key={p} className="text-xs text-slate-600 flex items-center gap-1.5">
                    <span className="text-slate-400">•</span> {p}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      {/* Modals */}
      {showCreate && (
        <CreateUserModal
          onClose={() => setShowCreate(false)}
          onSuccess={() => qc.invalidateQueries({ queryKey: ['users'] })}
        />
      )}
      {editUser && (
        <EditUserModal
          user={editUser}
          onClose={() => setEditUser(null)}
          onSuccess={() => qc.invalidateQueries({ queryKey: ['users'] })}
        />
      )}
      {deleteUser && !isProtected(deleteUser).protected && (
        <DeleteUserModal
          user={deleteUser}
          isPending={deactivateMut.isPending && pendingDeactivateId === deleteUser.id}
          onConfirm={() => deactivateMut.mutate(deleteUser.id)}
          onCancel={() => setDeleteUser(null)}
        />
      )}

      {/* Permanent Delete Confirmation */}
      {permanentDeleteUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
          onClick={() => setPermanentDeleteUser(null)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-6"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                <Trash2 size={18} className="text-red-600" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-slate-800">Delete Permanently</h2>
                <p className="text-xs text-red-500 font-semibold">This cannot be undone</p>
              </div>
            </div>
            <p className="text-sm text-slate-600 mb-2">
              Permanently delete{' '}
              <span className="font-semibold text-slate-800">@{permanentDeleteUser.username}</span>?
            </p>
            <p className="text-xs text-slate-500 mb-5 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
              ⚠️ This will <strong>erase the user record entirely</strong> from the database.
              The username and all login history will be gone. Deactivate is safer if you may need to restore access.
            </p>
            <div className="flex gap-3 justify-end">
              <button className="btn-secondary" onClick={() => setPermanentDeleteUser(null)} disabled={permanentDeleteMut.isPending}>
                Cancel
              </button>
              <button
                className="px-4 py-2 text-sm font-semibold bg-red-700 hover:bg-red-800 text-white rounded-lg transition-colors flex items-center gap-2 disabled:opacity-60"
                onClick={() => permanentDeleteMut.mutate(permanentDeleteUser.id)}
                disabled={permanentDeleteMut.isPending}
              >
                {permanentDeleteMut.isPending
                  ? <><Loader2 size={13} className="animate-spin" /> Deleting…</>
                  : <><Trash2 size={13} /> Delete Permanently</>}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
