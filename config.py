# config.py

# Configuración del scanner
LIMIT_EVENTS = 500          # Número máximo de eventos a descargar. Máximo permitido por Gamma: 500
MIN_LIQUIDITY = 10         # Liquidez mínima por mercado
MIN_VOLUME = 10          # Volumen mínimo por mercado
CATEGORIES = None          # Lista de categorías a filtrar, None para todas
MULTI_OUTCOME = True      # Mostrar solo mercados con más de 2 outcomes
DISPLAY_DELAY = 1          # Segundos entre mostrar mercados
FETCH_DELAY = 2            # Segundos si no hay mercados aptos
MAX_SNAPSHOTS = 500        # Histórico máximo por mercado. None = historial ilimitado