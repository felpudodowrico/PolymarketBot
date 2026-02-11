# hybrid_strategy.py
import time
import threading
import random
import os
import platform
from scanner import EventScannerGamma
import config

# Configuración
ORDER_REFRESH = 1          # segundos entre ciclos
MAX_ORDER_SIZE = 50
SPREAD = 0.02              # para arbitraje
ARBITRAGE_THRESHOLD = 0.02
SCALPING_VOLUME_FACTOR = 1.5
SCALPING_LIQUIDITY_FACTOR = 0.5
DASHBOARD_HISTORY = 10     # número de operaciones recientes a mostrar

def clear_screen():
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")

class HybridStrategy:
    def __init__(self, scanner: EventScannerGamma):
        self.scanner = scanner
        self.active_orders = {}   # order_id -> dict
        self.completed_orders = []  # órdenes ejecutadas
        self.pnl = {"contrarian": 0.0, "arbitrage": 0.0, "scalping": 0.0}
        self.start_time = time.time()
        self.order_counter = 0

    # ===================== Utilidades =====================
    def mid_price(self, market):
        bid = float(market.get("bestBid") or 0)
        ask = float(market.get("bestAsk") or 1)
        return (bid + ask) / 2

    def place_order(self, market_id, outcome_id, side, strategy, market, size=MAX_ORDER_SIZE):
        order_id = f"{market_id}_{outcome_id}_{side}_{self.order_counter}"
        self.order_counter += 1

        # Precio de ejecución realista
        price_executed = float(market.get("bestAsk") or 1) if side == "buy" else float(market.get("bestBid") or 0)

        self.active_orders[order_id] = {
            "market": market_id,
            "outcome": outcome_id,
            "side": side,
            "strategy": strategy,
            "ts": time.time(),
            "price_executed": price_executed,
            "question": market.get("question", "N/A"),
            "closeTime": market.get("closeTime", "N/A")
        }
        return order_id

    def execute_order(self, order_id):
        if order_id not in self.active_orders:
            return
        o = self.active_orders.pop(order_id)

        # Calculamos PnL según estrategia
        pnl_change = 0.0
        mid = self.mid_price(self.scanner.history[o["market"]][-1])
        if o["strategy"] in ["contrarian", "scalping"]:
            if o["side"] == "buy":
                pnl_change = (mid - o["price_executed"]) * MAX_ORDER_SIZE
            else:
                pnl_change = (o["price_executed"] - mid) * MAX_ORDER_SIZE
        elif o["strategy"] == "arbitrage":
            pnl_change = SPREAD * MAX_ORDER_SIZE

        self.pnl[o["strategy"]] += pnl_change
        o["pnl"] = pnl_change
        o["exit_price"] = mid
        o["executed_ts"] = time.time()
        self.completed_orders.append(o)

