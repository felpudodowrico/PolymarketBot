# config.py

# Configuración del scanner
MIN_LIQUIDITY = 0         # Liquidez mínima por mercado
MIN_VOLUME = 0          # Volumen mínimo por mercado
CATEGORIES = None          # Lista de categorías a filtrar, None para todas
MULTI_OUTCOME = False      # Mostrar solo mercados con más de 2 outcomes
DISPLAY_DELAY = 0.5         # Segundos entre mostrar mercados
FETCH_DELAY = 0.5            # Segundos si no hay mercados aptos
MAX_SNAPSHOTS = 1000        # Histórico máximo por mercado. None = historial ilimitado
