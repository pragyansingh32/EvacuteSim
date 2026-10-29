"""Central application settings with hard computation limits.

All limits exist so that an accidentally enormous scenario cannot exhaust
local resources. They are deliberately conservative for a local research tool.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_prefix="EVACUATESIM_",
        extra="ignore",
    )

    app_name: str = "EvacuateSim API"
    api_version: str = "v1"

    # --- storage ---
    database_url: str = f"sqlite:///{BACKEND_ROOT / 'data' / 'evacuatesim.db'}"

    # --- CORS: local frontend origin (development) ---
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # --- hard input limits ---
    max_grid_width: int = 120
    max_grid_height: int = 120
    min_grid_size: int = 4
    max_occupants: int = 2000
    max_sim_duration_s: float = 3600.0
    max_blocked_cells: int = 2000
    max_exits: int = 20
    max_zones: int = 30

    # --- engine defaults ---
    default_dt_s: float = 0.25
    default_cell_size_m: float = 0.5
    default_frame_interval_s: float = 1.0
    max_total_steps: int = 40_000  # hard cap on simulated steps per run

    # --- run execution ---
    run_workers: int = 2
    max_frames_per_run: int = 4000

    # --- experiments ---
    max_experiment_runs: int = 200


settings = Settings()


def ensure_data_dir() -> Path:
    """Create the data directory (SQLite parent) if missing."""
    data_dir = BACKEND_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
