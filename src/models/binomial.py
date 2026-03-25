"""
Binomial Options Pricing Model for Polymarket 15-minute markets.

This model discretizes the Black-Scholes process into discrete time steps,
making it more intuitive for short-expiry binary options.

For Polymarket 15-minute BTC Up/Down markets:
- "Up" = Binary Call (pays $1 if BTC price >= strike at expiry)
- "Down" = Binary Put (pays $1 if BTC price < strike at expiry)

The strike is effectively $0 (or the current price at market creation),
and the payoff is based on whether the price goes up or down.
"""
import math
from dataclasses import dataclass
from typing import Optional, Tuple
from scipy.stats import norm


SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60  # 31,557,600


@dataclass
class BinomialResult:
    """Result of binomial option pricing calculation."""
    up_price: float
    down_price: float
    delta_up: float
    delta_down: float
    gamma: float
    theta_per_second: float
    vega: float
    prob_up: float
    prob_down: float
    steps: int


class BinomialPricer:
    """
    Binomial option pricing for binary options.

    Uses the Cox-Ross-Rubinstein (CRR) binomial tree model adapted
    for binary (digital) options.
    """

    def __init__(self, default_volatility: float = 0.60):
        """
        Initialize pricer.

        Args:
            default_volatility: Annualized volatility (default 60% for crypto)
        """
        self.default_volatility = default_volatility

    def _calculate_u_d(
        self,
        sigma: float,
        dt: float
    ) -> Tuple[float, float]:
        """
        Calculate up and down factors for one time step.

        CRR formulation:
            u = exp(sigma * sqrt(dt))
            d = 1/u
        """
        u = math.exp(sigma * math.sqrt(dt))
        d = 1.0 / u
        return u, d

    def _calculate_risk_neutral_prob(
        self,
        u: float,
        d: float,
        r: float = 0.0,
        dt: float = 1.0
    ) -> float:
        """
        Calculate risk-neutral probability of up move.

        p = (exp(r*dt) - d) / (u - d)

        For r=0 (crypto, no risk-free rate):
            p = 1 / (1 + u)  ... wait that's not right

        Actually with r=0:
            p = (1 - d) / (u - d)
        """
        if abs(u - d) < 1e-10:
            return 0.5
        p = (1.0 - d) / (u - d)
        return max(0.0, min(1.0, p))

    def binary_call_price(
        self,
        S: float,
        K: float,
        T_seconds: float,
        sigma: Optional[float] = None,
        r: float = 0.0,
        steps: int = 100
    ) -> float:
        """
        Calculate binary call (Up) option price using binomial tree.

        Args:
            S: Current spot price (BTC)
            K: Strike price
            T_seconds: Time to expiry in seconds
            sigma: Annualized volatility
            r: Risk-free rate (default 0)
            steps: Number of binomial steps

        Returns:
            Price between 0 and 1
        """
        if sigma is None:
            sigma = self.default_volatility

        if T_seconds <= 0:
            return 1.0 if S >= K else 0.0

        dt = T_seconds / SECONDS_PER_YEAR / steps
        u, d = self._calculate_u_d(sigma, dt)
        p = self._calculate_risk_neutral_prob(u, d, r, dt)
        q = 1.0 - p  # prob of down move

        # At each node, the binary option payoff is:
        # - Call: 1 if S >= K at expiry, 0 otherwise
        #
        # We work backwards through the tree
        #
        # For a binary option, at each node we need to track
        # the probability of ending up in the money

        # Alternative approach: price as expected payoff discounted
        # P(up n times) = C(steps, n) * p^n * q^(steps-n)
        # For binary call: payoff = 1 if final price >= K

        # Final prices at each node: S * u^(steps-j) * d^j
        # where j = number of down moves

        # Count how many paths end up >= K
        # This is faster than building the full tree

        # Binary call payoff at expiry:
        # Price >= K when (steps-j) >= m where m = ln(K/S) / ln(u)
        # i.e., j <= steps - m

        # Number of up moves needed for S*u^n >= K
        if K <= 0:
            return 1.0  # Always in the money

        # CRR tree: final price = S * u^n * d^(steps-n)
        # For price to exceed K: S * u^n * d^(steps-n) > K
        # With u*d = 1: u^(2n - steps) > K/S
        # Taking log: (2n - steps) * log(u) > log(K/S)
        # So: n > (steps/2) + log(K/S) / (2*log(u))
        
        n_needed = (steps / 2) + math.log(K / S) / (2 * math.log(u))

        if n_needed <= 0:
            # Almost always in the money (far above strike)
            return 1.0
        elif n_needed >= steps:
            # Almost never in the money (far below strike)
            return 0.0
        else:
            # We need n_u > n_needed
            # If n_needed is exact integer, we need n_u > n_needed (n >= n_needed + 1)
            # If n_needed is fractional, we need n_u >= ceil(n_needed)
            if abs(n_needed - round(n_needed)) < 1e-10:
                n_start = int(round(n_needed)) + 1
            else:
                n_start = int(math.ceil(n_needed))
            total_prob = 0.0
            for n in range(n_start, steps + 1):
                # Binomial probability of exactly n up moves
                binom = self._binomial(steps, n)
                prob = binom * (p ** n) * (q ** (steps - n))
                total_prob += prob

            return total_prob

    def _binomial(self, n: int, k: int) -> float:
        """Calculate binomial coefficient C(n,k) = n! / (k! * (n-k)!)"""
        if k < 0 or k > n:
            return 0.0
        if k == 0 or k == n:
            return 1.0

        # Use log to avoid overflow for large n
        log_result = (self._log_factorial(n) -
                      self._log_factorial(k) -
                      self._log_factorial(n - k))
        return math.exp(log_result)

    def _log_factorial(self, n: int) -> float:
        """Log factorial using Stirling approximation for large n."""
        if n <= 1:
            return 0.0
        if n < 20:
            # Direct calculation for small n
            result = 0.0
            for i in range(2, n + 1):
                result += math.log(i)
            return result
        else:
            # Stirling's approximation
            return (n * math.log(n) - n + 0.5 * math.log(2 * math.pi * n))

    def binary_put_price(
        self,
        S: float,
        K: float,
        T_seconds: float,
        sigma: Optional[float] = None,
        r: float = 0.0,
        steps: int = 100
    ) -> float:
        """
        Calculate binary put (Down) option price.

        Binary put = 1 - Binary call (for same strike)
        """
        return 1.0 - self.binary_call_price(S, K, T_seconds, sigma, r, steps)

    def price(
        self,
        spot: float,
        strike: float,
        ttl_seconds: float,
        sigma: Optional[float] = None,
        steps: int = 100
    ) -> BinomialResult:
        """
        Full pricing with Greeks using binomial model.

        Args:
            spot: Current BTC spot price
            strike: Strike price (usually current price at creation)
            ttl_seconds: Time to expiry in seconds
            sigma: Annualized volatility
            steps: Number of binomial steps

        Returns:
            BinomialResult with prices and Greeks approximations
        """
        if sigma is None:
            sigma = self.default_volatility

        # Calculate prices
        up_price = self.binary_call_price(spot, strike, ttl_seconds, sigma, steps=steps)
        down_price = self.binary_put_price(spot, strike, ttl_seconds, sigma, steps=steps)

        # Calculate Greeks via finite differences
        dS = spot * 0.001  # 0.1% bump
        epsilon = 1.0  # 1 second

        # Delta: dPrice/dS
        up_up = self.binary_call_price(spot + dS, strike, ttl_seconds, sigma, steps=steps)
        up_down = self.binary_call_price(spot - dS, strike, ttl_seconds, sigma, steps=steps)
        delta = (up_up - up_down) / (2 * dS)

        # Gamma: d²Price/dS²
        gamma = (up_up - 2 * up_price + up_down) / (dS ** 2)

        # Theta: dPrice/dT (per second)
        up_T1 = self.binary_call_price(spot, strike, ttl_seconds, sigma, steps=steps)
        up_T0 = self.binary_call_price(spot, strike, max(0, ttl_seconds - 1), sigma, steps=steps)
        theta_per_second = up_T0 - up_T1  # Price increases as we get closer to expiry (for ITM)

        # Vega: dPrice/dSigma (approximated)
        sigma_bump = sigma * 0.01  # 1% bump in vol
        up_sigma1 = self.binary_call_price(spot, strike, ttl_seconds, sigma + sigma_bump, steps=steps)
        vega = (up_sigma1 - up_price) / sigma_bump

        # Risk-neutral probabilities
        dt = ttl_seconds / SECONDS_PER_YEAR / steps
        u, d = self._calculate_u_d(sigma, dt)
        p = self._calculate_risk_neutral_prob(u, d, 0.0, dt)

        return BinomialResult(
            up_price=up_price,
            down_price=down_price,
            delta_up=delta,
            delta_down=-delta,
            gamma=gamma,
            theta_per_second=theta_per_second,
            vega=vega,
            prob_up=p,
            prob_down=1 - p,
            steps=steps
        )


