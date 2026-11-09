# Troubleshooting

**Port 8000 is in use.** Start uvicorn on another port and update the proxy
target in `frontend/vite.config.ts` for dev mode.

**The frontend shows a network error or no data.** The backend is not
reachable. Check http://127.0.0.1:8000/api/v1/health.

**No buildings or scenarios appear.** Samples are seeded at startup. If
`backend/data/evacuatesim.db` is broken, stop the server and delete it. It is
recreated on the next start, and everything stored in it is lost.

**"database is locked".** Don't run two backends against the same database file.

**"Time step X s is too large for a 0.5 m cell and Y m/s maximum speed".** The
step must satisfy `dt <= cell_size / max_speed`. Lower `dt_s` or the maximum speed.

**"Zone has no walkable cells in this scenario".** Blocked cells or blocked
exits cover the whole zone.

**"All exits are blocked".** At least one reachable exit must remain open.

**A run has status `failed`.** The run detail shows the error. Fix the
configuration and start a new run.

**Occupants remain after the run ends.** The time limit was reached. Raise
`max_duration_s`, or treat it as a result.

**Every occupant is `unreachable`.** No exit is connected to the zones. The
editor's validation warnings point at the break.

**Blank page after `npm run build`.** Hard-refresh. The backend serves
`index.html` for client-side routes.

**Playback has few frames.** Frames are recorded every `frame_interval_s`
(default 1 s) and capped at 4000 per run.
