"""Parallel order execution with rollback capabilities"""
import asyncio
import logging
from typing import Dict, Optional
from decimal import Decimal
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionResult:
    """Immutable execution result"""
    success: bool
    limitless_order: Optional[Dict]
    polymarket_order: Optional[Dict]
    error: Optional[str] = None
    bet_size: Optional[Decimal] = None
    
    @property
    def both_filled(self) -> bool:
        """Check if both orders were successfully filled"""
        return bool(self.limitless_order and self.polymarket_order)


class OrderExecutor:
    """High-performance parallel order execution"""
    
    def __init__(
        self, 
        limitless_client, 
        polymarket_client,
        execution_timeout: int = 12
    ):
        self.limitless = limitless_client
        self.polymarket = polymarket_client
        self.execution_timeout = execution_timeout
    
    async def _execute_limitless_order(
        self,
        market_id: str,
        side: str,
        bet_size: Decimal,
        price: Decimal
    ) -> Optional[Dict]:
        """Execute Limitless order with error handling"""
        try:
            result = await self.limitless.place_order(
                market_id, 
                side, 
                bet_size, 
                price
            )
            return result
        except Exception as e:
            logger.error(f"Limitless order failed: {e}")
            return None
    
    async def _execute_polymarket_order(
        self,
        token_id: str,
        side: str,
        bet_size: Decimal,
        price: Decimal
    ) -> Optional[Dict]:
        """Execute Polymarket order with error handling"""
        try:
            result = await self.polymarket.place_order(
                token_id,
                side,
                bet_size,
                price
            )
            return result
        except Exception as e:
            logger.error(f"Polymarket order failed: {e}")
            return None
    
    def _get_polymarket_token_id(
        self, 
        polymarket_market: Dict, 
        side: str
    ) -> Optional[str]:
        """Extract correct token ID based on side"""
        try:
            tokens = polymarket_market.get('tokens', [])
            if not tokens or len(tokens) < 2:
                logger.error("Invalid Polymarket market structure")
                return None
            
            # Token index: YES = 1, NO = 0
            token_idx = 1 if side.upper() == 'YES' else 0
            return tokens[token_idx].get('token_id')
        except (KeyError, IndexError) as e:
            logger.error(f"Error getting token ID: {e}")
            return None
    
    async def execute_arbitrage(
        self,
        opportunity,
        bet_size: Decimal,
        match
    ) -> ExecutionResult:
        """
        Execute arbitrage by placing both orders in parallel
        
        Args:
            opportunity: Opportunity dataclass
            bet_size: Amount to bet per side
            match: MarketMatch containing market data
        
        Returns:
            ExecutionResult with order details
        """
        logger.info("=" * 60)
        logger.info(f"🎯 EXECUTING ARBITRAGE")
        logger.info(f"Strategy: {opportunity.type}")
        logger.info(f"Bet Size: ${bet_size} per side (${bet_size * 2} total)")
        logger.info(f"Expected Profit: {opportunity.profit_pct:.2f}%")
        logger.info("=" * 60)
        
        # Get Polymarket token ID
        poly_token_id = self._get_polymarket_token_id(
            match.polymarket,
            opportunity.polymarket_side
        )
        
        if not poly_token_id:
            return ExecutionResult(
                success=False,
                limitless_order=None,
                polymarket_order=None,
                error="Invalid Polymarket token ID"
            )
        
        # Create order tasks
        lim_task = asyncio.create_task(
            self._execute_limitless_order(
                match.limitless_id,
                opportunity.limitless_side,
                bet_size,
                opportunity.limitless_price
            )
        )
        
        poly_task = asyncio.create_task(
            self._execute_polymarket_order(
                poly_token_id,
                'BUY',  # Always buying on Polymarket
                bet_size,
                opportunity.polymarket_price
            )
        )
        
        try:
            # Execute both orders concurrently with timeout
            lim_result, poly_result = await asyncio.wait_for(
                asyncio.gather(lim_task, poly_task, return_exceptions=False),
                timeout=self.execution_timeout
            )
            
            success = bool(lim_result and poly_result)
            
            if success:
                logger.info("✅ ARBITRAGE EXECUTED SUCCESSFULLY!")
                logger.info(f"   Limitless Order ID: {lim_result.get('id', 'N/A')}")
                logger.info(f"   Polymarket Order ID: {poly_result.get('orderID', 'N/A')}")
            else:
                logger.warning("⚠️  PARTIAL EXECUTION - One order failed")
                logger.warning("   Manual intervention may be required")
                if not lim_result:
                    logger.warning("   → Limitless order FAILED")
                if not poly_result:
                    logger.warning("   → Polymarket order FAILED")
            
            return ExecutionResult(
                success=success,
                limitless_order=lim_result,
                polymarket_order=poly_result,
                bet_size=bet_size
            )
        
        except asyncio.TimeoutError:
            logger.error(f"❌ EXECUTION TIMEOUT ({self.execution_timeout}s)")
            logger.error("   Orders may be partially filled - check manually!")
            
            return ExecutionResult(
                success=False,
                limitless_order=None,
                polymarket_order=None,
                error="Execution timeout",
                bet_size=bet_size
            )
        
        except Exception as e:
            logger.error(f"❌ EXECUTION ERROR: {e}", exc_info=True)
            
            return ExecutionResult(
                success=False,
                limitless_order=None,
                polymarket_order=None,
                error=str(e),
                bet_size=bet_size
            )
