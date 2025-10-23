"""Arbitrage opportunity detection and calculation"""
import logging
from typing import Optional, List
from decimal import Decimal
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Opportunity:
    """Immutable arbitrage opportunity"""
    type: str
    limitless_side: str
    limitless_price: Decimal
    polymarket_side: str
    polymarket_price: Decimal
    total_cost: Decimal
    spread_pct: Decimal
    profit_pct: Decimal
    
    def __str__(self) -> str:
        return (
            f"{self.type} | "
            f"Spread: {self.spread_pct:.2f}% | "
            f"Profit: {self.profit_pct:.2f}%"
        )


class ArbitrageEngine:
    """Fast arbitrage detection with optimized calculations"""
    
    def __init__(
        self, 
        min_spread_pct: Decimal, 
        max_bet: Decimal, 
        slippage: Decimal
    ):
        self.min_spread_pct = min_spread_pct
        self.max_bet = max_bet
        self.slippage = slippage
        
        # Pre-calculate constants
        self._one = Decimal('1')
        self._hundred = Decimal('100')
        self._zero = Decimal('0')
    
    def calculate_spread(self, price1: Decimal, price2: Decimal) -> Decimal:
        """Calculate percentage spread between two prices"""
        if not price1 or not price2 or price1 <= self._zero or price2 <= self._zero:
            return self._zero
        
        mid = (price1 + price2) / 2
        if mid == self._zero:
            return self._zero
        
        return abs(price1 - price2) / mid * self._hundred
    
    def _evaluate_scenario(
        self,
        lim_price: Optional[Decimal],
        poly_price: Optional[Decimal],
        scenario_type: str,
        lim_side: str,
        poly_side: str
    ) -> Optional[Opportunity]:
        """Evaluate a specific arbitrage scenario"""
        if not lim_price or not poly_price:
            return None
        
        total_cost = lim_price + poly_price
        
        # Arbitrage exists when total cost < 1.00
        if total_cost >= self._one:
            return None
        
        # Calculate profit and spread
        profit_pct = (self._one - total_cost) / total_cost * self._hundred
        
        # For spread, compare complementary probabilities
        poly_implied = self._one - poly_price
        spread = self.calculate_spread(lim_price, poly_implied)
        
        # Check if spread meets minimum threshold
        if spread < self.min_spread_pct:
            return None
        
        return Opportunity(
            type=scenario_type,
            limitless_side=lim_side,
            limitless_price=lim_price,
            polymarket_side=poly_side,
            polymarket_price=poly_price,
            total_cost=total_cost,
            spread_pct=spread,
            profit_pct=profit_pct
        )
    
    def find_arbitrage(
        self, 
        lim_prices: dict, 
        poly_prices: dict
    ) -> Optional[Opportunity]:
        """Detect arbitrage opportunities from price data"""
        opportunities: List[Opportunity] = []
        
        # Scenario 1: Buy YES on Limitless + Buy NO on Polymarket
        # Win if outcome is YES: Limitless pays $1, lose Poly NO stake
        # Win if outcome is NO: Polymarket pays $1, lose Limitless YES stake
        # Both outcomes guaranteed if total_cost < $1
        opp1 = self._evaluate_scenario(
            lim_prices.get('yes_ask'),
            poly_prices.get('no_ask'),
            'YES_LIMITLESS_NO_POLYMARKET',
            'YES',
            'NO'
        )
        if opp1:
            opportunities.append(opp1)
        
        # Scenario 2: Buy NO on Limitless + Buy YES on Polymarket
        opp2 = self._evaluate_scenario(
            lim_prices.get('no_ask'),
            poly_prices.get('yes_ask'),
            'NO_LIMITLESS_YES_POLYMARKET',
            'NO',
            'YES'
        )
        if opp2:
            opportunities.append(opp2)
        
        if not opportunities:
            return None
        
        # Return the best opportunity by profit percentage
        best = max(opportunities, key=lambda x: x.profit_pct)
        
        logger.info(f"💰 Arbitrage found: {best}")
        return best
    
    def calculate_bet_size(self, opportunity: Opportunity) -> Decimal:
        """Calculate optimal bet size with slippage protection"""
        # Apply slippage tolerance to max bet
        slippage_factor = self._one - (self.slippage / self._hundred)
        adjusted_max = self.max_bet * slippage_factor
        
        # Bet size per side (since we're placing two orders)
        bet_per_side = adjusted_max / 2
        
        # Round to 2 decimal places for currency
        return bet_per_side.quantize(Decimal('0.01'))
    
    def estimate_profit(
        self, 
        opportunity: Opportunity, 
        bet_size: Decimal
    ) -> Decimal:
        """Calculate expected profit after fees"""
        total_invested = bet_size * 2  # Two sides
        total_payout = bet_size * 2 / opportunity.total_cost
        
        return (total_payout - total_invested).quantize(Decimal('0.01'))
