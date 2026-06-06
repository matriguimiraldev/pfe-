import unittest
from unittest.mock import patch

from app.agent import run_dispatch_agent
from app.intent_detector import detect_intent
from app.tools.driver_tools import get_drivers_near_route_kilometer


class RouteKilometerToolsTest(unittest.TestCase):
    def test_detects_route_and_kilometer(self):
        intent, params = detect_intent(
            "donner moi les livreurs les plus proches de route lafrane klm 5"
        )

        self.assertEqual(intent, "drivers_near_route_kilometer")
        self.assertEqual(params["route_query"].lower(), "route lafrane")
        self.assertEqual(params["target_km"], 5.0)

    @patch("app.tools.driver_tools.get_ors_road_distance_km")
    @patch("app.tools.driver_tools.get_driver_positions")
    def test_filters_with_one_kilometer_tolerance(self, mock_positions, mock_ors):
        mock_positions.return_value = [
            {"dm_id": 101, "zone_id": 1, "lat": 34.7485, "long": 10.7200},
            {"dm_id": 102, "zone_id": 1, "lat": 34.7465, "long": 10.7300},
        ]
        mock_ors.side_effect = lambda end_lat, end_lng: 5.4 if end_lng == 10.7200 else 7.2

        result = get_drivers_near_route_kilometer(
            route_query="route lafrane",
            target_km=5,
            tolerance_km=1,
            route_radius_m=1000,
        )

        self.assertTrue(result["route_found"])
        self.assertEqual(result["drivers_count"], 1)
        self.assertEqual(result["drivers"][0]["dm_id"], 101)
        self.assertEqual(result["drivers"][0]["road_distance_from_sfax_center_km"], 5.4)

    @patch("app.agent.get_drivers_near_route_kilometer")
    def test_agent_formats_matching_drivers(self, mock_tool):
        mock_tool.return_value = {
            "route_found": True,
            "route_name_fr": "Route Lafrane",
            "target_km": 5,
            "tolerance_km": 1,
            "candidates_count": 2,
            "ors_failures": 0,
            "drivers": [
                {
                    "dm_id": 101,
                    "road_distance_from_sfax_center_km": 5.4,
                }
            ],
        }

        result = run_dispatch_agent(
            "donner moi les livreurs les plus proches de route lafrane kilometre 5"
        )

        self.assertEqual(result["intent"], "drivers_near_route_kilometer")
        self.assertIn("DM 101 a 5.4 km", result["answer"])


if __name__ == "__main__":
    unittest.main()
