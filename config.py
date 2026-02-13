# config.py

# Configuración del scanner
MIN_LIQUIDITY = 100000         # Liquidez mínima por mercado
MIN_VOLUME = 100000       # Volumen mínimo por mercado
CATEGORIES = None          # Lista de categorías a filtrar, None para todas
MULTI_OUTCOME = False      # Mostrar solo mercados con más de 2 outcomes
DISPLAY_DELAY = 1         # Segundos entre mostrar mercados
MAX_SPREAD_FILTER = 0.99   # Filtro spread arbitraje

# =========================
# MOMENTUM MICRO BOT CONFIG
# =========================

# Ventana de análisis (segundos)
MOM_LOOKBACK_SEC = 2.5

# Movimiento mínimo para considerar momentum (0.004 = 0.4%)
MOM_MIN_MOVE = 0.004

# Imbalance mínimo para confirmar (0.58 = 58% del size en bid)
MOM_MIN_IMBALANCE = 0.58

# Spread máximo permitido para operar (si no, te revientan con fills malos)
MOM_MAX_SPREAD = 0.020

# Liquidez mínima del mercado para operar
MOM_MIN_LIQUIDITY = 1000.0

# Cooldown por mercado (segundos) para no spamear el mismo
MOM_MARKET_COOLDOWN_SEC = 12.0

# Tamaño por trade en USDC (o equivalente)
MOM_STAKE_USD = 8.0

# Take profit / Stop loss en unidades de prob (0.006 = +0.6%)
MOM_TAKE_PROFIT = 0.006
MOM_STOP_LOSS = 0.007

# Si no se cierra en X segundos, se cierra por timeout
MOM_MAX_HOLD_SEC = 25.0

# Modo de entrada:
# "maker" = bid
# "taker-lite" = bid + 0.001 (sin cruzar al ask si puede evitarse)
MOM_ENTRY_MODE = "maker"

# Paper / Live
MOM_LIVE = False

# Logs
MOM_DEBUG = True
