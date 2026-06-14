import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import OperatorPage from './pages/OperatorPage'
import SupervisorPage from './pages/SupervisorPage'
import CaseDetailPage from './pages/CaseDetailPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/operator" replace />} />
          <Route path="operator" element={<OperatorPage />} />
          <Route path="operator/cases/:caseId" element={<CaseDetailPage />} />
          <Route path="supervisor" element={<SupervisorPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
