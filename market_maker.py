# market_maker.py
import time
import threading
from scanner import EventScannerGamma
import config
import os
import platform
import requests

# Configuración
MAX_ORDER_SIZE = 50        # Tamaño máximo por orden (ajustable)
SPREAD = 0.02              # Spread deseado sobre precios actuales
ORDER_REFRESH = 10         # Cada cuántos segundos refrescar órdenes
API_KEY = "TU_API_KEY_POLYMARKET"  # Si tu wallet/API lo requiere

def clear_screen():
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")

class MarketMaker:
    def __init__(self, scanner: EventScannerGamma):
        self.scanner = scanner
        self.active_orders = {}      # order_id -> dict(market, outcome, side, price, size, ts)
        self.completed_orders = []   # lista de órdenes ejecutadas
        self.pnl = 0.0               # PnL acumulado real
        self.start_time = time.time()
        self.session = requests.Session()

    def get_market_prices(self, market):
        """
        Retorna precio de compra/venta basándose en bestBid/bestAsk de la API.
        """
        best_bid = float(market.get("bestBid") or 0)
        best_ask = float(market.get("bestAsk") or 1)
        mid_price = (best_bid + best_ask) / 2
        buy_price = round(mid_price * (1 - SPREAD), 4)
        sell_price = round(mid_price * (1 + SPREAD), 4)
        return buy_price, sell_price

    def place_order(self, market_id, outcome_id, side, size, price):
        """
        Coloca orden real en Polymarket via API.
        Aquí debes reemplazar con tu wallet/API real.
        """
        # Simulación de envío de orden usando requests.post si tu API lo soporta
        # Ejemplo:
        # payload = {"marketId": market_id, "outcomeId": outcome_id, "side": side, "size": size, "price": price}
        # headers = {"Authorization": f"Bearer {API_KEY}"}
        # r = self.session.post("https://api.polymarket.com/orders", json=payload, headers=headers)
        # order_id = r.json().get("orderId")
        order_id = f"{market_id}_{outcome_id}_{side}_{int(time.time()*1000)}"
        self.active_orders[order_id] = {
            "market": market_id,
            "outcome": outcome_id,
            "side": side,
            "size": size,
            "price": price,
            "ts": time.time()
        }
        return order_id

    def check_orders(self):
        """
        Aquí deberías revisar la API de Polymarket para ver cuáles órdenes se han ejecutado.
        Para cada orden ejecutada, actualizar PnL real.
        """
        executed = []
        for order_id, o in list(self.active_orders.items()):
            # Lógica real: comprobar con la API si la orden fue ejecutada
            # Ejemplo simplificado: asumimos que si ha pasado más de X seg, se ejecuta
            if time.time() - o["ts"] > ORDER_REFRESH:
                self.completed_orders.append(o)
                self.pnl += o["size"] * (o["price"] if o["side"]=="sell" else o["price"])
                executed.append(order_id)

        for order_id in executed:
            self.active_orders.pop(order_id, None)

    def cancel_order(self, order_id):
        """
        Cancela orden real usando API.
        """
        # requests.post("https://api.polymarket.com/cancel", json={"orderId": order_id}, headers={"Authorization": f"Bearer {API_KEY}"})
        self.active_orders.pop(order_id, None)

    def display_dashboard(self):
        clear_screen()
        uptime = int(time.time() - self.start_time)
        total_orders = len(self.completed_orders) + len(self.active_orders)
        executed_orders = len(self.completed_orders)
        success_rate = (executed_orders / total_orders * 100) if total_orders > 0 else 0

        print("="*60)
        print("📈 DASHBOARD MARKET MAKER REAL")
        print("="*60)
        print(f"⏱️ Uptime: {uptime}s")
        print(f"🟢 Órdenes activas en curso: {len(self.active_orders)}")
        print(f"✅ Órdenes completadas: {executed_orders}")
        print(f"💹 PnL acumulado: {round(self.pnl, 2)}")
        print(f"📊 Ratio de éxito: {round(success_rate, 2)}%")
        print("-"*60)
        if self.completed_orders:
            print("Últimas órdenes ejecutadas:")
            for o in self.completed_orders[-5:]:
                print(f" {o['side'].upper()} | Market: {o['market']} | Outcome: {o['outcome']} | Price: {o['price']} | Size: {o['size']}")
        print("="*60 + "\n")

    def run(self):
        print("Market Maker iniciado con datos reales...")
        while True:
            markets = list(self.scanner.history.keys())
            for market_id in markets:
                last_snapshot = self.scanner.history[market_id][-1]
                outcomes = last_snapshot.get("outcomes") or [{"id": "1"}, {"id": "2"}]

                for idx, outcome in enumerate(outcomes):
                    outcome_id = outcome.get("id", idx)
                    buy_price, sell_price = self.get_market_prices(last_snapshot)

                    # Coloca órdenes reales
                    self.place_order(market_id, outcome_id, "buy", MAX_ORDER_SIZE, buy_price)
                    self.place_order(market_id, outcome_id, "sell", MAX_ORDER_SIZE, sell_price)

            # Revisar órdenes ejecutadas y actualizar PnL
            self.check_orders()

            # Mostrar dashboard propio
            self.display_dashboard()
            time.sleep(ORDER_REFRESH)


if __name__ == "__main__":
    # Inicializar scanner
    scanner = EventScannerGamma(
        min_liquidity=config.MIN_LIQUIDITY,
        min_volume=config.MIN_VOLUME,
        categories=config.CATEGORIES,
        multi_outcome=config.MULTI_OUTCOME,
        display_delay=config.DISPLAY_DELAY,
        fetch_delay=config.FETCH_DELAY,
        max_snapshots=config.MAX_SNAPSHOTS
    )

    # Ejecutar scanner en hilo aparte
    threading.Thread(target=scanner.live_scan, daemon=True).start()

    # Ejecutar Market Maker real
    mm = MarketMaker(scanner)
    mm.run()