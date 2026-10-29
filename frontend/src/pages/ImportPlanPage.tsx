// Plan import: upload an existing floor plan (image or ASCII DXF) and convert
// it to a grid draft. The conversion is verified visually: a fidelity overlay
// draws the original image with the detected walls on top, and threshold /
// density / resolution can be re-tuned until the mapping is faithful.
// Doors, exits, zones, and populations are detected automatically; the editor
// remains available for fine-tuning.

import { useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { api, ApiRequestError, type ImportPreviewResponse } from "../api/client"
import PlanOverlay from "../components/PlanOverlay"
import { DisclaimerBanner, ErrorAlert } from "../components/ui"

const SAMPLE_PLAN_URL = "/sample-plan.png"

export default function ImportPlanPage() {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [fileUrl, setFileUrl] = useState<string | null>(null)
  const [fileName, setFileName] = useState("")
  const [name, setName] = useState("Imported building")
  const [targetWidth, setTargetWidth] = useState(80)
  const [realWidthM, setRealWidthM] = useState(15)
  const [autoThreshold, setAutoThreshold] = useState(true)
  const [threshold, setThreshold] = useState(128)
  const [wallDensity, setWallDensity] = useState(0.3)
  const [invert, setInvert] = useState(false)
  const [result, setResult] = useState<ImportPreviewResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [runningAll, setRunningAll] = useState(false)
  const [isDxf, setIsDxf] = useState(false)
  const [showImageOnly, setShowImageOnly] = useState(false)
  const fileUrlRef = useRef<string | null>(null)

  const draftBuilding = useMemo(() => {
    if (!result) return null
    return {
      id: 0,
      name: result.draft.name,
      description: "Imported plan draft",
      width: result.draft.width,
      height: result.draft.height,
      cell_size_m: result.draft.cell_size_m,
      is_sample: false,
      created_at: "",
      updated_at: "",
      warnings: [],
      walls: result.draft.walls,
      exits: result.draft.exits,
      zones: result.draft.zones,
    }
  }, [result])

  function pickFile(f: File | null) {
    setFile(f)
    setResult(null)
    setError(null)
    if (fileUrlRef.current) URL.revokeObjectURL(fileUrlRef.current)
    if (!f) {
      setFileUrl(null)
      setFileName("")
      return
    }
    const url = URL.createObjectURL(f)
    fileUrlRef.current = url
    setFileUrl(url)
    setFileName(f.name)
    const lower = f.name.toLowerCase()
    setIsDxf(lower.endsWith(".dxf") || lower.endsWith(".drawio") || lower.endsWith(".xml"))
    setName(f.name.replace(/\.[^.]+$/, "") || "Imported building")
  }

  async function convert() {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const preview = await api.previewImportPlan(file, {
        name,
        target_width: targetWidth,
        real_width_m: realWidthM,
        threshold: autoThreshold ? null : threshold,
        invert,
        wall_density: wallDensity,
      })
      setResult(preview)
    } catch (e) {
      setResult(null)
      setError(e instanceof ApiRequestError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function convertAndRun() {
    if (!result) return
    setRunningAll(true)
    setError(null)
    try {
      const building = await api.createBuilding({
        name: result.draft.name,
        description: "Imported from a floor plan with automatic door/exit/zone detection.",
        width: result.draft.width,
        height: result.draft.height,
        cell_size_m: result.draft.cell_size_m,
        walls: result.draft.walls,
        exits: result.draft.exits,
        zones: result.draft.zones,
      })
      let runId: number | null = null
      const suggested = result.suggested_scenario
      if (suggested) {
        const scenario = await api.createScenario({
          building_id: building.id,
          name: suggested.name,
          description: suggested.description,
          config: suggested.config,
        })
        const { run } = await api.createRun({ scenario_id: scenario.id })
        runId = run.id
      }
      navigate(runId ? `/runs/${runId}` : `/buildings/${building.id}`)
    } catch (e) {
      setError(e instanceof ApiRequestError ? e.message : String(e))
      setRunningAll(false)
    }
  }

  function openInEditor() {
    if (!result) return
    const draft = { ...result.draft, importWarnings: result.warnings }
    try {
      sessionStorage.setItem("evacuatesim-import-draft", JSON.stringify(draft))
    } catch {
      // storage unavailable: router state still carries it for this navigation
    }
    navigate("/buildings", { state: { importDraft: draft } })
  }

  async function useSamplePlan() {
    try {
      setBusy(true)
      const resp = await fetch(SAMPLE_PLAN_URL)
      if (!resp.ok) throw new Error("Sample plan not available")
      const blob = await resp.blob()
      pickFile(new File([blob], "sample-plan.png", { type: "image/png" }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const semantics = result?.stats.semantics

  return (
    <div>
      <h1>Import Building Plan</h1>
      <p className="page-sub">
        Upload a prepared floor plan — an image (PNG/JPG/BMP/TIFF) or an ASCII DXF CAD file —
        and EvacuateSim converts it into a simulation automatically: walls, doors, exits (with
        width-based capacities), starting zones with suggested populations, and a ready-to-run
        scenario. The fidelity overlay lets you verify the conversion against your exact image.
      </p>
      <DisclaimerBanner />
      <ErrorAlert message={error} />

      <div className="grid-2" style={{ gridTemplateColumns: "1fr 1.4fr", alignItems: "start" }}>
        <div>
          <div className="card">
            <h3>1. Upload the plan</h3>
            <input
              ref={fileInputRef}
              type="file"
              accept=".png,.jpg,.jpeg,.bmp,.gif,.tif,.tiff,.webp,.dxf,.drawio,.xml"
              onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
            />
            {fileName && <div className="muted">Selected: {fileName}</div>}
            <div className="toolbar" style={{ marginTop: 10 }}>
              <button className="secondary" onClick={useSamplePlan} disabled={busy}>
                Use the bundled sample plan
              </button>
            </div>
            <div className="kbd-note">
              Supported: <strong>draw.io diagrams (.drawio / .xml — most precise)</strong>,
              PNG/JPG/BMP/GIF/TIFF/WebP images, and plain-text (ASCII) DXF. Max 10 MB.
              Binary DXF and PDF are not supported. In draw.io, draw walls as unfilled
              rectangles and lines, leave gaps for doors, and put text labels on their own
              text shapes (labels are ignored).
            </div>
          </div>

          <div className="card">
            <h3>2. Conversion settings</h3>
            <label className="field">
              <span className="lbl">Building name</span>
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <div className="grid-2">
              <label className="field">
                <span className="lbl">Grid width (cells, 8–120)</span>
                <input
                  type="number"
                  min={8}
                  max={120}
                  value={targetWidth}
                  onChange={(e) => setTargetWidth(Number(e.target.value) || 80)}
                />
              </label>
              <label className="field">
                <span className="lbl">Real plan width (metres)</span>
                <input
                  type="number"
                  step={0.5}
                  min={1}
                  value={realWidthM}
                  onChange={(e) => setRealWidthM(Number(e.target.value) || 15)}
                />
              </label>
            </div>
            {!isDxf && (
              <>
                <label className="field" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={autoThreshold}
                    onChange={(e) => setAutoThreshold(e.target.checked)}
                    style={{ width: "auto" }}
                  />
                  Automatic ink threshold (Otsu — recommended; image plans only)
                </label>
                {!autoThreshold && (
                  <label className="field">
                    <span className="lbl">
                      Ink threshold ({threshold}) — darker cutoff keeps only strong lines
                    </span>
                    <input
                      type="range"
                      min={20}
                      max={235}
                      value={threshold}
                      onChange={(e) => setThreshold(Number(e.target.value))}
                    />
                  </label>
                )}
                <label className="field">
                  <span className="lbl">
                    Wall density ({Math.round(wallDensity * 100)}%) — how much ink per cell
                    counts as wall; lower keeps thin lines
                  </span>
                  <input
                    type="range"
                    min={5}
                    max={80}
                    value={Math.round(wallDensity * 100)}
                    onChange={(e) => setWallDensity(Number(e.target.value) / 100)}
                  />
                </label>
                <label className="field" style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={invert}
                    onChange={(e) => setInvert(e.target.checked)}
                    style={{ width: "auto" }}
                  />
                  Invert (plan drawn light-on-dark)
                </label>
              </>
            )}
            <button onClick={convert} disabled={!file || busy}>
              {busy ? "Converting…" : "Convert to simulation grid"}
            </button>
          </div>

          {result && (
            <div className="card">
              <h3>4. Review &amp; continue</h3>
              <div className="toolbar">
                <button onClick={convertAndRun} disabled={runningAll}>
                  {runningAll ? "Creating & simulating…" : "Convert & run evacuation"}
                </button>
                <button className="secondary" onClick={openInEditor}>
                  Review in editor first
                </button>
              </div>
              <div className="kbd-note">
                "Convert &amp; run" creates the building, the auto-generated scenario
                (populations per zone), and starts the evacuation immediately. The editor is
                available if anything needs adjusting.
              </div>
            </div>
          )}
        </div>

        <div>
          <div className="map-wrap">
            {result && draftBuilding && fileUrl && result.stats.crop_box ? (
              <FidelityView
                fileUrl={fileUrl}
                result={result}
                draftBuilding={draftBuilding}
                showImageOnly={showImageOnly}
                setShowImageOnly={setShowImageOnly}
              />
            ) : (
              <div className="empty" style={{ minHeight: 300 }}>
                The converted grid and the fidelity overlay appear here after converting.
              </div>
            )}
          </div>
          {result && (
            <>
              <div className="alert info">
                Auto-detected {semantics?.exits ?? 0} exit(s), {semantics?.zones ?? 0} starting
                zone(s) with suggested populations, and {semantics?.doors ?? 0} door(s).
              </div>
              {result.warnings.length > 0 && (
                <div className="alert error">
                  <strong>Conversion notes:</strong>
                  <ul style={{ margin: "6px 0 0 18px" }}>
                    {result.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function FidelityView({
  fileUrl,
  result,
  draftBuilding,
  showImageOnly,
  setShowImageOnly,
}: {
  fileUrl: string
  result: ImportPreviewResponse
  draftBuilding: {
    width: number
    height: number
    walls: [number, number][]
  }
  showImageOnly: boolean
  setShowImageOnly: (v: boolean) => void
}) {
  const stats = result.stats
  const cellPx = Math.max(6, Math.min(20, Math.floor(760 / draftBuilding.width)))
  return (
    <div>
      <div className="toolbar">
        <div className="seg" role="group" aria-label="Fidelity view mode">
          <button className={!showImageOnly ? "active" : ""} onClick={() => setShowImageOnly(false)}>
            Overlay
          </button>
          <button className={showImageOnly ? "active" : ""} onClick={() => setShowImageOnly(true)}>
            Original
          </button>
        </div>
        {stats.ink_captured_pct != null && (
          <span className="muted">
            Ink captured: <strong>{stats.ink_captured_pct}%</strong>
            {stats.threshold_auto ? " · auto threshold" : ` · threshold ${stats.threshold}`} ·
            density {Math.round((stats.wall_density ?? 0.3) * 100)}%
          </span>
        )}
      </div>
      {stats.ink_captured_pct != null && stats.ink_captured_pct < 60 && !showImageOnly && (
        <div className="alert error">
          Low fidelity: less than 60% of the plan's ink landed inside detected wall cells. Lower
          the wall density or adjust the threshold, then re-convert.
        </div>
      )}
      <PlanOverlay
        imageUrl={fileUrl}
        cropBox={stats.crop_box ?? [0, 0, 1, 1]}
        building={draftBuilding as never}
        cellPx={cellPx}
        imageOnly={showImageOnly}
      />
      {!showImageOnly && (
        <div className="legend">
          <span>
            <span className="swatch" style={{ background: "rgba(225, 29, 72, 0.45)" }} />
            Detected wall cell
          </span>
          <span>Red marks over your image = what the simulation treats as wall.</span>
        </div>
      )}
    </div>
  )
}
