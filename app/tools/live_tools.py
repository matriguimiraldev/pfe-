import json
import os
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

ZONES: Dict[int, Dict[str, Any]] = {
    1: {"name": "Sfax", "lat": 34.7406, "lng": 10.7603},
}


@dataclass
class LiveToolsConfig:
    stream_url: str
    connect_timeout_s: float = 10.0
    read_timeout_s: float = 60.0
    reconnect_delay_s: float = 2.0


class LiveToolsService:
    """
    Consumes REAL_TIME_ZIGZAG SSE stream and keeps latest driver state in memory.
    """

    def __init__(self, config: LiveToolsConfig):
        self.config = config
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._connected = False
        self._last_error: Optional[str] = None
        self._last_event_at: Optional[str] = None
        self._events_seen = 0

        # Latest event per delivery man id.
        self._drivers: Dict[int, Dict[str, Any]] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="live-tools-sse", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)



    def get_driver_positions(self, zone_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._drivers.values())

        if zone_id is not None:
            items = [d for d in items if d.get("zone_id") == zone_id]
        for item in items:
            z_id = item.get("zone_id")
            zone = ZONES.get(z_id)
            if zone:
                item["zone_name"] = zone["name"]
        return items

    def get_driver_by_id(self, dm_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._drivers.get(dm_id)

    def get_zone_live_load(self, zone_id: Optional[int] = None) -> Dict[str, Any]:
        rows = self.get_driver_positions(zone_id=zone_id)
        status_counter: Counter[str] = Counter()
        active_orders = 0

        for row in rows:
            commandes = row.get("commandes") or []
            active_orders += len(commandes)
            for order in commandes:
                status_counter[str(order.get("status", "unknown"))] += 1

        return {
            "zone_id": zone_id,
            "zone_name": ZONES.get(zone_id, {}).get("name") if zone_id is not None else None,
            "drivers_online": len(rows),
            "active_orders": active_orders,
            "orders_by_status": dict(status_counter),
        }

    def _run_loop(self) -> None:
        if not self.config.stream_url:
            with self._lock:
                self._last_error = "REAL_TIME_ZIGZAG is missing in environment."
            return

        while not self._stop_event.is_set():
            try:
                with httpx.Client(
                    timeout=httpx.Timeout(
                        connect=self.config.connect_timeout_s,
                        read=self.config.read_timeout_s,
                        write=self.config.connect_timeout_s,
                        pool=self.config.connect_timeout_s,
                    ),
                ) as client:
                    with client.stream("GET", self.config.stream_url) as response:
                        response.raise_for_status()
                        self._set_connected(True)
                        for line in response.iter_lines():
                            if self._stop_event.is_set():
                                break
                            self._consume_line(line)
            except Exception as exc:
                with self._lock:
                    self._connected = False
                    self._last_error = str(exc)
                time.sleep(self.config.reconnect_delay_s)

    def _set_connected(self, connected: bool) -> None:
        with self._lock:
            self._connected = connected
            if connected:
                self._last_error = None

    def _consume_line(self, raw_line: str) -> None:
        line = (raw_line or "").strip()
        if not line.startswith("data:"):
            return

        payload = line[5:].strip()
        if not payload:
            return
        if payload.startswith("Subscribed to topic"):
            return

        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            return

        dm_id = obj.get("dm_id")
        if dm_id is None:
            return

        with self._lock:
            self._drivers[int(dm_id)] = obj
            self._events_seen += 1
            self._last_event_at = datetime.utcnow().isoformat() + "Z"


def _build_config_from_env() -> LiveToolsConfig:
    return LiveToolsConfig(
        stream_url=os.getenv("REAL_TIME_ZIGZAG", "").strip(),
        connect_timeout_s=float(os.getenv("REAL_TIME_ZIGZAG_CONNECT_TIMEOUT", "10")),
        read_timeout_s=float(os.getenv("REAL_TIME_ZIGZAG_READ_TIMEOUT", "60")),
        reconnect_delay_s=float(os.getenv("REAL_TIME_ZIGZAG_RECONNECT_DELAY", "2")),
    )


live_tools_service = LiveToolsService(config=_build_config_from_env())


# Family: live_tools (callables for agent/tooling layer)
def get_driver_positions(zone_id: Optional[int] = None) -> List[Dict[str, Any]]:
    return live_tools_service.get_driver_positions(zone_id=zone_id)


def get_driver_by_id(dm_id: int) -> Optional[Dict[str, Any]]:
    return live_tools_service.get_driver_by_id(dm_id=dm_id)


def get_zone_live_load(zone_id: Optional[int] = None) -> Dict[str, Any]:
    return live_tools_service.get_zone_live_load(zone_id=zone_id)


def get_zone_id_by_name(zone_name: str) -> Optional[int]:
    normalized = (zone_name or "").strip().lower()
    if not normalized:
        return None
    for zone_id, zone in ZONES.items():
        if zone["name"].strip().lower() == normalized:
            return zone_id
    return None


def get_drivers_by_status_in_zone(zone_id: Optional[int] = None, status_filter: Optional[str] = None) -> Dict[str, Any]:
    """Return drivers in a zone grouped by their status."""
    rows = live_tools_service.get_driver_positions(zone_id=zone_id)
    available_drivers: List[Dict[str, Any]] = []
    occupied_drivers: List[Dict[str, Any]] = []

    for driver in rows:
        commandes = driver.get("commandes") or []
        driver_status = "occupé" if len(commandes) > 0 else "disponible"

        if status_filter:
            normalized_filter = status_filter.strip().lower()
            if normalized_filter not in driver_status:
                continue

        if driver_status == "occupé":
            occupied_drivers.append(driver)
        else:
            available_drivers.append(driver)

    by_status: Dict[str, List[Dict[str, Any]]] = {
        "disponible": available_drivers,
        "occupé": occupied_drivers,
    }

    zone_name = ZONES.get(zone_id, {}).get("name") if zone_id is not None else None
    return {
        "zone_id": zone_id,
        "zone_name": zone_name,
        "drivers_by_status": by_status,
        "total_drivers": len(rows),
        "drivers_filtered": len(available_drivers) + len(occupied_drivers),
        "status_counts": {
            "disponible": len(available_drivers),
            "occupé": len(occupied_drivers),
        },
    }
