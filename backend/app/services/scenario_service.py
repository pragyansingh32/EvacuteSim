"""Scenario service: validation against the building and CRUD."""

from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.models import ScenarioModel
from app.repositories import buildings as building_repo
from app.repositories import scenarios as scenario_repo
from app.simulation.grid import BuildingGrid


def _validate_config_against_building(grid: BuildingGrid, config: dict) -> None:
    """Reject scenario configs that reference unknown zones/exits or bad cells."""
    unknown_zones = set(config["zone_populations"]) - set(grid.zones)
    if unknown_zones:
        raise ValidationError(f"Scenario references unknown zone(s): {sorted(unknown_zones)}.")
    if not any(v > 0 for v in config["zone_populations"].values()):
        raise ValidationError("At least one zone must have a positive population.")

    known_exits = set(grid.exits)
    blocked = set(config["blocked_exit_ids"])
    unknown_exits = blocked - known_exits
    if unknown_exits:
        raise ValidationError(f"Scenario blocks unknown exit(s): {sorted(unknown_exits)}.")
    if blocked >= known_exits:
        raise ValidationError("Cannot block every exit of the building.")

    for exit_id in config["exit_capacity_overrides"]:
        if exit_id not in known_exits:
            raise ValidationError(f"Capacity override references unknown exit '{exit_id}'.")

    for x, y in config["blocked_cells"]:
        if not grid.in_bounds(x, y):
            raise ValidationError(f"Blocked cell ({x}, {y}) is outside the grid bounds.")

    disaster = config.get("disaster") or {}
    ox, oy = disaster.get("origin_x"), disaster.get("origin_y")
    if (ox is None) != (oy is None):
        raise ValidationError(
            "Disaster origin needs both origin_x and origin_y (or neither for auto)."
        )
    if ox is not None and not grid.in_bounds(int(ox), int(oy)):
        raise ValidationError(
            f"Disaster origin ({ox}, {oy}) is outside the grid bounds."
        )

    speed = config["speed_distribution"]
    max_dt = grid.cell_size_m / speed["max"]
    if config["dt_s"] > max_dt + 1e-9:
        raise ValidationError(
            f"Time step {config['dt_s']}s is too large for a {grid.cell_size_m}m cell and "
            f"{speed['max']}m/s maximum speed; use dt <= {max_dt:.3f}s."
        )


def config_to_dict(schema) -> dict:  # noqa: ANN001
    """Pydantic ScenarioConfigSchema (or already-plain dict) -> engine-ready dict."""
    cfg = schema.model_dump() if hasattr(schema, "model_dump") else dict(schema)
    cfg["speed_distribution"] = cfg.pop("speed")
    cfg["pre_movement_distribution"] = cfg.pop("pre_movement")
    disaster = dict(cfg.get("disaster") or {})
    if disaster.get("type", "none") != "none":
        ox, oy = disaster.pop("origin_x", None), disaster.pop("origin_y", None)
        disaster["origin"] = [int(ox), int(oy)] if ox is not None and oy is not None else None
    else:
        disaster = {"type": "none", "intensity": 0.0, "origin": None}
    cfg["disaster"] = disaster
    return cfg


def create_scenario(db: Session, payload: dict) -> ScenarioModel:
    building = building_repo.get_building(db, payload["building_id"])
    grid = BuildingGrid.from_dict(building.to_grid_dict())
    config = config_to_dict(payload["config"])
    _validate_config_against_building(grid, config)
    return scenario_repo.create_scenario(
        db,
        building_id=building.id,
        name=payload["name"],
        description=payload.get("description", ""),
        config=config,
    )


def update_scenario(db: Session, scenario_id: int, payload: dict) -> ScenarioModel:
    scenario = scenario_repo.get_scenario(db, scenario_id)
    building = building_repo.get_building(db, scenario.building_id)
    grid = BuildingGrid.from_dict(building.to_grid_dict())
    config = config_to_dict(payload["config"]) if payload.get("config") else None
    if config is not None:
        _validate_config_against_building(grid, config)
    return scenario_repo.update_scenario(
        db, scenario, payload.get("name"), payload.get("description"), config
    )
