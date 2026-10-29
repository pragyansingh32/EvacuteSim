# Troubleshooting

## Installation

**`ImportError: DLL load failed while importing _pydantic_core: An Application Control policy has blocked this file.`**
Windows Smart App Control blocked the wheel by cloud reputation. Pin the known-good version:
`pip install "pydantic==2.12.5"`. Do not disable the policy. (See KNOWN_LIMITATIONS §15.)

**`pip install` fails on Python 3.8/3.9** — the project targets Python ≥ 3.12 (tested on 3.14).
Install a newer interpreter and recreate the venv.

**`npm install` is slow or fails** — delete `frontend/node_modules` and retry; ensure Node ≥ 20.

## Running

**Port 8000 already in use** — stop the other process or run
`uvicorn app.main:app --port 8001`; if you change the port, also set the Vite proxy target in
`frontend/vite.config.ts` (dev mode).

**Frontend loads but shows "Network error"/empty data** — the backend is not reachable. In dev
mode the Vite proxy targets `http://127.0.0.1:8000`; make sure uvicorn is running. Check
`http://127.0.0.1:8000/api/v1/health`.

**No buildings/scenarios appear** — sample seeding runs at backend startup. If the DB file
(`backend/data/evacuatesim.db`) exists but is empty or broken, stop the server and delete the
file; it will be recreated on next start (all user data in it is lost — export runs first).

**SQLite "database is locked"** — the 2-worker run pool + API writes rarely conflict (WAL mode);
if you see it, avoid running two backends against the same DB file.

## Simulation

**"Time step X s is too large for a 0.5 m cell and Y m/s maximum speed"** — the step must resolve
the fastest walker: `dt ≤ cell_size / max_speed`. Lower `dt_s` (default 0.25) or reduce max speed.

**"Zone 'Z' has no walkable cells in this scenario"** — the scenario's blocked cells or a blocked
exit cover the whole zone. Unblock something.

**"All exits are blocked" / "Cannot block every exit"** — at least one reachable exit must remain.

**Run status `failed`** — open the run detail: the error message states the cause (e.g. a broken
layout). Failed runs are recorded honestly and never fabricate results; fix the configuration
and start a new run.

**Run status shows `incomplete` engine outcome with occupants remaining** — the time horizon was
reached before everyone got out. Increase `max_duration_s`, or treat it as a finding (that many
people would still be inside).

**All occupants `unreachable`** — no exit is path-connected to the zones. Use the editor's
validation warnings (unreachable cells, isolated exits) to locate the break.

## Frontend

**Blank page after `npm run build`** — hard-refresh (Ctrl+F5); the SPA fallback serves
`index.html` for client-side routes.

**Playback frame count seems low** — frames are recorded at `frame_interval_s` (default 1 s) and
capped at 4000 per run; the engine raises the interval automatically for very long runs.

**Charts show no data for a run** — only completed runs carry timeline/frames; failed or pending
runs intentionally show status only.
