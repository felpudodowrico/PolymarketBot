# run.py
from scanner import EventScannerGamma
import config

if __name__ == "__main__":
    scanner = EventScannerGamma(
        min_liquidity=config.MIN_LIQUIDITY,
        min_volume=config.MIN_VOLUME,
        categories=config.CATEGORIES,
        multi_outcome=config.MULTI_OUTCOME,
        display_delay=config.DISPLAY_DELAY,
        fetch_delay=config.FETCH_DELAY,
        max_snapshots=config.MAX_SNAPSHOTS
    )

    print("Escaneando mercados activos desde Gamma /events...")
    scanner.live_scan()