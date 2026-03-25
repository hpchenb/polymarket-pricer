# Polymarket Pricer

Binary options theoretical pricing model for Polymarket 15-minute BTC markets.

## Models

### Black-Scholes Model (`black_scholes.py`)
Continuous-time analytical solution for binary (digital) options.

### Binomial Model (`binomial.py`)
Discrete-time CRR (Cox-Ross-Rubinstein) model for binary options.

## Quick Start

```python
from src.models import BinaryOptionPricer, BinomialPricer

# Black-Scholes
bs = BinaryOptionPricer(default_volatility=0.60)
result = bs.price(spot=105000, strike=105000, ttl_seconds=300)
print(f"Theoretical YES price: {result.up_price:.4f}")

# Binomial
binomial = BinomialPricer(default_volatility=0.60)
result = binomial.price(spot=105000, strike=105000, ttl_seconds=300)
print(f"Theoretical YES price: {result.up_price:.4f}")

# Compare both
from src.models import compare_models
comparison = compare_models(spot=105000, strike=105000, ttl_seconds=300)
print(f"BS vs Binomial difference: {comparison['difference']['up_price']:.6f}")
```

## Key Concepts

### Greeks
- **Delta**: Price sensitivity to spot price change
- **Gamma**: Rate of change of Delta
- **Theta**: Time decay (per second)
- **Vega**: Volatility sensitivity

### Pricing Zones
| Zone | Description |
|------|-------------|
| `linear_decay` | T > ~3min, theta decay is linear |
| `lock_in` | T < ~1min, price locks in near current value |
| `transition` | Between the two regimes |

## Installation

```bash
pip install -r requirements.txt
```

## Theory

Polymarket 15-minute BTC markets are binary options with:
- **Up** = Binary Call (pays $1 if BTC price >= strike at expiry)
- **Down** = Binary Put (pays $1 if BTC price < strike at expiry)

The strike is effectively the BTC price at market creation time.

### Pricing Parameters
- **Spot (S)**: Current BTC price
- **Strike (K)**: Market creation price
- **Time to Expiry (T)**: Seconds remaining
- **Volatility (σ)**: Annualized, typically 50-80% for crypto

### Expected Behavior
1. **Near Creation**: Price ≈ 0.50 (coin flip)
2. **As Time Passes**: Price should decay toward 0.50 via theta
3. **FOMO Effect**: Real market often pushes price above theoretical value
4. **Last Minute**: Price locks near current state with small adjustments

## Strategy Implications

When `Actual Price > Theoretical Price`:
- The option is "expensive" relative to fair value
- Market may be overvaluing the outcome due to FOMO
- Consider selling (if possible) or buying the opposite side

When `Actual Price < Theoretical Price`:
- The option is "cheap"
- Market may be undervaluing the outcome
- Potential buying opportunity

## License

MIT
