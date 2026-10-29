"""Individual occupant state."""

from __future__ import annotations

from dataclasses import dataclass

# Occupant lifecycle states.
STATUS_WAITING = "waiting"      # pre-movement delay not yet elapsed
STATUS_MOVING = "moving"        # actively walking
STATUS_AT_EXIT = "at_exit"      # standing on an exit cell, waiting to discharge
STATUS_EVACUATED = "evacuated"  # successfully left the building
STATUS_UNREACHABLE = "unreachable"  # no path to any exit existed at spawn

STATUS_CODES = {
    STATUS_WAITING: 0,
    STATUS_MOVING: 1,
    STATUS_AT_EXIT: 2,
    STATUS_EVACUATED: 3,
    STATUS_UNREACHABLE: 4,
}

# Statuses of occupants still inside the building at any point in time.
INSIDE_STATUSES = frozenset({STATUS_WAITING, STATUS_MOVING, STATUS_AT_EXIT})

# Terminal statuses: the mass balance is
# total == evacuated + unreachable + (waiting + moving + at_exit).
TERMINAL_STATUSES = frozenset({STATUS_EVACUATED, STATUS_UNREACHABLE})


@dataclass
class Occupant:
    """One simulated person.

    Movement model: an occupant may advance one cell when its movement
    accumulator has collected at least `cell_size / speed` seconds of
    eligible time. Eligible time only accrues once the reaction delay
    has elapsed, which is how walking speed and pre-movement delay both
    influence movement timing.
    """

    id: int
    x: int
    y: int
    speed_mps: float
    reaction_delay_s: float
    priority: float  # seeded tie-break for movement conflicts
    status: str = STATUS_WAITING
    reacted: bool = False  # pre-movement delay elapsed (door discharge requires this)
    move_accumulator_s: float = 0.0
    assigned_exit: str | None = None
    exit_id: str | None = None          # exit cell the occupant is standing on
    exit_entered_t: float | None = None  # FIFO order for door queues
    queue_time_s: float = 0.0           # seconds spent blocked while ready to move
    moves: int = 0
    evacuated_t: float | None = None
    fallback_used: bool = False  # strategy had to reroute (recorded for explainability)

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)
