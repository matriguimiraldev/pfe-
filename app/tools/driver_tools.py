import csv
import difflib
import math
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.tools.live_tools import get_driver_positions

ROUTES_CSV_PATH = (
    Path(__file__).resolve().parent / "data_sfax" / "sfax_routes_places_seed_v3_comma.csv"
)
DEFAULT_ROUTE_RADIUS_M = float(os.getenv("ROUTE_MATCH_RADIUS_M", "1500"))


def _normalize_text(value: str) -> str:
    cleaned = (value or "").strip().lower()
    cleaned = unicodedata.normalize("NFKD", cleaned)
    cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^a-z0-9\u0600-\u06ff\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _tokenize(value: str) -> List[str]:
    return [tok for tok in _normalize_text(value).split(" ") if tok]


def _parse_wkt_points(raw: str) -> List[Tuple[float, float]]:
    if not raw:
        return []
    text = raw.strip()
    m = re.search(r"\(\s*\(?(.+?)\)?\s*\)$", text)
    if not m:
        m = re.search(r"POINT\s*\((.+)\)", text, flags=re.IGNORECASE)
        if not m:
            return []

    pairs = [part.strip() for part in m.group(1).split(",")]
    points: List[Tuple[float, float]] = []
    for pair in pairs:
        m_pair = re.match(r"([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)$", pair)
        if not m_pair:
            continue
        points.append((float(m_pair.group(1)), float(m_pair.group(2))))
    return points


@lru_cache(maxsize=1)
def load_routes_catalog() -> List[Dict[str, Any]]:
    routes: List[Dict[str, Any]] = []
    if not ROUTES_CSV_PATH.exists():
        return routes

    with ROUTES_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            row["coords"] = _parse_wkt_points(row.get("geometry_wkt", ""))
            row["route_name_fr_norm"] = _normalize_text(row.get("name", ""))
            row["route_id_norm"] = _normalize_text(row.get("id", ""))
            row["ref_hint_norm"] = _normalize_text(row.get("ref_hint", ""))
            aliases = [x.strip() for x in (row.get("aliases", "") or "").split("|") if x.strip()]
            row["aliases_norm"] = [_normalize_text(x) for x in aliases]
            routes.append(row)
    return routes


def find_route_by_query(route_query: str) -> Optional[Dict[str, Any]]:
    query_norm = _normalize_text(route_query)
    if not query_norm:
        return None

    stopwords = {
        "quel", "quels", "quelles", "sont", "les", "dans", "sur", "a", "au", "aux",
        "de", "du", "des", "la", "le", "et", "ce", "cette", "fax", "sfax", "route",
        "livreur", "livreurs", "driver", "drivers", "coursier", "coursiers",
        "spont", "quelle",
    }
    query_tokens = [tok for tok in _tokenize(query_norm) if tok not in stopwords]
    compact_query = " ".join(query_tokens) if query_tokens else query_norm

    routes = load_routes_catalog()
    must_match_ring_road = "ceinture" in query_tokens or "ceinture" in compact_query
    must_match_avenue = "avenue" in query_tokens or "av" in query_tokens

    allowed_categories = {"road", "ring road", "avenue", "district", "landmark"}

    for route in routes:
        category = _normalize_text(route.get("category", ""))
        if category not in allowed_categories:
            continue
        if must_match_ring_road and category != "ring road":
            continue
        if must_match_avenue and category != "avenue":
            continue

        if compact_query in {
            route.get("route_id_norm", ""),
            route.get("route_name_fr_norm", ""),
            route.get("ref_hint_norm", ""),
        }:
            return route
        if compact_query in set(route.get("aliases_norm") or []):
            return route

    candidates: List[Tuple[float, Dict[str, Any]]] = []
    for route in routes:
        category = _normalize_text(route.get("category", ""))
        if category not in allowed_categories:
            continue
        if must_match_ring_road and category != "ring road":
            continue
        if must_match_avenue and category != "avenue":
            continue

        route_name = route.get("route_name_fr_norm", "")
        aliases = route.get("aliases_norm") or []

        if compact_query in route_name:
            return route
        if any(compact_query in alias for alias in aliases):
            return route

        search_terms = [route_name, route.get("route_id_norm", ""), route.get("ref_hint_norm", "")]
        search_terms.extend(aliases)

        best_ratio = 0.0
        for term in search_terms:
            if not term:
                continue

            best_ratio = max(best_ratio, difflib.SequenceMatcher(None, compact_query, term).ratio())

            query_set = set(query_tokens)
            term_set = set(_tokenize(term))
            if query_set and term_set:
                overlap = len(query_set & term_set) / max(1, len(query_set))
                best_ratio = max(best_ratio, overlap)

        candidates.append((best_ratio, route))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_route = candidates[0]
    if best_score >= 0.58:
        return best_route
    return None


def _extract_driver_lat_lng(driver: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    candidates = [
        (driver.get("lat"), driver.get("lng")),
        (driver.get("latitude"), driver.get("longitude")),
        (driver.get("lat"), driver.get("lon")),
        (driver.get("lat"), driver.get("long")),
    ]
    position = driver.get("position")
    if isinstance(position, dict):
        candidates.extend(
            [
                (position.get("lat"), position.get("lng")),
                (position.get("latitude"), position.get("longitude")),
                (position.get("lat"), position.get("lon")),
                (position.get("lat"), position.get("long")),
            ]
        )

    for lat, lng in candidates:
        try:
            if lat is not None and lng is not None:
                return float(lat), float(lng)
        except (TypeError, ValueError):
            continue
    return None


def _distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _point_to_segment_distance_m(
    p_lat: float,
    p_lng: float,
    a_lat: float,
    a_lng: float,
    b_lat: float,
    b_lng: float,
) -> float:
    lat0 = math.radians(p_lat)
    m_per_deg_lat = 111320.0
    m_per_deg_lng = 111320.0 * math.cos(lat0)

    px, py = 0.0, 0.0
    ax = (a_lng - p_lng) * m_per_deg_lng
    ay = (a_lat - p_lat) * m_per_deg_lat
    bx = (b_lng - p_lng) * m_per_deg_lng
    by = (b_lat - p_lat) * m_per_deg_lat

    abx = bx - ax
    aby = by - ay
    ab2 = abx * abx + aby * aby
    if ab2 == 0:
        return math.hypot(ax - px, ay - py)

    apx = px - ax
    apy = py - ay
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab2))
    cx = ax + t * abx
    cy = ay + t * aby
    return math.hypot(cx - px, cy - py)


