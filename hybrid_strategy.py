# hybrid_strategy_fast.py
import time
import threading
import random
import os
import platform
import numpy as np
from scanner import EventScannerGamma
import config

# ================= CONFIG =================
ORDER_REFRESH = 1
MAX_ORDER_SIZE = 50
SPREAD = 0.02
ARBITRAGE_THRESHOLD = 0.02
SCALPING_VOLUME_FACTOR = 1.5
SCALPING_LIQUIDITY_FACTOR = 0.5
BUY_THRESHOLD = 0.25
SELL_THRESHOLD = 0.75
DASHBOARD_HISTORY = 10
TOP_MARKETS = 20
TOP_CATEGORIES = 3

# ================= UTILIDADES =================
def clear_screen():
    os.system("cls" if platform.system() == "Windows" else "clear")

# ================= HYBRID STRATEGY =================
class HybridStrategy:
    def __init__(self, scanner: EventScannerGamma):
        self.scanner = scanner
        self.active_orders = {}
        self.completed_orders = []
        self.pnl = {"contrarian": 0.0, "arbitrage": 0.0, "scalping": 0.0}
        self.start_time = time.time()
        self.order_counter = 0
        self.last_total_snapshots = 0
        self.step_counter = 0
        self.last_snapshot_ts = time.time()
        self.last_step_ts = time.time()
        self.initial_deposit = 1000.0   # cámbialo a lo que quieras
        self.last_total_snapshots = 0
        self.step_counter = 0
        
        self.last_trade_ts = {}  # (market_id, outcome_side, strategy) -> ts
        self.min_trade_interval = 5.0  # segundos

    # ---------------- UTILIDADES ----------------
    def mid_price(self, snapshot, outcome_side="yes"):
        if outcome_side == "yes":
            bid = float(snapshot.get("bestBid_yes") or 0)
            ask = float(snapshot.get("bestAsk_yes") or 1)
        else:
            bid = float(snapshot.get("bestBid_no") or 0)
            ask = float(snapshot.get("bestAsk_no") or 1)
        return (bid + ask) / 2
    
    def can_trade(self, market_id, outcome_side, strategy):
        key = (market_id, outcome_side, strategy)
        now = time.time()
        last = self.last_trade_ts.get(key, 0)
        if now - last < self.min_trade_interval:
            return False
        self.last_trade_ts[key] = now
        return True

    def place_order(self, market_id, outcome_side, side, strategy, snapshot, size=MAX_ORDER_SIZE):
        """
        outcome_side: "yes" o "no"
        side: buy/sell
        """
        order_id = f"{market_id}_{outcome_side}_{side}_{self.order_counter}"
        self.order_counter += 1
    
        if outcome_side == "yes":
            bid = float(snapshot.get("bestBid_yes") or 0)
            ask = float(snapshot.get("bestAsk_yes") or 1)
        else:
            bid = float(snapshot.get("bestBid_no") or 0)
            ask = float(snapshot.get("bestAsk_no") or 1)
    
        # ejecución realista
        price_executed = ask if side == "buy" else bid
    
        self.active_orders[order_id] = {
            "market": market_id,
            "outcome_side": outcome_side,   # yes/no
            "side": side,
            "strategy": strategy,
            "ts": time.time(),
            "price_executed": price_executed,
            "question": snapshot.get("question", "N/A"),
            "closeTime": snapshot.get("closeTime", "N/A"),
            "size": size
        }
        return order_id

    def execute_order(self, order_id):
        if order_id not in self.active_orders:
            return
    
        o = self.active_orders.pop(order_id)
        market_id = o["market"]
    
        if market_id not in self.scanner.history or not self.scanner.history[market_id]:
            return
    
        last_snapshot = self.scanner.history[market_id][-1]
        mid = self.mid_price(last_snapshot, o["outcome_side"])
    
        size = float(o.get("size", MAX_ORDER_SIZE))
        entry = float(o["price_executed"])
    
        # PnL coherente:
        # buy -> ganas si mid sube
        # sell -> ganas si mid baja
        if o["side"] == "buy":
            pnl_change = (mid - entry) * size
        else:
            pnl_change = (entry - mid) * size
    
        self.pnl[o["strategy"]] += pnl_change
        o["pnl"] = pnl_change
        o["exit_price"] = mid
        o["executed_ts"] = time.time()
        self.completed_orders.append(o)
        
        
    def display_dashboard(self):
        clear_screen()
    
        now = time.time()
        uptime = int(now - self.start_time)
    
        executed_orders = len(self.completed_orders)
        total_orders = executed_orders + len(self.active_orders)
    
        # PnL total
        total_pnl = sum(self.pnl.values())
    
        # Balance actual en vivo
        balance = self.initial_deposit + total_pnl
    
        # Hit Rate = % operaciones ganadoras
        if executed_orders == 0:
            hit_rate = 0.0
            winning_orders = 0
        else:
            winning_orders = sum(1 for o in self.completed_orders if o.get("pnl", 0) > 0)
            hit_rate = (winning_orders / executed_orders) * 100
    
        # Métricas del scanner
        total_markets = len(self.scanner.history)
        total_snapshots = sum(len(snapshots) for snapshots in self.scanner.history.values())
    
        # Snapshots añadidos en este paso
        snapshots_this_step = total_snapshots - getattr(self, "last_total_snapshots", 0)
        self.last_total_snapshots = total_snapshots
    
        # Contador de pasos
        self.step_counter += 1
    
        # Snapshots/min y pasos/min
        uptime_minutes = max((now - self.start_time) / 60, 1e-9)
        snapshots_per_min = total_snapshots / uptime_minutes
        steps_per_min = self.step_counter / uptime_minutes
    
        print("=" * 110)
        print("📊 HYBRID STRATEGY DASHBOARD (SIMULACIÓN REALISTA)")
        print("=" * 110)
    
        print(
            f"⏱️ Uptime: {uptime}s | "
            f"🟢 Órdenes activas: {len(self.active_orders)} | "
            f"✅ Ejecutadas: {executed_orders}"
        )
    
        print(
            f"💰 Depósito inicial: {self.initial_deposit:.2f} | "
            f"💳 Balance actual: {balance:.2f} | "
            f"📈 PnL total: {total_pnl:.2f} | "
            f"🎯 Hit Rate: {hit_rate:.2f}% ({winning_orders}/{executed_orders})"
        )
    
        print(
            f"🧐 Mercados escaneados: {total_markets} | "
            f"📸 Snapshots totales: {total_snapshots} | "
            f"➕ Snapshots este paso: {snapshots_this_step} | "
            f"🔁 Pasos: {self.step_counter}"
        )
    
        print(
            f"⚡ Snapshots/min: {snapshots_per_min:.1f} | "
            f"🏃 Pasos/min: {steps_per_min:.1f}"
        )
    
        print("-" * 110)
    
        print(f"Últimas {DASHBOARD_HISTORY} operaciones ejecutadas:")
        for o in self.completed_orders[-DASHBOARD_HISTORY:]:
            print(
                f"[{time.strftime('%H:%M:%S', time.localtime(o['executed_ts']))}] "
                f"{o['strategy'].upper():10} | {o['side']:4} | "
                f"Q: {o['question'][:55]:55} | "
                f"Cierre: {o['closeTime']} | "
                f"Entrada: {o['price_executed']:.3f} | "
                f"Salida: {o['exit_price']:.3f} | "
                f"PnL: {o['pnl']:.2f}"
            )
    
        print("=" * 110 + "\n")
    

    # ---------------- ESTRATEGIAS ----------------
    def contrarian_strategy(self, snapshot, market_id, outcome_side="yes"):
        # SOLO operamos YES para no duplicar señales.
        # Si quieres, puedes invertir la lógica para NO, pero no ambas.
        if outcome_side != "yes":
            return

        if not self.can_trade(market_id, outcome_side, "contrarian"):
            return

        # ====== extraer precios reales ======
        bid = float(snapshot.get("bestBid_yes") or 0)
        ask = float(snapshot.get("bestAsk_yes") or 0)

        # Si no hay book real, fuera
        if bid <= 0 or ask <= 0:
            return
        if ask <= bid:
                return
    
        # Spread absoluto y relativo
        spread = ask - bid
        mid = (bid + ask) / 2
        rel_spread = spread / max(mid, 1e-9)

        # ====== filtros anti-basura ======
        liq = float(snapshot.get("liquidity") or 0)
        vol = float(snapshot.get("volume") or 0)

        # No operar en mercados sin actividad
        if liq < max(25, config.MIN_LIQUIDITY):
            return
        if vol < max(200, config.MIN_VOLUME):
            return

        # No operar si el spread es asqueroso
        # (en extremos suele ser brutal)
        if spread > 0.04:
            return
        if rel_spread > 0.08:
            return

        # No operar en precios demasiado extremos
        # porque el "reversal" suele no existir y te comes drift
        if ask < 0.05 or bid > 0.95:
            return

        # ====== lógica contrarian "buena" ======
        # En contrarian REAL:
        # - si el mercado está "demasiado caro", vendes a BID (lo que te pagan)
        # - si está "demasiado barato", compras a ASK (lo que pagas)

        # Umbrales (ajústalos)
        SELL_LEVEL = 0.78
        BUY_LEVEL  = 0.22

        # Evita comprar barato si el bid es 0 (mercado muerto)
        if bid < 0.01:
            return

        # Si ask está MUY bajo -> comprar (pero pagando ask)
        if ask <= BUY_LEVEL:
        self.place_order(market_id, "yes", "buy", "contrarian", snapshot)

        # Si bid está MUY alto -> vender (pero vendiendo al bid)
        elif bid >= SELL_LEVEL:
        self.place_order(market_id, "yes", "sell", "contrarian", snapshot)
    
    
    
    def contrarian_strategy(self, snapshot, market_id, outcome_side):
        if not self.can_trade(market_id, outcome_side, "contrarian"):
            return
        price = self.mid_price(snapshot, outcome_side)
    
        # contrarian:
        # si YES está carísimo -> vende YES
        # si YES está baratísimo -> compra YES
        # para NO aplica igual (pero es redundante)
        if price > 0.75:
            self.place_order(market_id, outcome_side, "sell", "contrarian", snapshot)
        elif price < 0.25:
            self.place_order(market_id, outcome_side, "buy", "contrarian", snapshot)

    def scalping_strategy(self, snapshot, market_id, outcome_side):
        if not self.can_trade(market_id, outcome_side, "scalping"):
            return
        history = self.scanner.history.get(market_id, [])
        if len(history) < 2:
            return
    
        prev = history[-2]
    
        vol_now = float(snapshot.get("volume") or 0)
        vol_prev = float(prev.get("volume") or 1)
    
        liq_now = float(snapshot.get("liquidity") or 1)
        liq_prev = float(prev.get("liquidity") or 1)
    
        # scalping:
        # - spike de volumen -> buy
        # - caída de liquidez -> sell
        if vol_now > SCALPING_VOLUME_FACTOR * vol_prev:
            self.place_order(market_id, outcome_side, "buy", "scalping", snapshot)
    
        if liq_now < SCALPING_LIQUIDITY_FACTOR * liq_prev:
            self.place_order(market_id, outcome_side, "sell", "scalping", snapshot)

    def arbitrage_strategy(self, market_id, outcome_id, market_map):
        if not self.can_trade(market_id, outcome_side, "arbitrage"):
            return
        related = market_map.get(market_id, [])
        hist = self.scanner.history
        for rel_market in related:
            price1 = hist[market_id]["snapshots"][-1]["mid"]
            price2 = hist[rel_market]["snapshots"][-1]["mid"]
            if abs(price1 + price2 - 1) > ARBITRAGE_THRESHOLD:
                self.place_order(market_id, outcome_id, "buy", "arbitrage", hist[market_id]["snapshots"][-1])
                self.place_order(rel_market, outcome_id, "sell", "arbitrage", hist[rel_market]["snapshots"][-1])

    # ---------------- RUN ----------------
    def run(self):
        print("Hybrid Strategy iniciado (simulación rápida y eficiente)...")
    
        while True:
            market_ids = list(self.scanner.history.keys())
    
            for market_id in market_ids:
                h = self.scanner.history.get(market_id, [])
                if not h:
                    continue
    
                last_snapshot = h[-1]
    
                for outcome_side in ["yes", "no"]:
                    self.contrarian_strategy(last_snapshot, market_id, outcome_side)
                    self.scalping_strategy(last_snapshot, market_id, outcome_side)
    
            # Ejecutar órdenes con probabilidad (simulación)
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
        display_delay=0.2,
        fetch_delay=0.2,
        max_snapshots=1000
    )
    threading.Thread(target=scanner.live_scan, daemon=True).start()
    hs = HybridStrategy(scanner)

    hs.run()
