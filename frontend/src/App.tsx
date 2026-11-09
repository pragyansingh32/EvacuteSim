import { NavLink, Route, Routes } from 'react-router-dom'
import AccuracyPage from './pages/AccuracyPage'
import AdvisorPage from './pages/AdvisorPage'
import RestorePointsPage from './pages/RestorePointsPage'
import BuildingEditorPage from './pages/BuildingEditorPage'
import ComparePage from './pages/ComparePage'
import DisasterReadinessPage from './pages/DisasterReadinessPage'
import MethodologyPage from './pages/MethodologyPage'
import ExperimentsPage from './pages/ExperimentsPage'
import HomePage from './pages/HomePage'
import ImportPlanPage from './pages/ImportPlanPage'
import RunViewPage from './pages/RunViewPage'
import RunsPage from './pages/RunsPage'
import ScenarioEditorPage from './pages/ScenarioEditorPage'
import ScenarioLibraryPage from './pages/ScenarioLibraryPage'
import { useTheme } from './theme'

export default function App() {
  const { isDark, toggle } = useTheme()
  return (
    <div className="app-shell">
      <nav className="sidebar">
        <div className="brand">
          <span className="mark">⏱</span>
          <span>
            Evacuate<span className="word">Sim</span>
          </span>
        </div>
        <div className="section-label">Workspace</div>
        <NavLink to="/" end>
          Home
        </NavLink>
        <NavLink to="/buildings">Buildings &amp; Editor</NavLink>
        <NavLink to="/import">Import Plan</NavLink>
        <NavLink to="/scenarios">Scenario Editor</NavLink>
        <NavLink to="/library">Scenario Library</NavLink>
        <div className="section-label">Analysis</div>
        <NavLink to="/runs">Runs</NavLink>
        <NavLink to="/compare">Compare</NavLink>
        <NavLink to="/disaster-readiness">Disaster Readiness</NavLink>
        <NavLink to="/experiments">Experiments</NavLink>
        <NavLink to="/advisor">Advisor</NavLink>
        <NavLink to="/accuracy">System Accuracy</NavLink>
        <NavLink to="/methodology">Methodology</NavLink>
        <div className="section-label">System</div>
        <NavLink to="/restore-points">Restore Points</NavLink>
        <div className="footnote">
          Educational/research simulation. Outcomes depend on model assumptions and are not
          certified safety predictions.
        </div>
        <button className="theme-toggle" onClick={toggle} title="Toggle light/dark theme">
          {isDark ? '☀ Light mode' : '☾ Dark mode'}
        </button>
      </nav>
      <main className="main">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/buildings" element={<BuildingEditorPage />} />
          <Route path="/buildings/:id" element={<BuildingEditorPage />} />
          <Route path="/import" element={<ImportPlanPage />} />
          <Route path="/scenarios" element={<ScenarioEditorPage />} />
          <Route path="/scenarios/:id" element={<ScenarioEditorPage />} />
          <Route path="/library" element={<ScenarioLibraryPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/runs/:id" element={<RunViewPage />} />
          <Route path="/compare" element={<ComparePage />} />
          <Route path="/disaster-readiness" element={<DisasterReadinessPage />} />
          <Route path="/experiments" element={<ExperimentsPage />} />
          <Route path="/accuracy" element={<AccuracyPage />} />
          <Route path="/methodology" element={<MethodologyPage />} />
          <Route path="/advisor" element={<AdvisorPage />} />
          <Route path="/restore-points" element={<RestorePointsPage />} />
        </Routes>
      </main>
    </div>
  )
}
