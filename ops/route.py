from typing import List, Dict, Tuple
import math
import hashlib


def dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Calculate Euclidean distance between two points."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


def cost(
    a: Dict, b: Dict, door_penalty: float = 15.0, cage_penalty: float = 25.0
) -> float:
    """Calculate cost between two stops including door and cage penalties."""
    return (
        dist((a["x"], a["y"]), (b["x"], b["y"]))
        + door_penalty * float(b.get("doors", 0))
        + cage_penalty * float(b.get("cage_changes", 0))
    )


def cluster_same_coords(items: List[Dict]) -> List[Dict]:
    """Cluster tickets that share the same coordinates into stops."""
    buckets = {}
    for it in items:
        key = (float(it["x"]), float(it["y"]))
        buckets.setdefault(key, []).append(it)

    stops = []
    for (x, y), arr in buckets.items():
        stops.append({"x": x, "y": y, "tickets": arr})

    return stops


def nn_order(stops: List[Dict], start: Tuple[float, float] = (800, 860)) -> List[int]:
    """Nearest-neighbor heuristic for TSP."""
    un = list(range(len(stops)))
    cur = {"x": start[0], "y": start[1]}
    order = []

    while un:
        j = min(un, key=lambda i: cost(cur, stops[i]))
        order.append(j)
        cur = stops[j]
        un.remove(j)

    return order


def two_opt(
    stops: List[Dict],
    order: List[int],
    start: Tuple[float, float] = (800, 860),
) -> List[int]:
    """2-opt improvement heuristic for TSP."""
    def length(ordr):
        total = 0.0
        cur = {"x": start[0], "y": start[1]}
        for i in ordr:
            total += cost(cur, stops[i])
            cur = stops[i]
        return total

    best = order[:]
    best_len = length(best)
    n = len(best)
    improved = True

    while improved:
        improved = False
        for i in range(n - 2):
            for k in range(i + 2, n):
                cand = best[: i + 1] + list(reversed(best[i + 1 : k + 1])) + best[k + 1 :]
                L = length(cand)
                if L + 1e-6 < best_len:
                    best, best_len, improved = cand, L, True

    return best


def optimize(
    points_raw: List[Dict], start: Tuple[float, float] = (800, 860)
) -> Dict:
    """
    Optimize route using clustering, nearest-neighbor + 2-opt.
    Returns dict with 'sequence' (list of ticket_ids), 'distance' (float), and 'route_id' (str).
    """
    try:
        if not points_raw:
            return {"sequence": [], "distance": 0.0, "route_id": "empty"}

        # Filter out any points with invalid coordinates
        valid_points = []
        for p in points_raw:
            try:
                x, y = float(p.get("x", 0)), float(p.get("y", 0))
                if not (math.isnan(x) or math.isnan(y) or math.isinf(x) or math.isinf(y)):
                    valid_points.append(p)
            except (ValueError, TypeError):
                continue
        
        if not valid_points:
            return {"sequence": [], "distance": 0.0, "route_id": "empty"}

        stops = cluster_same_coords(valid_points)
        
        if not stops:
            return {"sequence": [], "distance": 0.0, "route_id": "empty"}
        
        nn = nn_order(stops, start=start)
        order = two_opt(stops, nn, start=start)

        # Flatten sequence by stop, keep original order within each stop
        total = 0.0
        cur = {"x": start[0], "y": start[1]}
        seq = []

        for idx in order:
            if idx < len(stops):
                s = stops[idx]
                total += cost(cur, s)
                cur = s
                seq.extend([t["ticket_id"] for t in s["tickets"]])

        # Ensure distance is valid
        if math.isnan(total) or math.isinf(total):
            total = 0.0

        rid = hashlib.sha1((";".join(seq) + str(start)).encode()).hexdigest()[:8]

        return {"sequence": seq, "distance": total, "route_id": rid}
    except Exception as e:
        # Return safe default on any error
        import traceback
        print(f"Error in optimize(): {e}")
        print(traceback.format_exc())
        return {"sequence": [], "distance": 0.0, "route_id": "error"}
