from typing import Any, Dict

from app.intent_detector import detect_intent
from app.tools.driver_tools import get_drivers_on_route, get_nearest_driver_on_route
from app.tools.live_tools import get_driver_by_id, get_driver_positions, get_zone_live_load, get_drivers_by_status_in_zone
from app.tools.map_tools import get_drivers_routes_map


def run_dispatch_agent(question: str) -> Dict[str, Any]:
	"""Tool-first orchestrator for dispatch requests."""
	intent, params = detect_intent(question)
	if not intent:
		return {
			"intent": None,
			"tool_name": None,
			"tool_params": {},
			"tool_result": None,
			"answer": None,
		}

	tool_name = intent
	tool_result: Any = None
	answer = None

	if intent == "drivers_on_route":
		tool_result = get_drivers_on_route(params["route_query"])
		if not tool_result.get("route_found"):
			answer = (
				"Je n'ai pas trouve cette route dans le fichier des routes Sfax. "
				"Peux-tu donner le nom exact (ex: Route de Tunis, Route Lafrane) ?"
			)
		else:
			route_name = tool_result.get("route_name_fr") or params["route_query"]
			count = int(tool_result.get("drivers_count") or 0)
			drivers = tool_result.get("drivers") or []
			driver_ids = []
			seen_ids = set()
			for driver in drivers:
				dm_id = driver.get("dm_id") or driver.get("id")
				if dm_id is None:
					continue
				dm_id_str = str(dm_id)
				if dm_id_str in seen_ids:
					continue
				seen_ids.add(dm_id_str)
				driver_ids.append(dm_id_str)

			if count == 0:
				answer = f"Aucun livreur proche de {route_name}."
			elif driver_ids:
				partial_hint = " (liste partielle)" if len(driver_ids) < count else ""
				answer = (
					f"J'ai trouve {count} livreur(s) proches de {route_name}. "
					f"IDs: {', '.join(driver_ids)}{partial_hint}."
				)
			else:
				answer = (
					f"J'ai trouve {count} livreur(s) proches de {route_name}, "
					"mais les IDs ne sont pas disponibles."
				)

	elif intent == "nearest_driver_on_route":
		tool_result = get_nearest_driver_on_route(params["route_query"])
		if not tool_result.get("route_found"):
			answer = (
				"Je n'ai pas trouve cette route dans le fichier des routes Sfax. "
				"Peux-tu donner le nom exact (ex: Route de Tunis, Route Lafrane) ?"
			)
		else:
			nearest = tool_result.get("nearest_driver")
			if not nearest:
				answer = "Aucun livreur en ligne n'est disponible actuellement."
			else:
				dm_id = nearest.get("dm_id") or nearest.get("id") or "N/A"
				route_name = tool_result.get("route_name_fr") or "cette route"
				distance_m = nearest.get("distance_to_route_m")
				if isinstance(distance_m, (int, float)):
					answer = f"Le livreur le plus proche de {route_name} est DM {dm_id}, a environ {int(distance_m)} m."
				else:
					answer = f"Le livreur le plus proche de {route_name} est DM {dm_id}."

	elif intent == "drivers_with_routes":
		tool_result = get_drivers_routes_map(max_distance_m=1500.0, limit=50)
		if int(tool_result.get("drivers_with_route") or 0) == 0 and int(tool_result.get("drivers_count") or 0) > 0:
			tool_result = get_drivers_routes_map(max_distance_m=5000.0, limit=50)
		count = int(tool_result.get("drivers_count") or 0)
		with_route = int(tool_result.get("drivers_with_route") or 0)
		radius = int(tool_result.get("max_distance_m") or 0)
		answer = (
			f"J'ai {count} livreur(s) en ligne, dont {with_route} rattaches a une route connue. "
			f"(rayon {radius} m). Je peux te donner le detail par livreur si tu veux."
		)

	elif intent == "driver_by_id":
		tool_result = get_driver_by_id(params["dm_id"])
		if not tool_result:
			answer = "Je n'ai pas trouve ce livreur dans le cache live."
		else:
			dm_id = tool_result.get("dm_id") or tool_result.get("id") or params["dm_id"]
			zone_id = tool_result.get("zone_id")
			status = tool_result.get("status") or "inconnu"
			answer = f"DM {dm_id} est en statut {status} (zone {zone_id})."

	elif intent == "drivers_by_status":
		tool_result = get_drivers_by_status_in_zone(zone_id=1)
		zone_name = tool_result.get("zone_name") or "Sfax"
		status_counts = tool_result.get("status_counts") or {}

		available_count = int(status_counts.get("disponible") or 0)
		occupied_count = int(status_counts.get("occupé") or 0)

		if available_count == 0 and occupied_count == 0:
			answer = f"Aucun livreur dans {zone_name}."
		else:
			answer = (
				f"Dans {zone_name}: {available_count} livreur(s) disponible(s) "
				f"et {occupied_count} livreur(s) occupé(s)."
			)

	elif intent == "zone_live_load":
		tool_result = get_zone_live_load(zone_id=1)
		zone_name = tool_result.get("zone_name") or f"zone {params.get('zone_id')}"
		drivers_online = int(tool_result.get("drivers_online") or 0)
		active_orders = int(tool_result.get("active_orders") or 0)
		answer = f"{zone_name}: {drivers_online} livreur(s) en ligne et {active_orders} commande(s) active(s)."

	elif intent == "driver_positions":
		tool_result = get_driver_positions(zone_id=1)[:50]
		answer = f"J'ai {len(tool_result)} position(s) live disponibles."

	return {
		"intent": intent,
		"tool_name": tool_name,
		"tool_params": params,
		"tool_result": tool_result,
		"answer": answer,
	}