def _distance_to_route_m(
    driver_lat: float, driver_lng: float, route_lonlat_points: List[Tuple[float, float]]
) -> float:
    if not route_lonlat_points:
        return float("inf")
    if len(route_lonlat_points) == 1:
        point_lon, point_lat = route_lonlat_points[0]
        return _distance_m(driver_lat, driver_lng, point_lat, point_lon)

    distances: List[float] = []
    for i in range(len(route_lonlat_points) - 1):
        a_lon, a_lat = route_lonlat_points[i]
        b_lon, b_lat = route_lonlat_points[i + 1]
        distances.append(
            _point_to_segment_distance_m(
                p_lat=driver_lat,
                p_lng=driver_lng,
                a_lat=a_lat,
                a_lng=a_lon,
                b_lat=b_lat,
                b_lng=b_lon,
            )
        )
    return min(distances) if distances else float("inf")


def get_drivers_on_route(route_query: str, max_distance_m: Optional[float] = None) -> Dict[str, Any]:
    radius_m = float(max_distance_m) if max_distance_m is not None else DEFAULT_ROUTE_RADIUS_M
    route = find_route_by_query(route_query)
    if not route:
        return {"route_found": False, "route_query": route_query, "drivers": []}

    coords = route.get("coords") or []
    matched: List[Dict[str, Any]] = []
    for driver in get_driver_positions(zone_id=1):
        lat_lng = _extract_driver_lat_lng(driver)
        if not lat_lng:
            continue
        lat, lng = lat_lng
        distance = _distance_to_route_m(lat, lng, coords)
        if distance <= radius_m:
            row = dict(driver)
            row["distance_to_route_m"] = round(distance, 1)
            matched.append(row)

    matched.sort(key=lambda item: item.get("distance_to_route_m", float("inf")))
    return {
        "route_found": True,
        "route_query": route_query,
        "route_id": route.get("id"),
        "route_name_fr": route.get("name"),
        "ref_hint": route.get("ref_hint"),
        "max_distance_m": radius_m,
        "drivers_count": len(matched),
        "drivers": matched[:50],
    }


def get_nearest_driver_on_route(route_query: str) -> Dict[str, Any]:
    route = find_route_by_query(route_query)
    if not route:
        return {"route_found": False, "route_query": route_query, "nearest_driver": None}

    coords = route.get("coords") or []
    nearest_driver: Optional[Dict[str, Any]] = None
    nearest_distance = float("inf")

    for driver in get_driver_positions(zone_id=1):
        lat_lng = _extract_driver_lat_lng(driver)
        if not lat_lng:
            continue
        lat, lng = lat_lng
        distance = _distance_to_route_m(lat, lng, coords)
        if distance < nearest_distance:
            nearest_distance = distance
            nearest_driver = dict(driver)
            nearest_driver["distance_to_route_m"] = round(distance, 1)

    return {
        "route_found": True,
        "route_query": route_query,
        "route_id": route.get("id"),
        "route_name_fr": route.get("name"),
        "nearest_driver": nearest_driver,
    }


def find_nearest_route_for_driver(
    driver: Dict[str, Any], max_distance_m: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """Return nearest catalog route for a driver position if distance is within threshold."""
    lat_lng = _extract_driver_lat_lng(driver)
    if not lat_lng:
        return None

    lat, lng = lat_lng
    nearest_route: Optional[Dict[str, Any]] = None
    nearest_distance = float("inf")
    for route in load_routes_catalog():
        coords = route.get("coords") or []
        if not coords:
            continue
        distance = _distance_to_route_m(lat, lng, coords)
        if distance < nearest_distance:
            nearest_distance = distance
            nearest_route = route

    if not nearest_route:
        return None

    threshold = float(max_distance_m) if max_distance_m is not None else DEFAULT_ROUTE_RADIUS_M
    if nearest_distance > threshold:
        return None

    return {
        "route_id": nearest_route.get("id"),
        "route_name_fr": nearest_route.get("name"),
        "distance_to_route_m": round(nearest_distance, 1),
    }


def get_drivers_with_nearest_routes(
    max_distance_m: Optional[float] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """Attach nearest known route to each online driver when available."""
    rows: List[Dict[str, Any]] = []
    for driver in get_driver_positions(zone_id=1):
        item = dict(driver)
        nearest = find_nearest_route_for_driver(item, max_distance_m=max_distance_m)
        if nearest:
            item.update(nearest)
            item["route_found"] = True
        else:
            item["route_found"] = False
        rows.append(item)

    rows.sort(
        key=lambda d: (
            not d.get("route_found", False),
            d.get("distance_to_route_m", float("inf")),
        )
    )

    with_route = [r for r in rows if r.get("route_found")]
    without_route = [r for r in rows if not r.get("route_found")]
    return {
        "drivers_count": len(rows),
        "drivers_with_route": len(with_route),
        "drivers_without_route": len(without_route),
        "items": rows[: max(1, limit)],
    }
