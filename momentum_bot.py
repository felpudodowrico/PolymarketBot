# momentum_bot.py
# Momentum Micro bot para Polymarket CLOB (paper/live)

import time
import math
import threading
from dataclasses import dataclass
from typing import Dict, Optional, List, Tuple

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

# =========================
# CONFIG
# =========================


@dataclass
class MomentumConfig:
    # Ventana para momentum (segundos)
    lookback_sec: float = 2.5

    # Mínimo movimiento para entrar (ej 0.004 = 0.4%)
    min_move: float = 0.004

    # Confirmación imbalance
    min_imbalance: float = 0.58

    # Spread máximo para operar
    max_spread: float = 0.020

    # Liquidez mínima real del mercado
    min_liquidity: float = 1000.0

    # Cooldown por mercado (para no spamear el mismo)
    market_cooldown_sec: float = 12.0

    # Tamaño por trade (euros/dólares) aprox en USDC
    stake_usd: float = 8.0

    # TP/SL en términos de precio (prob)
    take_profit: float = 0.006     # +0.6%
    stop_loss: float = 0.007       # -0.7%

    # Si no sales en X segundos, sales por market
    max_hold_sec: float = 25.0

    # Slippage interno: entramos pegados al bid/ask
    # (para evitar comprar en el ask cuando el spread está abierto)
    entry_mode: str = "maker"  # "maker" o "taker-lite"

    # Live trading
    live: bool = False

    # Verbose logs
    debug: bool = True


# =========================
# MOMENTUM BOT
# =========================

