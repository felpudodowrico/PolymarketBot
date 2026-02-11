# mapa_mercados_filtrado.py
from scanner import EventScannerGamma
import config

if __name__ == "__main__":
    scanner = EventScannerGamma(
        min_liquidity=0,       # filtraremos manualmente abajo
        min_volume=0,
        categories=None,
        multi_outcome=False,
        display_delay=0,
        fetch_delay=0,
        max_snapshots=None
    )

    # Parámetros de filtrado
    MIN_LIQUIDITY = config.MIN_LIQUIDITY
    MIN_VOLUME = config.MIN_VOLUME
    CATEGORIES = config.CATEGORIES
    MULTI_OUTCOME = True  # solo multi-outcome

    events = scanner.fetch_events()
    filtered_markets = []

    for e in events:
        category = e.get("tags", [""])[0] if e.get("tags") else ""
        if CATEGORIES and category.lower() not in [c.lower() for c in CATEGORIES]:
            continue

        for m in e.get("markets", []):
            outcomes = scanner.parse_outcomes(m)
            liquidity = float(m.get("liquidityNum", 0))
            volume = float(m.get("volume", 0))

            if MULTI_OUTCOME and len(outcomes) <= 2:
                continue
            if liquidity < MIN_LIQUIDITY or volume < MIN_VOLUME:
                continue

            filtered_markets.append({
                "id": m.get("id"),
                "question": m.get("question"),
                "outcomes": len(outcomes),
                "liquidity": liquidity,
                "volume": volume,
                "category": category
            })

    print("\n=== Mercados filtrados ===\n")
    for m in filtered_markets:
        print(f"ID: {m['id']}, Question: {m['question']}")
        print(f"Outcomes: {m['outcomes']}, Liquidity: {m['liquidity']}, Volume: {m['volume']}, Category: {m['category']}")
        print("-"*60)

    print(f"\nTotal mercados filtrados multi-outcome: {len(filtered_markets)}")