"""
Real-time monitoring module for Polymarket theoretical pricing.

Connects to:
- Binance WebSocket for real-time BTC price
- Polymarket API for current market prices
- Calculates theoretical price vs actual price
- Generates trading signals in simulation mode
"""
import asyncio
import json
import math
import time
import websockets
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional
import requests

from .models import BinaryOptionPricer


@dataclass
class MarketSnapshot:
    """Snapshot of a market at a point in time."""
    timestamp: str
    btc_spot: float
    market_id: str
    question: str
    expiry: str
    actual_yes: float
    actual_no: float
    theoretical_yes: float
    theoretical_no: float
    deviation_yes: float  # actual - theoretical
    deviation_no: float
    signal: str  # BUY_YES, BUY_NO, SELL_YES, SELL_NO, NEUTRAL
    signal_strength: float  # 0-1


class PricingMonitor:
    """
    Real-time pricing monitor for Polymarket 15-minute BTC markets.
    """

    def __init__(
        self,
        volatility: float = 0.60,
        deviation_threshold: float = 0.05,
        signal_threshold: float = 0.08,
        simulation: bool = True
    ):
        """
        Initialize monitor.

        Args:
            volatility: Annualized volatility for theoretical pricing
            deviation_threshold: Deviation to trigger signal (5%)
            signal_threshold: Strong signal threshold (8%)
            simulation: Run in simulation mode (paper trading)
        """
        self.volatility = volatility
        self.deviation_threshold = deviation_threshold
        self.signal_threshold = signal_threshold
        self.simulation = simulation
        self.pricer = BinaryOptionPricer(default_volatility=volatility)

        self.current_btc_price: float = 0
        self.markets: dict = {}
        self.signals: list = []
        self.positions: dict = {}  # simulation mode positions

        # Stats
        self.total_signals = 0
        self.correct_signals = 0

    def get_active_markets(self) -> list:
        """Fetch active BTC Up/Down markets from Polymarket via CLOB API."""
        try:
            # Try CLOB markets endpoint first
            resp = requests.get(
                "https://clob.polymarket.com/markets",
                params={"limit": 100},
                timeout=10
            )
            if resp.status_code != 200:
                # Fallback to Gamma
                resp = requests.get(
                    "https://gamma-api.polymarket.com/markets",
                    params={"closed": "false", "limit": 50},
                    timeout=10
                )

            data = resp.json()
            markets = data.get('data', data.get('markets', [])) if isinstance(data, dict) else data

            # Filter for BTC up/down 15min markets
            btc_markets = []
            for m in markets:
                question = str(m.get('question', '')).lower()
                slug = str(m.get('slug', '')).lower()

                # Match BTC up/down 15min markets
                if ('btc' in question or 'btc' in slug or
                    'bitcoin' in question or 'bitcoin' in slug):
                    if ('up' in question or 'down' in question or
                        'up' in slug or 'down' in slug):

                        # Get price - try different field names
                        yes_price = (
                            float(m.get('yesPrice', 0)) or
                            float(m.get('yes_price', 0)) or
                            float(m.get('price', 0.5)) or
                            0.5
                        )
                        no_price = (
                            float(m.get('noPrice', 0)) or
                            float(m.get('no_price', 0)) or
                            float(1 - yes_price) or
                            0.5
                        )

                        if yes_price == 0:
                            yes_price = 0.5
                            no_price = 0.5

                        btc_markets.append({
                            'id': m.get('id', m.get('marketId', '')),
                            'question': m.get('question', slug),
                            'end_date': m.get('endDate', m.get('end_date', '')),
                            'yes_odds': yes_price,
                            'no_odds': no_price,
                            'liquidity': float(m.get('liquidity', 0)),
                            'volume': float(m.get('volume', m.get('vol', 0))),
                            'slug': slug,
                        })

            # Sort by volume descending
            btc_markets.sort(key=lambda x: x['volume'], reverse=True)
            return btc_markets

        except Exception as e:
            print(f"Error fetching markets: {e}")
            return []

    def calculate_theoretical_price(
        self,
        spot: float,
        ttl_seconds: float
    ) -> tuple:
        """Calculate theoretical YES/NO prices."""
        if spot <= 0 or ttl_seconds <= 0:
            return 0.5, 0.5

        result = self.pricer.price(spot, spot, ttl_seconds, self.volatility)
        return result.up_price, result.down_price

    def calculate_ttl(self, end_date: str) -> float:
        """Calculate seconds until market expiry."""
        try:
            # Parse ISO format date
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            now = datetime.now(end_dt.tzinfo)
            delta = (end_dt - now).total_seconds()
            return max(0, delta)
        except:
            return 0

    def generate_signal(
        self,
        actual_yes: float,
        actual_no: float,
        theoretical_yes: float,
        theoretical_no: float
    ) -> tuple:
        """
        Generate trading signal based on deviation from theoretical price.

        Returns:
            (signal_type, strength)
        """
        dev_yes = actual_yes - theoretical_yes
        dev_no = actual_no - theoretical_no

        # Normalize - if YES is overvalued, NO is undervalued (and vice versa)
        if dev_yes > self.deviation_threshold:
            # YES is expensive relative to theory - could mean:
            # 1. Market thinks UP is more likely (direction signal)
            # 2. Just FOMO overpricing (mean reversion opportunity)
            if dev_yes > self.signal_threshold:
                return ("STRONG_BUY_NO", dev_yes)  # NO is cheap
            else:
                return ("BUY_NO", dev_yes)
        elif dev_no > self.deviation_threshold:
            if dev_no > self.signal_threshold:
                return ("STRONG_BUY_YES", dev_no)
            else:
                return ("BUY_YES", dev_no)
        elif abs(dev_yes) < 0.02:
            return ("NEUTRAL", abs(dev_yes))
        else:
            # Small deviation, no strong signal
            return ("NEUTRAL", abs(dev_yes))

    async def connect_binance(self, uri: str = "wss://stream.binance.com:9443/ws/btcusdt@trade") -> None:
        """Connect to Binance WebSocket for BTC price."""
        while True:
            try:
                async with websockets.connect(uri, ping_interval=30) as ws:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Connected to Binance WebSocket")
                    async for msg in ws:
                        try:
                            data = json.loads(msg)
                            if data.get('e') == 'trade':
                                self.current_btc_price = float(data['p'])
                        except:
                            pass
            except Exception as e:
                print(f"Binance WS error: {e}, reconnecting in 5s...")
                await asyncio.sleep(5)

    async def run_market_monitor(self) -> None:
        """Monitor markets and generate signals."""
        while True:
            try:
                markets = self.get_active_markets()
                if not markets:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] No active markets found")
                    await asyncio.sleep(30)
                    continue

                print(f"\n{'='*80}")
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Monitoring {len(markets)} BTC markets | BTC: ${self.current_btc_price:,.2f}")
                print(f"{'='*80}")

                for m in markets[:5]:  # Top 5 by volume
                    ttl = self.calculate_ttl(m['end_date'])
                    if ttl <= 0:
                        continue

                    theo_yes, theo_no = self.calculate_theoretical_price(
                        self.current_btc_price, ttl
                    )

                    actual_yes = m['yes_odds']
                    actual_no = m['no_odds']

                    dev_yes = actual_yes - theo_yes
                    dev_no = actual_no - theo_no

                    signal, strength = self.generate_signal(
                        actual_yes, actual_no, theo_yes, theo_no
                    )

                    # Format expiry
                    try:
                        end_dt = datetime.fromisoformat(m['end_date'].replace('Z', '+00:00'))
                        expiry_str = end_dt.strftime('%H:%M')
                    except:
                        expiry_str = m['end_date'][:10]

                    # Status emoji
                    if signal.startswith('STRONG_'):
                        status = "🔥"
                    elif signal.startswith('BUY_'):
                        status = "📍"
                    else:
                        status = "⚪"

                    print(f"\n{status} {m['question'][:60]}")
                    print(f"   Expiry: {expiry_str} ({ttl/60:.1f}min) | Liq: ${m['liquidity']:,.0f}")
                    print(f"   Actual:  YES={actual_yes:.3f} NO={actual_no:.3f}")
                    print(f"   Theory:  YES={theo_yes:.3f} NO={theo_no:.3f}")
                    print(f"   Dev:     YES={dev_yes:+.3f} NO={dev_no:+.3f}")
                    print(f"   Signal:  {signal} ({strength:.3f})")

                    # Log signal
                    snapshot = MarketSnapshot(
                        timestamp=datetime.now().isoformat(),
                        btc_spot=self.current_btc_price,
                        market_id=m['id'],
                        question=m['question'],
                        expiry=expiry_str,
                        actual_yes=actual_yes,
                        actual_no=actual_no,
                        theoretical_yes=theo_yes,
                        theoretical_no=theo_no,
                        deviation_yes=dev_yes,
                        deviation_no=dev_no,
                        signal=signal,
                        signal_strength=strength
                    )
                    self.signals.append(snapshot)

                    if signal != "NEUTRAL":
                        self.total_signals += 1

                await asyncio.sleep(30)  # Check every 30 seconds

            except Exception as e:
                print(f"Monitor error: {e}")
                await asyncio.sleep(10)

    async def run(self) -> None:
        """Run both Binance connection and market monitor."""
        print("Starting Polymarket Pricing Monitor...")
        print(f"  Volatility: {self.volatility*100:.0f}%")
        print(f"  Deviation threshold: {self.deviation_threshold*100:.0f}%")
        print(f"  Signal threshold: {self.signal_threshold*100:.0f}%")
        print(f"  Mode: {'SIMULATION' if self.simulation else 'LIVE'}")
        print()

        await asyncio.gather(
            self.connect_binance(),
            self.run_market_monitor()
        )


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Polymarket Pricing Monitor")
    parser.add_argument("--vol", type=float, default=0.60, help="Volatility (default: 0.60)")
    parser.add_argument("--dev", type=float, default=0.05, help="Deviation threshold (default: 0.05)")
    parser.add_argument("--sig", type=float, default=0.08, help="Signal threshold (default: 0.08)")
    parser.add_argument("--live", action="store_true", help="Run in live mode (not simulation)")
    args = parser.parse_args()

    monitor = PricingMonitor(
        volatility=args.vol,
        deviation_threshold=args.dev,
        signal_threshold=args.sig,
        simulation=not args.live
    )

    try:
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        print("\nMonitor stopped.")
        if monitor.signals:
            print(f"\nSummary: {monitor.total_signals} signals generated")


if __name__ == "__main__":
    main()
