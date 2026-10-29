"""BFS distance field tests."""

from app.algorithms.pathfinding import bfs_distance_field


def test_single_source_distances():
    # 3x3 open grid, source at (0,0).
    walkable = {(x, y) for x in range(3) for y in range(3)}
    dist = bfs_distance_field(3, 3, walkable, {(0, 0)})
    assert dist[(0, 0)] == 0
    assert dist[(2, 2)] == 4  # manhattan distance
    assert dist[(1, 0)] == 1
    assert dist[(0, 1)] == 1


def test_walls_block_paths():
    # Wall in the middle forces a detour.
    #   S . #
    #   . . #
    #   . . G
    walkable = {(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (2, 2)}
    dist = bfs_distance_field(3, 3, walkable, {(0, 0)})
    assert (2, 2) in dist
    assert dist[(2, 2)] == 4  # down, right, right (around the wall)
    assert (2, 0) not in dist and (2, 1) not in dist  # behind the wall


def test_unreachable_cells_absent():
    walkable = {(0, 0), (0, 1), (2, 2)}
    dist = bfs_distance_field(3, 3, walkable, {(0, 0)})
    assert (2, 2) not in dist


def test_no_sources_returns_empty():
    dist = bfs_distance_field(3, 3, {(0, 0)}, set())
    assert dist == {}
