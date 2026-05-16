import re
from typing import Any, Dict, Optional, Tuple

from app.tools.driver_tools import find_route_by_query
from app.tools.live_tools import ZONES


def extract_zone_id(question: str) -> Optional[int]:
	# Always return Sfax zone_id=1
	return 1


def extract_place_query(question: str) -> Optional[str]:
	text = (question or "").strip().replace("_", " ")
	if not text:
		return None

	patterns = [
		r"\b((?:route|ceinture|avenue|cite|cité|quartier)\s+(?:de|du|des|d')?\s*[\w\u00C0-\u024F\u0600-\u06FF\- ]+)",
		r"\b((?:bab|medina)\s+[\w\u00C0-\u024F\u0600-\u06FF\- ]+)",
		r"\b(?:proche|proches|près|pres)\s+(?:de|du|des|d')?\s*([\w\u00C0-\u024F\u0600-\u06FF\- ]+)",
	]
	for pattern in patterns:
		m = re.search(pattern, text, flags=re.IGNORECASE)
		if not m:
			continue
		candidate = m.group(1).strip(" .,!?:;\n\t")
		if candidate:
			return candidate

	route = find_route_by_query(text)
	if route:
		return route.get("name") or route.get("id") or text

	return None


def _is_route_assignment_request(q: str) -> bool:
	hints = [
		"chacun",
		"chaque",
		"leurs routes",
		"leur route",
		"son route",
		"sa route",
		"par route",
	]
	return any(h in q for h in hints)


def detect_intent(question: str) -> Tuple[Optional[str], Dict[str, Any]]:
	q = (question or "").lower()

	has_driver_intent = any(k in q for k in ["livreur", "livreurs", "driver", "drivers", "coursier", "coursiers"])
	has_place_hint = any(
		k in q
		for k in ["route", "ceinture", "avenue", "cite", "cité", "quartier", "zone", "bab", "medina", "sfax"]
	)
	has_nearest_intent = any(k in q for k in ["plus proche", "proche de", "nearest", "closest", "le plus proche"])
	has_status_intent = any(k in q for k in ["statut", "status", "disponible", "actif", "offline", "en ligne", "occupé"])

	place_query = extract_place_query(question)

	# Generic request: list drivers with their assigned/closest routes.
	if has_driver_intent and "route" in q and (_is_route_assignment_request(q) or place_query is None):
		return "drivers_with_routes", {}

	if has_driver_intent and has_nearest_intent and place_query:
		return "nearest_driver_on_route", {"route_query": place_query}

	if has_driver_intent and place_query:
		return "drivers_on_route", {"route_query": place_query}

	m_driver = re.search(r"(?:dm_id|livreur|driver)\s*[:#-]?\s*(\d+)", q)
	if m_driver:
		return "driver_by_id", {"dm_id": int(m_driver.group(1))}

	zone_id = extract_zone_id(question)
	if has_driver_intent and has_status_intent:
		return "drivers_by_status", {"zone_id": zone_id}

	live_keywords = ["position", "positions", "livreurs", "drivers", "carte", "flux", "charge"]
	if any(keyword in q for keyword in live_keywords):
		return "driver_positions", {"zone_id": None}

	return None, {}
