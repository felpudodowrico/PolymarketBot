# scanner.py optimizado

import requests
import json
import time
from typing import List, Dict, Optional
from collections import deque

class EventScannerGamma:
    BASE_URL = "https://gamma-api.polymarket.com/events?active=true&closed=false&order=volume24hr&ascending=false&limit=500"

    def __init__(
        self,
        min_liquidity: float,
        min_volume: float,
        categories: Optional[List[str]],
        multi_outcome: bool,
        display_delay: float,
        fetch_delay: float,
        max_snapshots: Optional[int]
    ):
        self.min_liquidity = min_liquidity
        self.min_volume = min_volume
        self.categories = [str(c).lower() for c in categories] if categories else None
        self.multi_outcome = multi_outcome
        self.display_delay = display_delay
        self.fetch_delay = fetch_delay
        self.max_snapshots = max_snapshots or 1000

        # Historia optimizada con deque para mantener máximo de snapshots
        # Cada market_id -> {"snapshots": deque(maxlen=max_snapshots), "outcomes": []}
        self.history: Dict[str, Dict] = {}

        self.stats = {
            "start_time": time.time(),
            "loops": 0,
            "total_events_downloaded": 0,
            "total_markets_after_filter": 0,
            "markets_displayed": 0,
            "unique_markets_displayed": set(),
        }

    # ---------------- Fetch eficiente ----------------
    def fetch_events(self) -> List[Dict]:
        try:
            r = requests.get(self.BASE_URL, timeout=10)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            elif isinstance(data, list):
                return data
            return []
        except requests.RequestException as e:
            print(f"[Scanner] Error al conectar con Gamma API: {e}")
            return []

    # ---------------- Parse outcomes ----------------
    def parse_outcomes(self, market: Dict) -> List[Dict]:
        outcomes = market.get("outcomes", [])
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except json.JSONDecodeError:
                outcomes = []
        # Normalizar a lista de dicts
        return [o if isinstance(o, dict) else {"id": str(o)} for o in outcomes]

    # ---------------- Filtrado eficiente ----------------
    def filter_markets(self, events: List[Dict]) -> List[Dict]:
        filtered = []
        for event in events:
            markets = event.get("markets", [])
            tags = event.get("tags", ["N/A"])
            category = str(tags[0]).lower() if tags else "N/A"
            for m in markets:
                liquidity = float(m.get("liquidityNum") or m.get("liquidity") or 0)
                volume = float(m.get("volumeNum") or m.get("volume") or 0)
                outcomes = self.parse_outcomes(m)

                if liquidity < self.min_liquidity or volume < self.min_volume:
                    continue
                if self.categories and category not in self.categories:
                    continue
                if self.multi_outcome and len(outcomes) <= 2:
                    continue

                # Guardar categoría en el market para HybridStrategy
                m["_category"] = category
                m["_outcomes"] = outcomes
                filtered.append(m)
        return filtered

    # ---------------- Update history ----------------
    def update_history(self, markets):
        now = time.time()
    
        for m in markets:
            market_id = str(m.get("id") or m.get("conditionId") or "unknown")
    
            liquidity = float(m.get("liquidityNum") or m.get("liquidity") or 0)
            volume = float(m.get("volumeNum") or m.get("volume") or 0)
    
            question = m.get("question", "")
            close_time = m.get("closeTime") or m.get("endDate") or "N/A"
    
            p_yes, p_no = self.parse_outcome_prices(m)
    
            # Si no hay precios, no podemos simular trading coherente -> saltamos snapshot
            if p_yes is None or p_no is None:
                continue
    
            # Spread simulado (realista) en función de liquidez
            # - mercados líquidos: spread pequeño
            # - mercados ilíquidos: spread grande
            # clamp en [0.002, 0.03]
            spread = 0.03
            if liquidity > 50000:
                spread = 0.003
            elif liquidity > 10000:
                spread = 0.006
            elif liquidity > 2000:
                spread = 0.012
            else:
                spread = 0.02
    
            # Bid/Ask simulados alrededor del precio (mid)
            def make_bid_ask(p):
                bid = max(0.001, p - spread / 2)
                ask = min(0.999, p + spread / 2)
                if bid >= ask:
                    # fallback por seguridad numérica
                    bid = max(0.001, p - 0.001)
                    ask = min(0.999, p + 0.001)
                return bid, ask
    
            bid_yes, ask_yes = make_bid_ask(p_yes)
            bid_no, ask_no = make_bid_ask(p_no)
    
            record = {
                "ts": now,
                "liquidity": liquidity,
                "volume": volume,
                "question": question,
                "closeTime": close_time,
    
                # precios coherentes
                "p_yes": p_yes,
                "p_no": p_no,
                "spread": spread,
    
                "bestBid_yes": bid_yes,
                "bestAsk_yes": ask_yes,
                "bestBid_no": bid_no,
                "bestAsk_no": ask_no,
            }
    
            if market_id not in self.history:
                self.history[market_id] = []
    
            self.history[market_id].append(record)
    
            if self.max_snapshots is not None and len(self.history[market_id]) > self.max_snapshots:
                self.history[market_id] = self.history[market_id][-self.max_snapshots:]

    # ---------------- Live scan optimizado ----------------
    def live_scan(self):
        while True:
            self.stats["loops"] += 1
            events = self.fetch_events()
            self.stats["total_events_downloaded"] = len(events)
            filtered = self.filter_markets(events)
            self.stats["total_markets_after_filter"] = len(filtered)

            if filtered:
                self.update_history(filtered)
            else:
                print("[Scanner] No se encontraron mercados aptos.")

            # Opcional: mostrar solo un mercado para debug
            #if filtered:
            #    display_market_live(filtered[0], self.parse_outcomes)

            time.sleep(self.display_delay)
            
    def parse_outcome_prices(self, market: Dict):
        """
        Devuelve (p_yes, p_no) en float si existe.
        Gamma suele devolverlo como string JSON tipo: ["0.63","0.37"].
        """
        raw = market.get("outcomePrices") or market.get("outcomeTokenPrices")
    
        if raw is None:
            return None, None
    
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                return None, None
    
        if not isinstance(raw, list) or len(raw) < 2:
            return None, None
    
        try:
            p0 = float(raw[0])
            p1 = float(raw[1])
        except Exception:
            return None, None
    
        # Normalizamos por si viene mal (a veces no suma 1 exacto)
        s = p0 + p1
        if s <= 0:
            return None, None
    
        p0 /= s
        p1 /= s
    
        return p0, p1