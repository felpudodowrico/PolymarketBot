# scanner.py (ARBITRAGE OPTIMIZED - ARBITRAGE FILTERED)

import requests
import json
import time
import threading
import random
import signal
import sys
import math
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import MIN_LIQUIDITY, MIN_VOLUME, CATEGORIES, MULTI_OUTCOME, MAX_SPREAD_FILTER

# =======================
# ARBITRAGE CONFIG
# =======================

TOP_N_ORDERBOOK = 40
ORDERBOOK_COOLDOWN_SEC = 0.35
MAX_SNAPSHOTS_PER_MARKET = 120

CLOB_TIMEOUT = 2.5
GAMMA_TIMEOUT = 3.5

CLOB_MAX_WORKERS = 16
MIN_LOOP_INTERVAL_SEC = 0.15

CLOB_BOOK_URL = "https://clob.polymarket.com/book"
CLOB_HEADERS = {"accept": "application/json", "user-agent": "Mozilla/5.0"}

GAMMA_URL = (
    "https://gamma-api.polymarket.com/events?"
    "active=true&closed=false&order=volume24hr&ascending=false&limit=500"
)

# ---------------- UTIL ----------------
def clear_screen():
    import os, platform
    os.system("cls" if platform.system() == "Windows" else "clear")

def safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

