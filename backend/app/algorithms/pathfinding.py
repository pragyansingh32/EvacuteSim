"""Pathfinding on the evacuation grid.

The engine uses precomputed BFS distance fields: one multi-source field from all
reachable exits (for nearest-exit decisions) and one single-source field per exit
(for strategies that route to a specific exit). BFS is appropriate because the
grid is unweighted and movement is four-directional; diagonal movement through
wall corners is deliberately not allowed.
"""

from __future__ import annotations

from collections import deque

# Fixed neighbor order (N, E, S, W) so tie-breaking between equal-cost
# neighbors is deterministic everywhere.
NEIGHBOR_OFFSETS: tuple[tuple[int, int], ...] = ((0, -1), (1, 0), (0, 1), (-1, 0))


def bfs_distance_field(
    width: int,
    height: int,
    walkable: set[tuple[int, int]],
    sources: set[tuple[int, int]],
) -> dict[tuple[int, int], int]:
    """Return {cell: step_distance} from the nearest source over 4-connected cells.

    Only cells in `walkable` are traversed; sources must be walkable.
    """
    if not sources:
        return {}
    dist: dict[tuple[int, int], int] = {}
    queue: deque[tuple[int, int]] = deque()
    for src in sources:
        if src in walkable and src not in dist:
            dist[src] = 0
            queue.append(src)
    while queue:
        x, y = queue.popleft()
        d = dist[(x, y)]
        for dx, dy in NEIGHBOR_OFFSETS:
            nxt = (x + dx, y + dy)
            if nxt in walkable and nxt not in dist:
                dist[nxt] = d + 1
                queue.append(nxt)
    return dist