def compare_models(
    spot: float,
    strike: float,
    ttl_seconds: float,
    sigma: float = 0.60,
    steps: int = 100
) -> dict:
    """
    Compare Black-Scholes and Binomial model prices.

    Args:
        spot: Current BTC price
        strike: Strike price
        ttl_seconds: Time to expiry
        sigma: Volatility
        steps: Binomial steps

    Returns:
        Dict comparing both models
    """
    from .black_scholes import BinaryOptionPricer

    bs_pricer = BinaryOptionPricer(default_volatility=sigma)
    bs_result = bs_pricer.price(spot, strike, ttl_seconds, sigma)

    bin_pricer = BinomialPricer(default_volatility=sigma)
    bin_result = bin_pricer.price(spot, strike, ttl_seconds, sigma, steps=steps)

    return {
        'spot': spot,
        'strike': strike,
        'ttl_seconds': ttl_seconds,
        'volatility': sigma,
        'black_scholes': {
            'up_price': bs_result.up_price,
            'down_price': bs_result.down_price,
            'delta': bs_result.delta,
            'gamma': bs_result.gamma,
            'theta_per_second': bs_result.theta,
            'vega': bs_result.vega,
            'zone': bs_result.zone
        },
        'binomial': {
            'up_price': bin_result.up_price,
            'down_price': bin_result.down_price,
            'delta': bin_result.delta_up,
            'gamma': bin_result.gamma,
            'theta_per_second': bin_result.theta_per_second,
            'vega': bin_result.vega,
            'prob_up': bin_result.prob_up
        },
        'difference': {
            'up_price': abs(bs_result.up_price - bin_result.up_price)
        }
    }