# ---------------- SCANNER ----------------
class EventScannerGamma:
    def __init__(
        self,
        min_liquidity: float = MIN_LIQUIDITY,
        min_volume: float = MIN_VOLUME,
        categories: Optional[List[str]] = CATEGORIES,
        multi_outcome: bool = MULTI_OUTCOME,
        top_n_orderbook: int = TOP_N_ORDERBOOK,
        orderbook_cooldown: float = ORDERBOOK_COOLDOWN_SEC,
        max_snapshots: int = MAX_SNAPSHOTS_PER_MARKET,
        clob_workers: int = CLOB_MAX_WORKERS,
        max_spread: float = MAX_SPREAD_FILTER, 
    ):
        self.min_liquidity = float(min_liquidity)
        self.min_volume = float(min_volume)
        self.categories = [str(c).lower() for c in categories] if categories else None
        self.multi_outcome = bool(multi_outcome)

        self.top_n_orderbook = int(top_n_orderbook)
        self.orderbook_cooldown = float(orderbook_cooldown)
        self.max_snapshots = int(max_snapshots)
        self.clob_workers = int(clob_workers)
        self.arb_opportunities_count = 0  # contador de snapshots válidos (arbitraje)
        self.closest_arb = {
            "spread": float("inf"),
            "market": None,
            "snapshot": None
        }
        self.max_spread = float(max_spread)  

        self.history: Dict[str, List[Dict]] = {}
        self.orderbook_cache: Dict[str, Dict] = {}
        self.orderbook_last_fetch: Dict[str, float] = {}

        self.stop_event = threading.Event()
        self.lock = threading.Lock()

        self.gamma_session = requests.Session()
        self.clob_session = requests.Session()

        self.start_time = time.time()
        self.loops = 0

        self.gamma_requests_this_second = 0
        self.gamma_requests_per_second = 0
        self.orderbooks_fetched_this_second = 0
        self.orderbooks_fetched_per_second = 0
        self.cache_hits_this_second = 0
        self.cache_hits_per_second = 0
        self.snapshots_this_second = 0
        self.snapshots_per_second = 0
        self.loops_this_second = 0
        self.loops_per_second = 0

        self.gamma_response_ms = 0.0
        self.clob_response_ms = 0.0

        self.last_loop_topN = 0
        self.last_loop_orderbooks_requested = 0
        self.last_loop_orderbooks_fetched = 0

        self.tracked_market_ids = set()

    # ---------------- FETCH GAMMA ----------------
    def fetch_events(self) -> List[Dict]:
        start = time.time()
        try:
            with self.lock:
                self.gamma_requests_this_second += 1

            r = self.gamma_session.get(GAMMA_URL, timeout=GAMMA_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            if isinstance(data, list):
                return data
            return []
        except requests.RequestException:
            return []
        finally:
            with self.lock:
                self.gamma_response_ms = (time.time() - start) * 1000.0

    # ---------------- PARSE ----------------
    def parse_outcomes(self, market: Dict) -> List[Dict]:
        outcomes = market.get("outcomes", [])
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except Exception:
                outcomes = []
        if not isinstance(outcomes, list):
            return []
        out = []
        for o in outcomes:
            if isinstance(o, dict):
                out.append(o)
            else:
                out.append({"id": str(o)})
        return out

    def parse_outcome_prices(self, market: Dict) -> Tuple[Optional[float], Optional[float]]:
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
        s = p0 + p1
        if s <= 0:
            return None, None
        return p0 / s, p1 / s

    # ---------------- TOKEN IDS ----------------
    def get_yes_no_token_ids(self, market: Dict) -> Tuple[Optional[str], Optional[str]]:
        clob_ids = market.get("clobTokenIds")
        if isinstance(clob_ids, str):
            try:
                clob_ids = json.loads(clob_ids)
            except Exception:
                clob_ids = None

        if isinstance(clob_ids, list) and len(clob_ids) >= 2:
            return str(clob_ids[0]), str(clob_ids[1])

        outcomes = market.get("_outcomes") or self.parse_outcomes(market)

        yes_id = None
        no_id = None
        for o in outcomes:
            name = str(o.get("name") or o.get("title") or o.get("label") or "").strip().lower()
            tid = o.get("tokenId") or o.get("clobTokenId") or o.get("token_id")
            if tid is None:
                continue
            tid = str(tid)
            if name in ("yes", "y"):
                yes_id = tid
            elif name in ("no", "n"):
                no_id = tid

        if (yes_id is None or no_id is None) and isinstance(outcomes, list) and len(outcomes) == 2:
            t0 = outcomes[0].get("tokenId") or outcomes[0].get("clobTokenId") or outcomes[0].get("token_id")
            t1 = outcomes[1].get("tokenId") or outcomes[1].get("clobTokenId") or outcomes[1].get("token_id")
            if t0 is not None and t1 is not None:
                return str(t0), str(t1)

        return None, None

    # ---------------- CLOB ORDERBOOK ----------------
    def fetch_orderbook(self, token_id: str) -> Optional[Dict]:
        start = time.time()
        try:
            if self.stop_event.is_set():
                return None

            r = self.clob_session.get(
                CLOB_BOOK_URL,
                params={"token_id": token_id},
                headers=CLOB_HEADERS,
                timeout=CLOB_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, dict):
                return None
            return data
        except requests.RequestException:
            return None
        finally:
            with self.lock:
                self.clob_response_ms = (time.time() - start) * 1000.0

    # ---------------- BEST BID/ASK (FILTRADO ARBITRAJE) ----------------
    def best_bid_ask(self, book: Dict) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        bids = [b for b in (book.get("bids") or []) if safe_float(b.get("price")) >= 0.05]
        asks = [a for a in (book.get("asks") or []) if safe_float(a.get("price")) <= 0.95]

        if not bids or not asks:
            return None, None, None, None

        b0 = bids[0]
        a0 = asks[0]

        return (
            safe_float(b0.get("price")),
            safe_float(b0.get("size")),
            safe_float(a0.get("price")),
            safe_float(a0.get("size")),
        )

    # ---------------- FILTER ----------------
    def filter_markets(self, events: List[Dict]) -> List[Dict]:
        filtered = []
        for event in events:
            tags = event.get("tags", ["N/A"])
            category = str(tags[0]).lower() if tags else "n/a"
            if self.categories and category not in self.categories:
                continue

            for m in (event.get("markets") or []):
                liq = safe_float(m.get("liquidityNum") or m.get("liquidity") or 0)
                vol = safe_float(m.get("volumeNum") or m.get("volume") or 0)

                if liq < self.min_liquidity or vol < self.min_volume:
                    continue

                outcomes = self.parse_outcomes(m)

                if not self.multi_outcome and len(outcomes) != 2:
                    continue

                if self.multi_outcome and len(outcomes) <= 2:
                    continue

                m["_outcomes"] = outcomes
                filtered.append(m)

        return filtered

    # ---------------- RANKING ----------------
    def market_score(self, market: Dict) -> float:
        liq = safe_float(market.get("liquidityNum") or market.get("liquidity") or 0)
        vol = safe_float(market.get("volumeNum") or market.get("volume") or 0)

        yes_tid, no_tid = self.get_yes_no_token_ids(market)
        if not (yes_tid and no_tid):
            return 0.0

        p_yes, _ = self.parse_outcome_prices(market)
        if p_yes is None:
            return 0.0

        if p_yes < 0.01 or p_yes > 0.99:
            return 0.0

        center = 1.0 - abs(p_yes - 0.5) * 2.0
        center = max(0.10, center)

        return math.log(vol + 1.0) * math.log(liq + 1.0) * center

    # ---------------- UPDATE TOP ONLY (FILTRADO ARBITRAJE) ----------------
    def update_top_with_books(self, top_markets: List[Dict]):
        now = time.time()
        market_map = {}
        tokens = []

        for m in top_markets:
            market_id = str(m.get("id") or m.get("conditionId") or "unknown")
            yes_tid, no_tid = self.get_yes_no_token_ids(m)
            if not (yes_tid and no_tid):
                continue
            market_map[market_id] = (m, yes_tid, no_tid)
            tokens.append(yes_tid)
            tokens.append(no_tid)

        tokens = list(dict.fromkeys(tokens))
        token_books: Dict[str, Dict] = {}
        tokens_to_fetch = []
        cache_hits = 0

        for tid in tokens:
            last = self.orderbook_last_fetch.get(tid, 0.0)
            if (now - last) < self.orderbook_cooldown:
                cached = self.orderbook_cache.get(tid)
                if cached:
                    token_books[tid] = cached
                    cache_hits += 1
                    continue
            tokens_to_fetch.append(tid)

        orderbooks_requested = len(tokens_to_fetch)
        orderbooks_fetched = 0

        if tokens_to_fetch and not self.stop_event.is_set():
            with ThreadPoolExecutor(max_workers=self.clob_workers) as ex:
                futures = {ex.submit(self.fetch_orderbook, tid): tid for tid in tokens_to_fetch}
                for fut in as_completed(futures):
                    if self.stop_event.is_set():
                        break
                    tid = futures[fut]
                    try:
                        book = fut.result()
                    except Exception:
                        book = None
                    if book:
                        token_books[tid] = book
                        self.orderbook_cache[tid] = book
                        self.orderbook_last_fetch[tid] = now
                        orderbooks_fetched += 1

        with self.lock:
            self.cache_hits_this_second += cache_hits
            self.orderbooks_fetched_this_second += orderbooks_fetched
            self.last_loop_topN = len(market_map)
            self.last_loop_orderbooks_requested = orderbooks_requested
            self.last_loop_orderbooks_fetched = orderbooks_fetched
            self.tracked_market_ids = set(market_map.keys())

            for market_id, (m, yes_tid, no_tid) in market_map.items():
                p_yes, p_no = self.parse_outcome_prices(m)
                if p_yes is None or p_no is None:
                    continue

                by = sy = ay = say = None
                bn = sn = an = san = None

                book_yes = token_books.get(yes_tid)
                book_no = token_books.get(no_tid)

                if book_yes:
                    by, sy, ay, say = self.best_bid_ask(book_yes)
                if book_no:
                    bn, sn, an, san = self.best_bid_ask(book_no)

                spread_yes = ay - by if (ay is not None and by is not None) else None
                spread_no  = an - bn if (an is not None and bn is not None) else None
                
                # FILTRO ARBITRAJE
                if spread_yes is None or spread_no is None:
                    continue
                
                # Actualizamos closest_arb
                min_spread = min(spread_yes, spread_no)
                if min_spread < self.closest_arb["spread"]:
                    self.closest_arb["spread"] = min_spread
                    self.closest_arb["market"] = m
                    self.closest_arb["snapshot"] = {
                        "ts": now,
                        "bestBid_yes": by,
                        "bestAsk_yes": ay,
                        "bestBid_no": bn,
                        "bestAsk_no": an,
                        "p_yes": p_yes,
                        "p_no": p_no
                    }
                
                # Filtro real de arbitraje
                if spread_yes > self.max_spread or spread_no > self.max_spread:
                    continue
                
                # Contamos oportunidad de arbitraje válida
                self.arb_opportunities_count += 1

                snap = {
                    "ts": now,
                    "question": m.get("question", "")[:120],
                    "p_yes": p_yes,
                    "p_no": p_no,
                    "yes_token_id": yes_tid,
                    "no_token_id": no_tid,
                    "bestBid_yes": by,
                    "bestAsk_yes": ay,
                    "bidSize_yes": sy,
                    "askSize_yes": say,
                    "bestBid_no": bn,
                    "bestAsk_no": an,
                    "bidSize_no": sn,
                    "askSize_no": san,
                }

                if market_id not in self.history:
                    self.history[market_id] = []

                self.history[market_id].append(snap)
                if len(self.history[market_id]) > self.max_snapshots:
                    self.history[market_id] = self.history[market_id][-self.max_snapshots:]

                self.snapshots_this_second += 1

            for mid in list(self.history.keys()):
                if mid not in self.tracked_market_ids:
                    del self.history[mid]

    # ---------------- LIVE SCAN ----------------
    def live_scan(self):
        last_loop = 0.0
        while not self.stop_event.is_set():
            now = time.time()
            if (now - last_loop) < MIN_LOOP_INTERVAL_SEC:
                self.stop_event.wait(MIN_LOOP_INTERVAL_SEC - (now - last_loop))
                continue
            last_loop = time.time()

            with self.lock:
                self.loops += 1
                self.loops_this_second += 1

            events = self.fetch_events()
            if self.stop_event.is_set() or not events:
                continue

            filtered = self.filter_markets(events)
            if not filtered:
                continue

            scored = []
            for m in filtered:
                s = self.market_score(m)
                if s > 0.0:
                    scored.append((s, m))

            scored.sort(key=lambda x: x[0], reverse=True)
            top_markets = [m for _, m in scored[: self.top_n_orderbook]]

            if top_markets:
                self.update_top_with_books(top_markets)

    # ---------------- DASHBOARD ----------------
    def display_dashboard(self):
        while not self.stop_event.is_set():
            self.stop_event.wait(1.0)

            with self.lock:
                self.gamma_requests_per_second = self.gamma_requests_this_second
                self.gamma_requests_this_second = 0

                self.orderbooks_fetched_per_second = self.orderbooks_fetched_this_second
                self.orderbooks_fetched_this_second = 0

                self.cache_hits_per_second = self.cache_hits_this_second
                self.cache_hits_this_second = 0

                self.snapshots_per_second = self.snapshots_this_second
                self.snapshots_this_second = 0

                self.loops_per_second = self.loops_this_second
                self.loops_this_second = 0

                tracked = len(self.history)
                ticks_per_market = (self.snapshots_per_second / tracked) if tracked > 0 else 0.0

                example = None
                if tracked > 0:
                    keys = list(self.history.keys())
                    k = random.choice(keys)
                    example = self.history[k][-1]

                gamma_latency = self.gamma_response_ms
                clob_latency = self.clob_response_ms

                last_topN = self.last_loop_topN
                last_req = self.last_loop_orderbooks_requested
                last_fetched = self.last_loop_orderbooks_fetched

            uptime = int(time.time() - self.start_time)

            clear_screen()
            print("=" * 95)
            print("📊 SCANNER REALTIME (ARBITRAGE MODE)")
            print(f"⏱️ Uptime: {uptime}s")
            print(f"🔁 Loops: {self.loops} | {self.loops_per_second} loops/seg")
            print("-" * 95)
            print(f"🎯 Tracked markets (top): {tracked}")
            print("-" * 95)
            print(f"🌐 Gamma req/sec: {self.gamma_requests_per_second}")
            print(f"📚 Orderbooks/sec (fetched): {self.orderbooks_fetched_per_second}")
            print(f"🧊 Cache hits/sec: {self.cache_hits_per_second}")
            print(f"🧾 Snapshots/sec: {self.snapshots_per_second}")
            print(f"🎯 Top-N orderbook por loop: {last_topN}")
            print(f"📌 Orderbooks solicitados (último loop): {last_req} | fetched: {last_fetched}")
            print("-" * 95)
            print(f"⚡ Ticks/market/sec (REAL): {ticks_per_market:.4f}")
            print(f"⏱️ Gamma latency: {gamma_latency:.1f} ms | CLOB latency: {clob_latency:.1f} ms")
            print("=" * 95)
            print(f"⚡ Oportunidades de arbitraje (validas): {self.arb_opportunities_count}")
            if self.closest_arb["market"]:
                m = self.closest_arb["market"]
                s = self.closest_arb["snapshot"]
                print(f"📌 Mejor 'casi oportunidad': {m.get('question','')[:80]}")
                print(f"   Spread mínimo observado: {self.closest_arb['spread']:.4f}")
                print(f"   Mid YES: {s['p_yes']:.4f} | NO: {s['p_no']:.4f}")
                print(f"   Bid/Ask YES: {s['bestBid_yes']:.4f}/{s['bestAsk_yes']:.4f}")
                print(f"   Bid/Ask NO: {s['bestBid_no']:.4f}/{s['bestAsk_no']:.4f}")

            if example:
                print(f"📌 Ejemplo: {example['question']}")
                print(f"📈 Mid YES: {example['p_yes']:.4f} | NO: {example['p_no']:.4f}")

                if example.get("bestBid_yes") is not None:
                    print("📕 ORDERBOOK REAL (YES/NO):")
                    print(
                        f"   YES bid {example['bestBid_yes']:.4f} ({example.get('bidSize_yes')})"
                        f" | ask {example['bestAsk_yes']:.4f} ({example.get('askSize_yes')})"
                    )
                    print(
                        f"   NO  bid {example['bestBid_no']:.4f} ({example.get('bidSize_no')})"
                        f" | ask {example['bestAsk_no']:.4f} ({example.get('askSize_no')})"
                    )
                else:
                    print("📕 ORDERBOOK REAL: (missing token_ids o book vacío)")

                print("=" * 95)

    def stop(self):
        self.stop_event.set()


# ---------------- MAIN ----------------
if __name__ == "__main__":
    scanner = EventScannerGamma()

    scan_thread = threading.Thread(target=scanner.live_scan, daemon=True)
    dash_thread = threading.Thread(target=scanner.display_dashboard, daemon=True)

    scan_thread.start()
    dash_thread.start()

    def signal_handler(sig, frame):
        print("\n[Scanner] Deteniendo ejecución...")
        scanner.stop()
        scan_thread.join(timeout=2)
        dash_thread.join(timeout=2)
        print("[Scanner] Cerrado correctamente.")
        raise SystemExit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        while True:
            time.sleep(0.25)
    except KeyboardInterrupt:
        signal_handler(None, None)
