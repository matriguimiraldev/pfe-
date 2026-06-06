import unittest

from app.agent import run_dispatch_agent
from app.tools.live_tools import (
    get_current_orders_in_zone,
    get_drivers_by_status_in_zone,
    live_tools_service,
)


class LiveCountToolsTest(unittest.TestCase):
    def setUp(self):
        self._previous_drivers = dict(live_tools_service._drivers)
        self._previous_connected = live_tools_service._connected
        self._previous_stream_url = live_tools_service.config.stream_url
        with live_tools_service._lock:
            live_tools_service._drivers = {}
            for dm_id in range(1, 21):
                live_tools_service._drivers[dm_id] = {
                    "dm_id": dm_id,
                    "zone_id": 1,
                    "commandes": [],
                }
            for dm_id in range(21, 41):
                live_tools_service._drivers[dm_id] = {
                    "dm_id": dm_id,
                    "zone_id": 1,
                    "commandes": [{"id": f"cmd-{dm_id}", "status": "active"}],
                }

    def tearDown(self):
        with live_tools_service._lock:
            live_tools_service._drivers = self._previous_drivers
            live_tools_service._connected = self._previous_connected
            live_tools_service.config.stream_url = self._previous_stream_url

    def test_drivers_by_status_tool_counts_sfax(self):
        result = get_drivers_by_status_in_zone(zone_id=1)

        self.assertEqual(result["zone_name"], "Sfax")
        self.assertEqual(result["total_drivers"], 40)
        self.assertEqual(result["status_counts"]["disponible"], 20)
        self.assertEqual(result["status_counts"]["occupe"], 20)

    def test_agent_answers_driver_status_count_question(self):
        result = run_dispatch_agent("donner moi le nombre de livreur selon leurs statu dans la zone sfax")

        self.assertEqual(result["intent"], "drivers_by_status")
        self.assertEqual(result["tool_name"], "drivers_by_status")
        self.assertEqual(result["answer"], "Dans Sfax: 20 livreur(s) disponible(s) et 20 livreur(s) occupe(s).")

    def test_current_orders_tool_and_agent(self):
        tool_result = get_current_orders_in_zone(zone_id=1)
        self.assertEqual(tool_result["current_orders_count"], 20)

        agent_result = run_dispatch_agent("combien de commande actuelle dans la zone sfax")
        self.assertEqual(agent_result["intent"], "current_orders")
        self.assertEqual(agent_result["answer"], "Dans Sfax: 20 commande(s) actuelle(s).")

    def test_drivers_remain_in_cache_between_sse_updates(self):
        with live_tools_service._lock:
            live_tools_service.config.stream_url = "http://sse.test/live"
            live_tools_service._connected = True
            live_tools_service._drivers = {
                1: {
                    "dm_id": 1,
                    "zone_id": 1,
                    "commandes": [],
                },
                2: {
                    "dm_id": 2,
                    "zone_id": 1,
                    "commandes": [{"id": "old-cmd", "status": "active"}],
                },
            }

        result = get_drivers_by_status_in_zone(zone_id=1, sync_live=False)

        self.assertEqual(result["total_drivers"], 2)
        self.assertEqual(result["status_counts"]["disponible"], 1)
        self.assertEqual(result["status_counts"]["occupe"], 1)


if __name__ == "__main__":
    unittest.main()
