"""
Main entry point for Polymarket Pricer.

Usage:
    python -m src.main spot ttl_seconds volatility
    
Examples:
    python -m src.main 105000 300 0.60
    python -m src.main 105000 300 0.60 --compare
    python -m src.main 105000 300 0.60 --greeks
"""
import argparse
import math
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import (
    BinaryOptionPricer,
    BinomialPricer,
    compare_models,
    GreeksAnalyzer
)


def format_seconds(seconds: int) -> str:
    """Format seconds into human-readable time."""
    if seconds >= 60:
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}m {secs}s"
    return f"{seconds}s"


def main():
    parser = argparse.ArgumentParser(
        description="Polymarket Binary Option Theoretical Pricing"
    )
    parser.add_argument(
        "spot",
        type=float,
        help="Current BTC spot price (e.g., 105000)"
    )
    parser.add_argument(
        "ttl",
        type=int,
        help="Time to expiry in seconds (e.g., 300 for 5 minutes)"
    )
    parser.add_argument(
        "volatility",
        type=float,
        default=0.60,
        nargs="?",
        help="Annualized volatility (default: 0.60 = 60%%)"
    )
    parser.add_argument(
        "--compare", "-c",
        action="store_true",
        help="Compare Black-Scholes vs Binomial"
    )
    parser.add_argument(
        "--greeks", "-g",
        action="store_true",
        help="Show detailed Greeks analysis"
    )
    parser.add_argument(
        "--strike", "-k",
        type=float,
        default=None,
        help="Strike price (default: same as spot)"
    )

    args = parser.parse_args()

    spot = args.spot
    ttl = args.ttl
    sigma = args.volatility
    strike = args.strike if args.strike is not None else spot

    print()
    print("=" * 60)
    print("  Polymarket Binary Option Theoretical Pricer")
    print("=" * 60)
    print()
    print(f"  Spot Price:    ${spot:,.2f}")
    print(f"  Strike Price:  ${strike:,.2f}")
    print(f"  Time to Expiry: {format_seconds(ttl)} ({ttl} seconds)")
    print(f"  Volatility:    {sigma*100:.1f}%")
    print()

    if args.compare:
        print("-" * 60)
        print("  Model Comparison")
        print("-" * 60)

        comparison = compare_models(spot, strike, ttl, sigma)

        bs = comparison['black_scholes']
        bn = comparison['binomial']

        print()
        print(f"  {'Model':<20} {'YES (Up)':<12} {'NO (Down)':<12}")
        print(f"  {'-'*44}")
        print(f"  {'Black-Scholes':<20} {bs['up_price']:<12.4f} {bs['down_price']:<12.4f}")
        print(f"  {'Binomial':<20} {bn['up_price']:<12.4f} {bn['down_price']:<12.4f}")
        print()
        print(f"  Difference: {comparison['difference']['up_price']:.6f}")
        print()

        print(f"  Zone: {bs['zone']}")
        print()

    elif args.greeks:
        print("-" * 60)
        print("  Greeks Analysis (Black-Scholes)")
        print("-" * 60)

        analyzer = GreeksAnalyzer()
        risk = analyzer.risk_profile(spot, strike, ttl, sigma)

        print()
        print(f"  Zone:            {risk['zone']}")
        print(f"  Moneyness:       {risk['moneyness']}")
        print(f"  Distance to K:   {risk['distance_to_strike_pct']:.2f}%")
        print()
        print(f"  YES Price:       {risk['up_price']:.4f}")
        print(f"  NO Price:        {risk['down_price']:.4f}")
        print()
        print(f"  Delta:           {risk['delta']:.6f}")
        print(f"  Gamma:           {risk['gamma']:.6f}")
        print(f"  Theta/min:       {risk['theta_per_minute']:.6f}")
        print(f"  Vega:            {risk['vega']:.6f}")
        print()
        print(f"  Recommendation:  {risk['recommendation']}")
        print()

    else:
        print("-" * 60)
        print("  Theoretical Prices")
        print("-" * 60)

        bs = BinaryOptionPricer(default_volatility=sigma)
        bs_result = bs.price(spot, strike, ttl, sigma)

        print()
        print(f"  {'Model':<20} {'YES (Up)':<12} {'NO (Down)':<12}")
        print(f"  {'-'*44}")
        print(f"  {'Black-Scholes':<20} {bs_result.up_price:<12.4f} {bs_result.down_price:<12.4f}")
        print()

        print(f"  Zone: {bs_result.zone}")
        print()


if __name__ == "__main__":
    main()
