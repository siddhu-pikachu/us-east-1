from typing import List, Dict, Tuple
import math


def dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Calculate Euclidean distance between two points."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def nearest_neighbor(
    points: List[Dict], start: Tuple[float, float] = (800, 860)
) -> List[int]:
    """
    Nearest-neighbor heuristic for TSP.
    Returns list of indices in visit order.
    """
    unvisited = list(range(len(points)))
    order, cur = [], start

    while unvisited:
        i_min = min(
            unvisited, key=lambda i: dist(cur, (points[i]["x"], points[i]["y"]))
        )
        order.append(i_min)
        cur = (points[i_min]["x"], points[i_min]["y"])
        unvisited.remove(i_min)

    return order


def two_opt(
    points: List[Dict],
    order: List[int],
    start: Tuple[float, float] = (800, 860),
) -> List[int]:
    """
    2-opt improvement heuristic for TSP.
    Returns improved order.
    """
    improved = True

    def route_len(ordr):
        total, cur = 0.0, start
        for i in ordr:
            nxt = (points[i]["x"], points[i]["y"])
            total += dist(cur, nxt)
            cur = nxt
        return total

    best = order[:]
    best_len = route_len(best)
    n = len(order)

    while improved:
        improved = False
        for i in range(n - 2):
            for j in range(i + 2, n):
                cand = best[: i + 1] + list(reversed(best[i + 1 : j + 1])) + best[j + 1 :]
                L = route_len(cand)
                if L + 1e-6 < best_len:
                    best, best_len, improved = cand, L, True

    return best


def optimize(
    points: List[Dict], start: Tuple[float, float] = (800, 860)
) -> Dict:
    """
    Optimize route using nearest-neighbor + 2-opt.
    Returns dict with 'order' (list of indices) and 'distance' (float).
    """
    if not points:
        return {"order": [], "distance": 0.0}

    nn = nearest_neighbor(points, start=start)
    opt = two_opt(points, nn, start=start)

    # compute length
    cur, total = start, 0.0
    for i in opt:
        nxt = (points[i]["x"], points[i]["y"])
        total += dist(cur, nxt)
        cur = nxt

    return {"order": opt, "distance": total}

