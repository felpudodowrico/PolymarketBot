# mapa_mercados.py
from scanner import EventScannerGamma
import config

if __name__ == "__main__":
    scanner = EventScannerGamma(
        min_liquidity=0,    # ignoramos filtros para ver todos
        min_volume=0,
        categories=None,
        multi_outcome=False, # mostrar todos
        display_delay=0,
        fetch_delay=0,
        max_snapshots=None
    )

    events = scanner.fetch_events()  # trae eventos
    total_markets = 0
    multi_outcome_markets = 0

    print("\n=== Mapa de mercados activos ===\n")
    for e in events:
        category = e.get("tags", [""])[0] if e.get("tags") else ""
        for m in e.get("markets", []):
            outcomes = scanner.parse_outcomes(m)
            total_markets += 1
            outcome_count = len(outcomes)
            if outcome_count > 2:
                multi_outcome_markets += 1

            print(f"ID: {m.get('id')}, Question: {m.get('question')}")
            print(f"Outcomes: {outcome_count}, Liquidity: {m.get('liquidityNum')}, Volume: {m.get('volume')}, Category: {category}")
            print("-"*60)

    print(f"\nTotal mercados: {total_markets}")
    print(f"Mercados multi-outcome (>2 outcomes): {multi_outcome_markets}")