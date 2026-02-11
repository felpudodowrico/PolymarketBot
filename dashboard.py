# dashboard.py
import time
from datetime import datetime

def display_market_live(market, parse_outcomes_fn):
    outcomes = parse_outcomes_fn(market)
    print("=== Mercado Polymarket multi-outcome encontrado ===")
    print(f"ID: {market.get('id')}")
    print(f"Pregunta: {market.get('question')}")
    print(f"Liquidity: {market.get('liquidityNum')}")
    print(f"Volume: {market.get('volume')}")
    print(f"Outcomes: {[o.get('outcome', 'N/A') for o in outcomes]}")
    print(f"Best Bid: {market.get('bestBid')}")
    print(f"Best Ask: {market.get('bestAsk')}")
    #if "clobTokenIds" in market:
        #print(f"Token IDs: {market['clobTokenIds']}")
    #print("------------------------\n")

def print_scan_stats(stats, idx, total_filtered):
    uptime = int(time.time() - stats["start_time"])

    print("\n" + "=" * 60)
    print("📊 ESTADÍSTICAS DEL SCANNER")
    print("=" * 60)
    print(f"⏱️  Uptime: {uptime}s")
    print(f"🕒 Ahora: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"🔁 Loops: {stats['loops']}")
    print(f"⬇️ Eventos descargados (último fetch): {stats['total_events_downloaded']}")
    print(f"✅ Mercados tras filtro: {total_filtered}")
    print(f"📺 Mercados mostrados: {stats['markets_displayed']}")
    print(f"🧠 Mercados únicos mostrados: {len(stats['unique_markets_displayed'])}")
    print(f"➡️ Posición actual: {idx}/{total_filtered}")
    print("=" * 60 + "\n")