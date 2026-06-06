import re
import unicodedata
from typing import Any, Dict, Optional, Tuple

from app.tools.driver_tools import find_route_by_query


def _normalize_text(value: str) -> str:
	text = unicodedata.normalize("NFKD", (value or "").lower())
	text = "".join(ch for ch in text if not unicodedata.combining(ch))
	return re.sub(r"\s+", " ", text).strip()


def extract_zone_id(question: str) -> Optional[int]:
	# The current product scope has one live zone: Sfax.
	return 1


def extract_route_kilometer(question: str) -> Optional[float]:
	text = _normalize_text(question or "")
	patterns = [
		r"\b(?:kilometre|kilometres|km|klm)\s*[:#-]?\s*(\d+(?:[.,]\d+)?)\b",
		r"\b(\d+(?:[.,]\d+)?)\s*(?:kilometre|kilometres|km|klm)\b",
	]
	for pattern in patterns:
		match = re.search(pattern, text)
		if match:
			return float(match.group(1).replace(",", "."))
	return None


def extract_place_query(question: str) -> Optional[str]:
	text = (question or "").strip().replace("_", " ")
	if not text:
		return None
	text = re.sub(
		r"\b(?:kilom[eè]tre|kilometre|kilometres|km|klm)\s*[:#-]?\s*\d+(?:[.,]\d+)?\b",
		" ",
		text,
		flags=re.IGNORECASE,
	)
	text = re.sub(
		r"\b\d+(?:[.,]\d+)?\s*(?:kilom[eè]tre|kilometre|kilometres|km|klm)\b",
		" ",
		text,
		flags=re.IGNORECASE,
	)

	patterns = [
		r"\b((?:route|ceinture|avenue|cite|quartier)\s+(?:de|du|des|d')?\s*[\w\u00C0-\u024F\u0600-\u06FF\- ]+)",
		r"\b((?:bab|medina)\s+[\w\u00C0-\u024F\u0600-\u06FF\- ]+)",
		r"\b(?:proche|proches|pres|pres de)\s+(?:de|du|des|d')?\s*([\w\u00C0-\u024F\u0600-\u06FF\- ]+)",
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
	q = _normalize_text(question or "")

	has_driver_intent = any(k in q for k in ["livreur", "livreurs", "driver", "drivers", "coursier", "coursiers"])
	has_nearest_intent = any(k in q for k in ["plus proche", "proche de", "nearest", "closest", "le plus proche"])
	has_count_intent = any(k in q for k in ["nombre", "combien", "count", "total"])
	has_status_intent = any(
		k in q
		for k in [
			"statut",
			"statu",
			"status",
			"etat",
			"disponible",
			"libre",
			"actif",
			"offline",
			"en ligne",
			"occupe",
			"occupes",
		]
	)
	has_order_intent = any(k in q for k in ["commande", "commandes", "order", "orders"])
	has_current_intent = any(k in q for k in ["actuelle", "actuelles", "active", "actives", "en cours", "maintenant"])

	place_query = extract_place_query(question)
	route_km = extract_route_kilometer(question)
	zone_id = extract_zone_id(question)

	if has_order_intent and (has_count_intent or has_current_intent or "zone" in q or "sfax" in q):
		return "current_orders", {"zone_id": zone_id}

	if has_driver_intent and (has_status_intent or (has_count_intent and ("zone" in q or "sfax" in q))):
		return "drivers_by_status", {"zone_id": zone_id}

	if has_driver_intent and route_km is not None and place_query:
		return "drivers_near_route_kilometer", {
			"route_query": place_query,
			"target_km": route_km,
		}

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

	live_keywords = ["position", "positions", "livreurs", "drivers", "carte", "flux", "charge"]
	if any(keyword in q for keyword in live_keywords):
		return "driver_positions", {"zone_id": None}

	return None, {}
