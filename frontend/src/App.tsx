import { NavLink, Route, Routes } from 'react-router-dom'
import BuildingEditorPage from './pages/BuildingEditorPage'
import ComparePage from './pages/ComparePage'
import ExperimentsPage from './pages/ExperimentsPage'
import HomePage from './pages/HomePage'
import ImportPlanPage from './pages/ImportPlanPage'
import RunViewPage from './pages/RunViewPage'
import RunsPage from './pages/RunsPage'
import ScenarioEditorPage from './pages/ScenarioEditorPage'
import ScenarioLibraryPage from './pages/ScenarioLibraryPage'

export default function App() {
  return (
    <div className="app-shell">
      <nav className="sidebar">
        <div className="brand">
          Evacuate<span>Sim</span>
        </div>
        <NavLink to="/" end>
          Home
        </NavLink>
        <NavLink to="/buildings">Buildings &amp; Editor</NavLink>
        <NavLink to="/import">Import Plan</NavLink>
        <NavLink to="/scenarios">Scenario Editor</NavLink>
        <NavLink to="/library">Scenario Library</NavLink>
        <NavLink to="/runs">Runs</NavLink>
        <NavLink to="/compare">Compare</NavLink>
        <NavLink to="/experiments">Experiments</NavLink>
        <div className="footnote">
          Educational/research simulation. Outcomes depend on model assumptions and are not
          certified safety predictions.
        </div>
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
          <Route path="/experiments" element={<ExperimentsPage />} />
        </Routes>
      </main>
    </div>
  )
}
