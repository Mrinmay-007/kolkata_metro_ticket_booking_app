
import heapq
from app.db.sqlite_client import get_sqlite_conn


def _load_graph(conn):
    """
    Builds an adjacency list for the metro graph from the SQLite database.

    Each node is a station row id (a station is unique per (name, line)).
    Edges come from two sources:
      - `connections`: travel between adjacent stations on the same line
        (weighted by travel_time_minutes, tagged as a "ride" edge).
      - `interchanges`: walking transfer between the same physical station
        on different lines (weighted by transfer_time_minutes, tagged as
        a "walk" edge).
    """
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, line FROM stations;")
    stations = {row["id"]: {"name": row["name"], "line": row["line"]} for row in cursor.fetchall()}

    graph = {station_id: [] for station_id in stations}

    cursor.execute("SELECT station_a_id, station_b_id, travel_time_minutes, fare_inr FROM connections;")
    for row in cursor.fetchall():
        a, b = row["station_a_id"], row["station_b_id"]
        if a in graph and b in graph:
            graph[a].append({
                "to": b,
                "weight": row["travel_time_minutes"],
                "fare": row["fare_inr"],
                "type": "ride",
            })

    cursor.execute("SELECT station_from_id, station_to_id, transfer_time_minutes FROM interchanges;")
    for row in cursor.fetchall():
        a, b = row["station_from_id"], row["station_to_id"]
        if a in graph and b in graph:
            graph[a].append({
                "to": b,
                "weight": row["transfer_time_minutes"],
                "fare": 0,
                "type": "walk",
            })

    return stations, graph


def _find_station_ids(stations, name):
    """Returns all station node ids that match a given station name (case-insensitive)."""
    name_normalized = name.strip().lower()
    return [sid for sid, info in stations.items() if info["name"].strip().lower() == name_normalized]


def _dijkstra(graph, sources):
    """
    Runs Dijkstra's algorithm from a set of candidate source nodes
    (a station name can map to multiple nodes, one per line).
    Returns dist and prev_edge maps rooted at a single virtual start.
    """
    dist = {node: float("inf") for node in graph}
    prev = {node: None for node in graph}  

    pq = []
    for s in sources:
        dist[s] = 0
        heapq.heappush(pq, (0, s))

    visited = set()

    while pq:
        current_dist, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)

        for edge in graph[u]:
            v = edge["to"]
            new_dist = current_dist + edge["weight"]
            if new_dist < dist[v]:
                dist[v] = new_dist
                prev[v] = (u, edge) #type: ignore
                heapq.heappush(pq, (new_dist, v))

    return dist, prev


def _reconstruct_path(prev, dist, target):
    path_nodes = [target]
    edges = []
    node = target
    while prev[node] is not None:
        prev_node, edge = prev[node]
        edges.append(edge)
        node = prev_node
        path_nodes.append(node)

    path_nodes.reverse()
    edges.reverse()
    return path_nodes, edges


def get_metro_route(source_name: str, destination_name: str):
    """
    Computes the shortest route (based on travel time) between the source and
    destination metro stations using Dijkstra's algorithm.
    Reads station, connection, and interchange graphs dynamically from SQLite.
    """
    if not source_name or not source_name.strip():
        raise ValueError("Source station name must be provided.")
    if not destination_name or not destination_name.strip():
        raise ValueError("Destination station name must be provided.")

    with get_sqlite_conn() as conn:
        stations, graph = _load_graph(conn)

    source_ids = _find_station_ids(stations, source_name)
    destination_ids = _find_station_ids(stations, destination_name)

    if not source_ids:
        raise ValueError(f"Source station '{source_name}' was not found in the metro network.")
    if not destination_ids:
        raise ValueError(f"Destination station '{destination_name}' was not found in the metro network.")

    if set(source_ids) & set(destination_ids):
        # Same station name given for both source and destination
        sid = source_ids[0]
        return {
            "route_summary": {
                "source": stations[sid]["name"],
                "destination": stations[sid]["name"],
                "total_fare_inr": 0,
                "total_travel_time_minutes": 0,
                "interchanges_count": 0,
            },
            "ordered_itinerary": [
                {
                    "station_name": stations[sid]["name"],
                    "line": stations[sid]["line"],
                    "is_interchange": False,
                    "transfer_to": None,
                }
            ],
        }

    dist, prev = _dijkstra(graph, source_ids)

    # Pick the reachable destination node (across lines) with the minimum distance
    best_target = min(
        (d for d in destination_ids if dist[d] != float("inf")),
        key=lambda d: dist[d],
        default=None,
    )

    if best_target is None:
        raise ValueError(
            f"No route could be found between '{source_name}' and '{destination_name}'."
        )

    path_nodes, edges = _reconstruct_path(prev, dist, best_target)

    total_fare = sum(edge["fare"] for edge in edges)
    total_time = dist[best_target]
    interchanges_count = sum(1 for edge in edges if edge["type"] == "walk")

    # Build the itinerary: one entry per station in the path. A station is
    # flagged as an interchange point when the edge leaving it is a "walk"
    # (line-transfer) edge rather than a "ride" edge.
    ordered_itinerary = []
    for i, node in enumerate(path_nodes):
        station = stations[node]
        is_interchange = i < len(edges) and edges[i]["type"] == "walk"
        transfer_to = stations[path_nodes[i + 1]]["line"] if is_interchange else None
        ordered_itinerary.append({
            "station_name": station["name"],
            "line": station["line"],
            "is_interchange": is_interchange,
            "transfer_to": transfer_to,
        })

    return {
        "route_summary": {
            "source": stations[path_nodes[0]]["name"],
            "destination": stations[path_nodes[-1]]["name"],
            "total_fare_inr": total_fare,
            "total_travel_time_minutes": total_time,
            "interchanges_count": interchanges_count,
        },
        "ordered_itinerary": ordered_itinerary,
    }