class MomentumMicroBot:
    """
    Bot que usa scanner.history para detectar momentum micro.
    Entra SOLO con LIMIT.
    Maneja TP/SL/timeout.
    """

    def __init__(self, scanner, config: MomentumConfig):
        self.scanner = scanner
        self.cfg = config

        self.stop_event = threading.Event()

        # Estado por mercado
        self.last_trade_ts: Dict[str, float] = {}

        # Posición actual (modo simple: 1 posición a la vez)
        self.position = None  # dict con info

        # Para live trading (placeholder)
        self.clob = None

        if self.cfg.live:
            self._init_clob()

    # ------------- LIVE SETUP -------------
    def _init_clob(self):
        """
        Inicializa cliente de CLOB.
        Esto depende de tu setup real (API key / wallet).
        Te dejo el esqueleto estándar.
        """
        try:
            # pip install py-clob-client
            from py_clob_client.client import ClobClient
            from py_clob_client.constants import POLYGON

            # OJO:
            # Necesitas host, chain_id, private_key, y a veces api_key/secret/passphrase
            # Esto NO lo puedo inventar por ti.
            #
            # Ejemplo típico:
            # host = "https://clob.polymarket.com"
            # chain_id = POLYGON
            # private_key = "0x...."
            #
            # client = ClobClient(host, chain_id=chain_id, private_key=private_key)
            # client.set_api_creds(api_key, api_secret, passphrase)
            #
            # self.clob = client

            raise RuntimeError(
                "LIVE mode activado pero falta configurar credenciales en _init_clob()."
            )

        except Exception as e:
            raise RuntimeError(f"No se pudo inicializar CLOB client: {e}")

    # ------------- UTILS -------------
    def _log(self, msg: str):
        if self.cfg.debug:
            print(f"[MomentumBot] {msg}")

    def stop(self):
        self.stop_event.set()

    # ------------- HISTORY HELPERS -------------
    def _get_recent_snaps(self, market_id: str, now: float) -> List[Dict]:
        """
        Devuelve snaps en ventana lookback_sec.
        """
        hist = self.scanner.history.get(market_id) or []
        if not hist:
            return []

        cutoff = now - self.cfg.lookback_sec
        # hist ya viene ordenado por ts
        out = []
        for s in reversed(hist):
            if s.get("ts", 0) < cutoff:
                break
            out.append(s)
        out.reverse()
        return out

    def _momentum_signal(self, snaps: List[Dict]) -> Optional[Dict]:
        """
        Construye señal:
        - dirección (YES o NO)
        - delta mid
        - confirmación imbalance
        """
        if len(snaps) < 4:
            return None

        s0 = snaps[0]
        s1 = snaps[-1]

        # Usamos mid del orderbook (más real que gamma)
        mid_yes_0 = s0.get("mid_yes")
        mid_yes_1 = s1.get("mid_yes")
        mid_no_0 = s0.get("mid_no")
        mid_no_1 = s1.get("mid_no")

        if mid_yes_0 is None or mid_yes_1 is None:
            return None
        if mid_no_0 is None or mid_no_1 is None:
            return None

        d_yes = mid_yes_1 - mid_yes_0
        d_no = mid_no_1 - mid_no_0

        # Confirmaciones (último snapshot)
        imb_yes = s1.get("imbalance_yes")
        imb_no = s1.get("imbalance_no")

        spread_yes = s1.get("spread_yes")
        spread_no = s1.get("spread_no")

        if spread_yes is None or spread_no is None:
            return None

        # No operamos spreads grandes (muerte por fills)
        if spread_yes > self.cfg.max_spread or spread_no > self.cfg.max_spread:
            return None

        # Señal: si YES sube con imbalance fuerte, long YES
        # Si YES baja, es equivalente a long NO.
        if abs(d_yes) < self.cfg.min_move:
            return None

        # Dirección basada en YES
        if d_yes > 0:
            # Confirmación: imbalance yes comprador
            if imb_yes is None or imb_yes < self.cfg.min_imbalance:
                return None
            direction = "YES"
            move = d_yes
        else:
            # Confirmación: imbalance no comprador
            if imb_no is None or imb_no < self.cfg.min_imbalance:
                return None
            direction = "NO"
            move = -d_yes  # magnitud positiva

        return {
            "direction": direction,
            "move": move,
            "last": s1,
            "first": s0,
        }

    # ------------- EXECUTION -------------
    def _calc_size_shares(self, price: float) -> float:
        """
        stake_usd / price aprox.
        """
        if price <= 0:
            return 0.0
        return self.cfg.stake_usd / price

    def _place_order_paper(self, token_id: str, side: str, price: float, size: float) -> str:
        """
        Simula orden.
        """
        oid = f"paper_{int(time.time()*1000)}"
        self._log(f"[PAPER] {side} token={token_id} price={price:.4f} size={size:.2f} oid={oid}")
        return oid

    def _place_order_live(self, token_id: str, side: str, price: float, size: float) -> str:
        """
        LIVE: coloca orden LIMIT en CLOB.
        """
        if not self.clob:
            raise RuntimeError("CLOB client no inicializado.")

        # Estructura típica en py-clob-client:
        #
        # from py_clob_client.clob_types import OrderArgs, OrderType, Side
        #
        # args = OrderArgs(
        #   price=price,
        #   size=size,
        #   side=Side.BUY,
        #   token_id=token_id,
        #   order_type=OrderType.GTC
        # )
        # signed_order = self.clob.create_order(args)
        # resp = self.clob.post_order(signed_order)
        # return resp["orderID"]

        raise RuntimeError("LIVE order placement no implementado: configura py-clob-client aquí.")

    def _place_order(self, token_id: str, side: str, price: float, size: float) -> str:
        if self.cfg.live:
            return self._place_order_live(token_id, side, price, size)
        return self._place_order_paper(token_id, side, price, size)

    # ------------- POSITION MGMT -------------
    def _open_position(self, market_id: str, direction: str, snap: Dict):
        """
        Abre una posición:
        - direction YES => buy YES token
        - direction NO  => buy NO token
        """
        yes_tid = snap.get("yes_token_id")
        no_tid = snap.get("no_token_id")

        if not yes_tid or not no_tid:
            return

        if direction == "YES":
            token_id = yes_tid
            bid = snap.get("bestBid_yes")
            ask = snap.get("bestAsk_yes")
        else:
            token_id = no_tid
            bid = snap.get("bestBid_no")
            ask = snap.get("bestAsk_no")

        if bid is None or ask is None:
            return

        # Entry price
        # maker => ponemos orden en bid (esperamos fill)
        # taker-lite => ponemos un pelín mejor que bid (pero sin ir al ask)
        if self.cfg.entry_mode == "maker":
            entry_price = bid
        else:
            entry_price = min(ask, bid + 0.001)

        entry_price = clamp(entry_price, 0.01, 0.99)
        size = self._calc_size_shares(entry_price)
        if size <= 0:
            return

        oid = self._place_order(token_id, "BUY", entry_price, size)

        self.position = {
            "market_id": market_id,
            "direction": direction,
            "token_id": token_id,
            "entry_price": entry_price,
            "size": size,
            "entry_ts": time.time(),
            "order_id": oid,
            "status": "OPEN",
        }

        self.last_trade_ts[market_id] = time.time()

        self._log(
            f"OPEN {direction} market={market_id} entry={entry_price:.4f} size={size:.2f}"
        )

    def _should_exit(self, snap: Dict) -> Optional[str]:
        """
        Decide salida por TP/SL/timeout.
        """
        if not self.position:
            return None

        direction = self.position["direction"]
        entry = self.position["entry_price"]
        age = time.time() - self.position["entry_ts"]

        # Mark price: usamos mid del token que compramos
        if direction == "YES":
            mid = snap.get("mid_yes")
        else:
            mid = snap.get("mid_no")

        if mid is None:
            return None

        pnl = mid - entry  # en prob

        if pnl >= self.cfg.take_profit:
            return "TP"
        if pnl <= -self.cfg.stop_loss:
            return "SL"
        if age >= self.cfg.max_hold_sec:
            return "TIME"
        return None

    def _close_position(self, snap: Dict, reason: str):
        """
        Cierra posición vendiendo el token comprado.
        """
        if not self.position:
            return

        direction = self.position["direction"]
        token_id = self.position["token_id"]
        size = self.position["size"]

        if direction == "YES":
            bid = snap.get("bestBid_yes")
            ask = snap.get("bestAsk_yes")
        else:
            bid = snap.get("bestBid_no")
            ask = snap.get("bestAsk_no")

        if bid is None or ask is None:
            return

        # Salimos agresivo pero sin regalar demasiado:
        exit_price = bid  # vender al bid
        exit_price = clamp(exit_price, 0.01, 0.99)

        oid = self._place_order(token_id, "SELL", exit_price, size)

        entry = self.position["entry_price"]
        age = time.time() - self.position["entry_ts"]

        # Estimación pnl
        if direction == "YES":
            mid = snap.get("mid_yes")
        else:
            mid = snap.get("mid_no")
        pnl = (mid - entry) if mid is not None else 0.0

        self._log(
            f"CLOSE {direction} reason={reason} exit={exit_price:.4f} pnl≈{pnl:+.4f} age={age:.1f}s oid={oid}"
        )

        self.position = None

    # ------------- MAIN LOOP -------------
    def run(self):
        """
        Loop principal:
        - si no hay posición => buscar señales
        - si hay posición => gestionar salida
        """
        self._log("Bot iniciado.")
        while not self.stop_event.is_set():
            time.sleep(0.20)

            now = time.time()

            # Necesitamos mercados trackeados
            with self.scanner.lock:
                market_ids = list(self.scanner.tracked_market_ids)

            if not market_ids:
                continue

            # Si hay posición, solo gestionamos esa
            if self.position:
                mid = self.position["market_id"]
                snaps = self._get_recent_snaps(mid, now)
                if not snaps:
                    continue
                last = snaps[-1]
                reason = self._should_exit(last)
                if reason:
                    self._close_position(last, reason)
                continue

            # Buscar señal entre markets
            for market_id in market_ids:
                # Cooldown
                last_t = self.last_trade_ts.get(market_id, 0.0)
                if (now - last_t) < self.cfg.market_cooldown_sec:
                    continue

                snaps = self._get_recent_snaps(market_id, now)
                if not snaps:
                    continue

                last = snaps[-1]
                liq = last.get("liquidity") or 0.0
                if liq < self.cfg.min_liquidity:
                    continue

                sig = self._momentum_signal(snaps)
                if not sig:
                    continue

                direction = sig["direction"]
                move = sig["move"]

                self._log(
                    f"SIGNAL market={market_id} dir={direction} move={move:.4f} spreadY={last.get('spread_yes'):.4f}"
                )

                self._open_position(market_id, direction, last)

                # Solo 1 posición
                break

        self._log("Bot detenido.")
        
        
