from typing import Any, Dict

from app.tools.driver_tools import get_drivers_with_nearest_routes


def get_drivers_routes_map(max_distance_m: float = 1500.0, limit: int = 50) -> Dict[str, Any]:
	"""Return map-oriented payload: each online driver with nearest known route when found."""
	data = get_drivers_with_nearest_routes(max_distance_m=max_distance_m, limit=limit)
	return {
		"type": "drivers_routes_map",
		"max_distance_m": max_distance_m,
		**data,
	}
