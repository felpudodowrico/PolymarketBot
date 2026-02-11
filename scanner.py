# scanner.py
import requests
import json
import time
import random
import time
from datetime import datetime
from typing import List, Dict, Optional

class EventScannerGamma:
    BASE_URL = "https://gamma-api.polymarket.com/events"

    def __init__(self):
        self.history = {}  # market_id -> list[snapshots]
        self.stats = {
            "start_time": time.time(),
            "loops": 0,
            "total_events_downloaded": 0,
            "total_markets_after_filter": 0,
            "markets_displayed": 0,
            "unique_markets_displayed": set(),
        }
    
    def fetch_events(self, limit: int = 50, active: bool = True) -> List[Dict]:
        """
        Obtiene eventos desde Gamma API.
        """
        params = {
            "limit": limit,
            "active": str(active).lower(),
        }
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=10)
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
        """
        Asegura que outcomes siempre sean lista de dicts.
        """
        outcomes = market.get("outcomes", [])
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
                # asegurarse que cada item es dict con clave 'outcome'
                outcomes = [
                    o if isinstance(o, dict) else {"outcome": str(o)}
                    for o in outcomes
                ]
            except json.JSONDecodeError:
                outcomes = []
        elif isinstance(outcomes, list):
            # asegurarse que cada item es dict con clave 'outcome'
            outcomes = [
                o if isinstance(o, dict) else {"outcome": str(o)}
                for o in outcomes
            ]
        else:
            outcomes = []
        return outcomes

    def filter_markets(
        self,
        events: List[Dict],
        min_liquidity: float = 50,
        min_volume: float = 5000,
        categories: Optional[List[str]] = None,
        multi_outcome: bool = True
    ) -> List[Dict]:
        """
        Filtra mercados dentro de los eventos según parámetros.
        """
        filtered = []
        for event in events:
            markets = event.get("markets", [])
            for m in markets:
                liquidity = float(m.get("liquidityNum", 0))
                volume = float(m.get("volume", 0))
                outcomes = self.parse_outcomes(m)
                category = event.get("tags", [""])[0] if event.get("tags") else ""

                if liquidity < min_liquidity or volume < min_volume:
                    continue
                if categories and category.lower() not in [c.lower() for c in categories]:
                    continue
                if multi_outcome and len(outcomes) <= 2:
                    continue
                filtered.append(m)
        return filtered

    def display_market_live(self, market: Dict):
        """
        Muestra un mercado en pantalla.
        """
        outcomes = self.parse_outcomes(market)
        print("=== Mercado Polymarket multi-outcome encontrado ===")
        print(f"ID: {market.get('id')}")
        print(f"Pregunta: {market.get('question')}")
        print(f"Liquidity: {market.get('liquidityNum')}")
        print(f"Volume: {market.get('volume')}")
        print(f"Outcomes: {[o.get('outcome', 'N/A') for o in outcomes]}")
        print(f"Best Bid: {market.get('bestBid')}")
        print(f"Best Ask: {market.get('bestAsk')}")
        if "clobTokenIds" in market:
            print(f"Token IDs: {market['clobTokenIds']}")
        print("------------------------\n")

    def update_history(self, markets):
        """
        Guarda snapshots históricos por market_id.
        Estructura:
            self.history[market_id] = [
                {snapshot1},
                {snapshot2},
                ...
            ]
        """

        now = time.time()

        for m in markets:
            market_id = str(m.get("id") or m.get("conditionId") or "unknown")

            liquidity = float(m.get("liquidityNum") or m.get("liquidity") or 0)
            volume = float(m.get("volumeNum") or m.get("volume") or 0)

            record = {
                "ts": now,
                "liquidity": liquidity,
                "volume": volume,
                "question": m.get("question", ""),
            }

            if market_id not in self.history:
                self.history[market_id] = []

            self.history[market_id].append(record)

            # Para no comernos RAM en Termux:
            # dejamos máximo 300 snapshots por mercado (~10 min si refrescas cada 2s)
            if len(self.history[market_id]) > 300:
                self.history[market_id] = self.history[market_id][-300:]
    
    def live_scan(self, limit: int = 50, min_liquidity: float = 1000):
        idx = 0

        while True:
            self.stats["loops"] += 1
 
            events = self.fetch_events(limit=limit)
            self.stats["total_events_downloaded"] = len(events)

            filtered = self.filter_markets(events, min_liquidity=min_liquidity)
            self.stats["total_markets_after_filter"] = len(filtered)
    
            if not filtered:
                print("No se encontraron mercados aptos.")
                time.sleep(2)
                continue

            if idx >= len(filtered):
                idx = 0

            market = filtered[idx]
            idx += 1
    
            # stats de display
            self.stats["markets_displayed"] += 1
            self.stats["unique_markets_displayed"].add(str(market.get("id", "N/A")))

            # mostrar stats + mercado
            self.print_scan_stats(idx=idx, total_filtered=len(filtered))
            self.display_market_live(market)
            self.update_history([market])

            time.sleep(1)
        
    def print_scan_stats(self, idx: int, total_filtered: int):
        uptime = int(time.time() - self.stats["start_time"])

        print("\n" + "=" * 60)
        print("📊 ESTADÍSTICAS DEL SCANNER")
        print("=" * 60)
        print(f"⏱️  Uptime: {uptime}s")
        print(f"🕒 Ahora: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"🔁 Loops: {self.stats['loops']}")
        print(f"⬇️  Eventos descargados (último fetch): {self.stats['total_events_downloaded']}")
        print(f"✅ Mercados tras filtro: {total_filtered}")
        print(f"📺 Mercados mostrados: {self.stats['markets_displayed']}")
        print(f"🧠 Mercados únicos mostrados: {len(self.stats['unique_markets_displayed'])}")
        print(f"➡️  Posición actual: {idx}/{total_filtered}")
        print("=" * 60 + "\n")
        
if __name__ == "__main__":
    scanner = EventScannerGamma()
    print("Escaneando mercados activos desde Gamma /events...")
    scanner.live_scan(limit=1000, min_liquidity=10)
