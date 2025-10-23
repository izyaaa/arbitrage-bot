"""
Optimized Arbitrage Bot - Maximum Performance Edition
Combines async/await, connection pooling, caching, and intelligent error handling
"""
import asyncio
import logging
import signal
from decimal import Decimal
from typing import List

from config.settings import BotConfig
from config.credentials import Credentials
from clients.limitless_client import LimitlessClient
from clients.polymarket_client import PolymarketClient
from core.market_monitor import MarketMonitor, MarketMatch
from core.arbitrage_engine import ArbitrageEngine, Opportunity
from core.order_executor import OrderExecutor
from utils.logger import setup_logger
from utils.cache import AsyncCache

logger = setup_logger()


class ArbitrageBot:
    """High-performance async arbitrage bot"""
    
    def __init__(self):
        self.config = BotConfig()
        self.cache = AsyncCache(ttl=self.config.CACHE_TTL)
        self.running = True
        self.stats = {
            'scans': 0,
            'opportunities_found': 0,
            'trades_executed': 0,
            'trades_successful': 0,
            'trades_failed': 0
        }
    
    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""
        def signal_handler(signum, frame):
            logger.info(f"\n🛑 Received signal {signum}, shutting down gracefully...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def initialize_clients(self):
        """Initialize API clients"""
        logger.info("Initializing API clients...")
        
        try:
            self.limitless = LimitlessClient(
                self.config.LIMITLESS_API_URL,
                Credentials.get_limitless_key(),
                Credentials.get_limitless_private_key(),
                timeout=self.config.REQUEST_TIMEOUT,
                max_concurrent=self.config.MAX_CONCURRENT_REQUESTS
            )
            
            self.polymarket = PolymarketClient(
                Credentials.get_polymarket_private_key(),
                self.config.POLYMARKET_CHAIN_ID,
                self.config.POLYMARKET_HOST
            )
            
            self.monitor = MarketMonitor(
                self.limitless,
                self.polymarket,
                self.config.MAX_STRIKE_DIFF
            )
            
            self.arbitrage_engine = ArbitrageEngine(
                self.config.MIN_SPREAD_PCT,
                self.config.MAX_BET_AMOUNT,
                self.config.SLIPPAGE_TOLERANCE
            )
            
            self.executor = OrderExecutor(
                self.limitless, 
                self.polymarket,
                execution_timeout=self.config.REQUEST_TIMEOUT + 4
            )
            
            logger.info("✓ All clients initialized successfully")
        
        except Exception as e:
            logger.error(f"Failed to initialize clients: {e}", exc_info=True)
            raise
    
    async def process_match(
        self, 
        match: MarketMatch
    ) -> bool:
        """
        Process a single market match for arbitrage
        
        Returns:
            True if trade was executed, False otherwise
        """
        try:
            # Fetch prices for both markets
            lim_prices, poly_prices = await asyncio.gather(
                self.limitless.get_market_prices(match.limitless_id),
                self.polymarket.get_market_prices(match.polymarket_condition_id)
            )
            
            if not lim_prices or not poly_prices:
                logger.debug(f"Missing prices for {match.time} UTC")
                return False
            
            # Check for arbitrage opportunity
            opportunity = self.arbitrage_engine.find_arbitrage(
                lim_prices, 
                poly_prices
            )
            
            if not opportunity:
                return False
            
            self.stats['opportunities_found'] += 1
            
            # Calculate bet size
            bet_size = self.arbitrage_engine.calculate_bet_size(opportunity)
            estimated_profit = self.arbitrage_engine.estimate_profit(
                opportunity, 
                bet_size
            )
            
            logger.info(f"""
╔══════════════════════════════════════════════════════════╗
║           🎯 ARBITRAGE OPPORTUNITY DETECTED              ║
╠══════════════════════════════════════════════════════════╣
║ Market Time:      {match.time} UTC
║ Limitless Strike: ${match.strike_limitless}
║ Polymarket Strike: ${match.strike_polymarket}
║ Strike Diff:      ${match.strike_diff}
╠══════════════════════════════════════════════════════════╣
║ Strategy:         {opportunity.type}
║ Spread:           {opportunity.spread_pct:.2f}%
║ Profit Potential: {opportunity.profit_pct:.2f}%
╠══════════════════════════════════════════════════════════╣
║ Limitless:        {opportunity.limitless_side} @ ${opportunity.limitless_price}
║ Polymarket:       {opportunity.polymarket_side} @ ${opportunity.polymarket_price}
║ Total Cost:       ${opportunity.total_cost}
╠══════════════════════════════════════════════════════════╣
║ Bet Size:         ${bet_size} per side
║ Total Investment: ${bet_size * 2}
║ Est. Profit:      ${estimated_profit}
╚══════════════════════════════════════════════════════════╝
            """)
            
            # Execute arbitrage
            result = await self.executor.execute_arbitrage(
                opportunity,
                bet_size,
                match
            )
            
            self.stats['trades_executed'] += 1
            
            if result.success:
                self.stats['trades_successful'] += 1
                logger.info(f"✅ Trade #{self.stats['trades_successful']} completed successfully!")
                return True
            else:
                self.stats['trades_failed'] += 1
                logger.error(f"❌ Trade failed: {result.error}")
                return False
        
        except Exception as e:
            logger.error(f"Error processing match: {e}", exc_info=True)
            return False
    
    async def scan_and_execute(self):
        """Main scanning and execution loop"""
        self.stats['scans'] += 1
        scan_num = self.stats['scans']
        
        logger.info("=" * 70)
        logger.info(f"🔍 SCAN #{scan_num} - Searching for arbitrage opportunities...")
        logger.info("=" * 70)
        
        try:
            # Find matching markets
            matches = await self.monitor.find_matching_markets()
            
            if not matches:
                logger.info("No matching markets found")
                return
            
            logger.info(f"📊 Processing {len(matches)} market match(es)...")
            
            # Process all matches concurrently
            tasks = [self.process_match(match) for match in matches]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Count successful trades
            trades_this_scan = sum(1 for r in results if r is True)
            
            if trades_this_scan > 0:
                logger.info(f"🎉 Executed {trades_this_scan} trade(s) this scan!")
            else:
                logger.info("No profitable opportunities found this scan")
        
        except Exception as e:
            logger.error(f"Scan error: {e}", exc_info=True)
        
        finally:
            # Cleanup expired cache entries
            cleaned = await self.cache.cleanup_expired()
            if cleaned > 0:
                logger.debug(f"Cleaned {cleaned} expired cache entries")
    
    def print_stats(self):
        """Print bot statistics"""
        logger.info("=" * 70)
        logger.info("📈 BOT STATISTICS")
        logger.info("=" * 70)
        logger.info(f"Total Scans:          {self.stats['scans']}")
        logger.info(f"Opportunities Found:  {self.stats['opportunities_found']}")
        logger.info(f"Trades Attempted:     {self.stats['trades_executed']}")
        logger.info(f"Trades Successful:    {self.stats['trades_successful']}")
        logger.info(f"Trades Failed:        {self.stats['trades_failed']}")
        
        if self.stats['trades_executed'] > 0:
            success_rate = (self.stats['trades_successful'] / 
                          self.stats['trades_executed'] * 100)
            logger.info(f"Success Rate:         {success_rate:.1f}%")
        
        logger.info("=" * 70)
    
    async def run(self):
        """Main bot execution loop"""
        self._setup_signal_handlers()
        
        logger.info("=" * 70)
        logger.info("🚀 ARBITRAGE BOT STARTING (OPTIMIZED)")
        logger.info("=" * 70)
        logger.info(f"Min Spread:           {self.config.MIN_SPREAD_PCT}%")
        logger.info(f"Max Bet:              ${self.config.MAX_BET_AMOUNT}")
        logger.info(f"Max Strike Diff:      ${self.config.MAX_STRIKE_DIFF}")
        logger.info(f"Poll Interval:        {self.config.POLL_INTERVAL}s")
        logger.info(f"Slippage Tolerance:   {self.config.SLIPPAGE_TOLERANCE}%")
        logger.info("=" * 70)
        
        async with self.limitless:
            try:
                while self.running:
                    await self.scan_and_execute()
                    
                    if self.running:
                        logger.debug(f"Sleeping for {self.config.POLL_INTERVAL}s...")
                        await asyncio.sleep(self.config.POLL_INTERVAL)
            
            except KeyboardInterrupt:
                logger.info("🛑 Bot stopped by user")
            
            except Exception as e:
                logger.error(f"Fatal error: {e}", exc_info=True)
            
            finally:
                self.print_stats()
                logger.info("🏁 Bot shutdown complete")


async def main():
    """Entry point"""
    bot = ArbitrageBot()
    
    try:
        await bot.initialize_clients()
        await bot.run()
    except Exception as e:
        logger.error(f"Bot initialization failed: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Goodbye!")
