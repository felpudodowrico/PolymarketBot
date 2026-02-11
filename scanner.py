# scanner.py
import requests
import json
import time
from typing import List, Dict, Optional
from dashboard import display_market_live, print_scan_stats

class EventScannerGamma:
    BASE_URL = "https://gamma-api.polymarket.com/events?active=true&closed=false&order=volume24hr&ascending=false&limit=500"

    def __init__(
        self,
        min_liquidity: float,
        min_volume: float,
        categories: Optional[List[str]],
        multi_outcome: bool,
        display_delay: int,
        fetch_delay: int,
        max_snapshots: Optional[int]
    ):
        # Configuración
        self.min_liquidity = min_liquidity
        self.min_volume = min_volume
        self.categories = categories
        self.multi_outcome = multi_outcome
        self.display_delay = display_delay
        self.fetch_delay = fetch_delay
        self.max_snapshots = max_snapshots

        # Datos históricos y estadísticas
        self.history = {}  # market_id -> list[snapshots]
        self.stats = {
            "start_time": time.time(),
            "loops": 0,
            "total_events_downloaded": 0,
            "total_markets_after_filter": 0,
            "markets_displayed": 0,
            "unique_markets_displayed": set(),
        }

    def fetch_events(self) -> List[Dict]:
        try:
            response = requests.get(self.BASE_URL, timeout=10)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "data" in data:
                return data["data"]
            return []
        except requests.RequestException as e:
            print(f"Error al conectar con Gamma API /events: {e}")
            return []

    def parse_outcomes(self, market: Dict) -> List[Dict]:
        outcomes = market.get("outcomes", [])
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
                outcomes = [o if isinstance(o, dict) else {"outcome": str(o)} for o in outcomes]
            except json.JSONDecodeError:
                outcomes = []
        elif isinstance(outcomes, list):
            outcomes = [o if isinstance(o, dict) else {"outcome": str(o)} for o in outcomes]
        else:
            outcomes = []
        return outcomes

    def filter_markets(self, events: List[Dict]) -> List[Dict]:
        filtered = []
        for event in events:
            markets = event.get("markets", [])
            for m in markets:
                liquidity = float(m.get("liquidityNum", 0))
                volume = float(m.get("volume", 0))
                outcomes = self.parse_outcomes(m)
                category = event.get("tags", [""])[0] if event.get("tags") else ""

                if liquidity < self.min_liquidity or volume < self.min_volume:
                    continue
                if self.categories and category.lower() not in [c.lower() for c in self.categories]:
                    continue
                if self.multi_outcome and len(outcomes) <= 2:
                    continue
                filtered.append(m)
        return filtered

    def update_history(self, markets):
        now = time.time()
        for m in markets:
            market_id = str(m.get("id") or m.get("conditionId") or "unknown")
            liquidity = float(m.get("liquidityNum") or m.get("liquidity") or 0)
            volume = float(m.get("volumeNum") or m.get("volume") or 0)
            record = {"ts": now, "liquidity": liquidity, "volume": volume, "question": m.get("question", "")}

            if market_id not in self.history:
                self.history[market_id] = []

            self.history[market_id].append(record)

            if self.max_snapshots is not None and len(self.history[market_id]) > self.max_snapshots:
                self.history[market_id] = self.history[market_id][-self.max_snapshots:]

    def live_scan(self):
        idx = 0
        while True:
            self.stats["loops"] += 1

            events = self.fetch_events()
            self.stats["total_events_downloaded"] = len(events)

            filtered = self.filter_markets(events)
            self.stats["total_markets_after_filter"] = len(filtered)

            if not filtered:
                print("No se encontraron mercados aptos.")
                time.sleep(self.fetch_delay)
                continue

            if idx >= len(filtered):
                idx = 0

            market = filtered[idx]
            idx += 1

            self.stats["markets_displayed"] += 1
            self.stats["unique_markets_displayed"].add(str(market.get("id", "N/A")))

            # Mostrar stats + mercado
            print_scan_stats(self.stats, idx=idx, total_filtered=len(filtered))
            display_market_live(market, self.parse_outcomes)
            self.update_history([market])
            time.sleep(self.display_delay)