def display_dashboard(self):
    clear_screen()
    uptime = int(time.time() - self.start_time)
    total_orders = len(self.completed_orders) + len(self.active_orders)
    executed_orders = len(self.completed_orders)
    total_pnl = sum(self.pnl.values())
    success_rate = (executed_orders / total_orders * 100) if total_orders > 0 else 0

    # Métricas de scanner
    total_markets = len(self.scanner.history)
    total_snapshots = sum(len(snapshots) for snapshots in self.scanner.history.values())
    # Número de snapshots añadidos desde el último paso
    snapshots_this_step = total_snapshots - getattr(self, 'last_total_snapshots', 0)
    self.last_total_snapshots = total_snapshots

    print("="*100)
    print("📊 HYBRID STRATEGY DASHBOARD (SIMULACIÓN REALISTA)")
    print("="*100)
    print(f"⏱️ Uptime: {uptime}s | 🟢 Órdenes activas: {len(self.active_orders)} | ✅ Ejecutadas: {executed_orders}")
    print(f"💹 PnL total: {round(total_pnl,2)} | 📊 Ratio de éxito: {round(success_rate,2)}%")
    print(f"🧐 Mercados escaneados: {total_markets} | Snapshots totales: {total_snapshots} | Snapshots en este paso: {snapshots_this_step}")
    print("-"*100)
    print("PnL por estrategia:")
    for s, v in self.pnl.items():
        print(f" {s}: {round(v,2)}")
    print("-"*100)
    print(f"Últimas {DASHBOARD_HISTORY} operaciones ejecutadas:")
    for o in self.completed_orders[-DASHBOARD_HISTORY:]:
        print(f"[{time.strftime('%H:%M:%S', time.localtime(o['executed_ts']))}] "
              f"{o['strategy'].upper():10} | {o['side']:4} | Q: {o['question'][:50]:50} | "
              f"Cierre: {o['closeTime']} | Entrada: {o['price_executed']:.2f} | Salida: {o['exit_price']:.2f} | PnL: {o['pnl']:.2f}")
    print("="*100+"\n")

    # ================= Estrategias ===================
    def contrarian_strategy(self, market, outcome, market_id, outcome_id):
        price = self.mid_price(market)
        if price > 0.7:
            self.place_order(market_id, outcome_id, "sell", "contrarian", market)
        elif price < 0.3:
            self.place_order(market_id, outcome_id, "buy", "contrarian", market)

    def arbitrage_strategy(self, market_id, outcome_id, market_map):
        related = market_map.get(market_id, [])
        for rel_market in related:
            price1 = self.mid_price(self.scanner.history[market_id][-1])
            price2 = self.mid_price(self.scanner.history[rel_market][-1])
            if abs(price1 + price2 - 1) > ARBITRAGE_THRESHOLD:
                self.place_order(market_id, outcome_id, "buy", "arbitrage",
                                 self.scanner.history[market_id][-1])
                self.place_order(rel_market, outcome_id, "sell", "arbitrage",
                                 self.scanner.history[rel_market][-1])

    def scalping_strategy(self, market, outcome, market_id, outcome_id):
        history = self.scanner.history[market_id]
        if len(history) < 2:
            return
        last_snapshot = history[-2]
        vol_now = float(market.get("volume") or 0)
        vol_prev = float(last_snapshot.get("volume") or 1)
        liq_now = float(market.get("liquidityNum") or 1)
        liq_prev = float(last_snapshot.get("liquidityNum") or 1)

        if vol_now > SCALPING_VOLUME_FACTOR * vol_prev:
            self.place_order(market_id, outcome_id, "buy", "scalping", market)
        if liq_now < SCALPING_LIQUIDITY_FACTOR * liq_prev:
            self.place_order(market_id, outcome_id, "sell", "scalping", market)

    # ================== RUN =====================
    def run(self):
        print("Hybrid Strategy iniciado (simulación rápida y eficiente)...")
        market_map = {}  # Para arbitraje: poblar manualmente si se desea
        while True:
            markets = list(self.scanner.history.keys())
            for market_id in markets:
                snapshots = self.scanner.history[market_id]
                last_snapshot = snapshots[-1]
                outcomes = last_snapshot.get("outcomes") or [{"id": "1"}, {"id": "2"}]

                for idx, outcome in enumerate(outcomes):
                    outcome_id = outcome.get("id", idx)
                    # Estrategias
                    self.contrarian_strategy(last_snapshot, outcome, market_id, outcome_id)
                    self.scalping_strategy(last_snapshot, outcome, market_id, outcome_id)

                self.arbitrage_strategy(market_id, outcome_id, market_map)

            # Ejecutar órdenes con 70% de probabilidad
            for order_id in list(self.active_orders.keys()):
                if random.random() < 0.7:
                    self.execute_order(order_id)

            self.display_dashboard()
            time.sleep(ORDER_REFRESH)


# ================== MAIN =========================
if __name__ == "__main__":
    scanner = EventScannerGamma(
        min_liquidity=config.MIN_LIQUIDITY,
        min_volume=config.MIN_VOLUME,
        categories=config.CATEGORIES,
        multi_outcome=config.MULTI_OUTCOME,
        display_delay=0.2,   # menos delay para más snapshots
        fetch_delay=0.2,
        max_snapshots=1000
    )
    threading.Thread(target=scanner.live_scan, daemon=True).start()

    hs = HybridStrategy(scanner)
    hs.run()