# =========================
# STANDALONE RUNNER
# =========================

if __name__ == "__main__":
    import signal
    import threading

    from scanner import EventScannerGamma

    from config import (
        MOM_LOOKBACK_SEC,
        MOM_MIN_MOVE,
        MOM_MIN_IMBALANCE,
        MOM_MAX_SPREAD,
        MOM_MIN_LIQUIDITY,
        MOM_MARKET_COOLDOWN_SEC,
        MOM_STAKE_USD,
        MOM_TAKE_PROFIT,
        MOM_STOP_LOSS,
        MOM_MAX_HOLD_SEC,
        MOM_ENTRY_MODE,
        MOM_LIVE,
        MOM_DEBUG,
    )

    scanner = EventScannerGamma()

    cfg = MomentumConfig(
        lookback_sec=MOM_LOOKBACK_SEC,
        min_move=MOM_MIN_MOVE,
        min_imbalance=MOM_MIN_IMBALANCE,
        max_spread=MOM_MAX_SPREAD,
        min_liquidity=MOM_MIN_LIQUIDITY,
        market_cooldown_sec=MOM_MARKET_COOLDOWN_SEC,
        stake_usd=MOM_STAKE_USD,
        take_profit=MOM_TAKE_PROFIT,
        stop_loss=MOM_STOP_LOSS,
        max_hold_sec=MOM_MAX_HOLD_SEC,
        entry_mode=MOM_ENTRY_MODE,
        live=MOM_LIVE,
        debug=MOM_DEBUG,
    )

    bot = MomentumMicroBot(scanner, cfg)

    scan_thread = threading.Thread(target=scanner.live_scan, daemon=True)
    bot_thread = threading.Thread(target=bot.run, daemon=True)

    scan_thread.start()
    bot_thread.start()

    def signal_handler(sig, frame):
        print("\n[MomentumBot] Deteniendo...")
        bot.stop()
        scanner.stop()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, signal_handler)

    while True:
        time.sleep(1)

