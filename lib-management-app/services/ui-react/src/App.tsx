import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Libraries from './pages/Libraries'
import Governance from './pages/Governance'
import Scheduler from './pages/Scheduler'
import Analytics from './pages/Analytics'
import Settings from './pages/Settings'
import Users from './pages/Users'
import Audit from './pages/Audit'
import NotificationReliability from './pages/NotificationReliability'
import WeeklyDigest from './pages/WeeklyDigest'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { token } = useAuth()
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useAuth()
  return isAdmin ? <>{children}</> : <Navigate to="/dashboard" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="libraries" element={<Libraries />} />
        <Route path="governance" element={<Governance />} />
        <Route path="hitl-review" element={<Navigate to="/libraries" replace />} />
        <Route path="scheduler" element={<Scheduler />} />
        <Route path="notification-reliability" element={<NotificationReliability />} />
        <Route path="notification-configuration" element={<Navigate to="/settings?category=businessComms" replace />} />
        <Route path="business-communication-controls" element={<Navigate to="/settings?category=businessComms" replace />} />
        <Route path="settings/business-communication-controls" element={<Navigate to="/settings?category=businessComms" replace />} />
        <Route path="weekly-digest" element={<WeeklyDigest />} />
        <Route path="audit" element={<Audit />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="settings"  element={<RequireAdmin><Settings /></RequireAdmin>} />
        <Route path="users"     element={<RequireAdmin><Users /></RequireAdmin>} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
