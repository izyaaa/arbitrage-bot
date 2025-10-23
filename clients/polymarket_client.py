"""Optimized Polymarket CLOB API client"""
import asyncio
import logging
from typing import Dict, List, Optional
from decimal import Decimal
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class PolymarketClient:
    """High-performance async Polymarket client"""
    
    def __init__(
        self, 
        private_key: str, 
        chain_id: int = 137,
        host: str = "https://clob.polymarket.com"
    ):
        self.private_key = private_key
        self.chain_id = chain_id
        self.host = host
        self._client = None
        self._lock = asyncio.Lock()
    
    async def _get_client(self):
        """Lazy initialization with thread safety"""
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    try:
                        from py_clob_client.client import ClobClient
                        self._client = ClobClient(
                            key=self.private_key,
                            chain_id=self.chain_id,
                            host=self.host
                        )
                        logger.info("Polymarket client initialized")
                    except ImportError:
                        logger.error("py_clob_client not installed. Run: pip install py-clob-client")
                        raise
                    except Exception as e:
                        logger.error(f"Failed to initialize Polymarket client: {e}")
                        raise
        return self._client
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8)
    )
    async def get_active_hourly_markets(self) -> List[Dict]:
        """Fetch active hourly BTC markets"""
        try:
            client = await self._get_client()
            markets = await asyncio.to_thread(client.get_markets)
            
            # Filter for hourly BTC markets
            return [
                m for m in markets
                if 'BTC above' in m.get('question', '')
                and 'UTC' in m.get('question', '')
                and m.get('active', False)
            ]
        except Exception as e:
            logger.error(f"Error fetching Polymarket markets: {e}")
            return []
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8)
    )
    async def get_market_prices(self, condition_id: str) -> Dict:
        """Get orderbook prices for a condition"""
        try:
            client = await self._get_client()
            orderbook = await asyncio.to_thread(
                client.get_order_book, 
                condition_id
            )
            
            # Token IDs: '1' = YES, '0' = NO
            yes_book = orderbook.get('1', {})
            no_book = orderbook.get('0', {})
            
            return {
                'yes_ask': Decimal(yes_book['asks'][0]['price']) if yes_book.get('asks') else None,
                'yes_bid': Decimal(yes_book['bids'][0]['price']) if yes_book.get('bids') else None,
                'no_ask': Decimal(no_book['asks'][0]['price']) if no_book.get('asks') else None,
                'no_bid': Decimal(no_book['bids'][0]['price']) if no_book.get('bids') else None,
                'condition_id': condition_id
            }
        except Exception as e:
            logger.warning(f"Error fetching prices for {condition_id}: {e}")
            return {}
    
    async def get_market_prices_batch(self, condition_ids: List[str]) -> Dict[str, Dict]:
        """Fetch prices for multiple markets concurrently"""
        if not condition_ids:
            return {}
        
        tasks = [self.get_market_prices(cid) for cid in condition_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            cid: res for cid, res in zip(condition_ids, results)
            if isinstance(res, dict) and res
        }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8)
    )
    async def place_order(
        self, 
        token_id: str, 
        side: str, 
        amount: Decimal, 
        price: Decimal
    ) -> Optional[Dict]:
        """Place order on Polymarket"""
        try:
            client = await self._get_client()
            from py_clob_client.clob_types import OrderArgs
            from py_clob_client.order_builder.constants import BUY, SELL
            
            order_args = OrderArgs(
                token_id=token_id,
                price=float(price),
                size=float(amount),
                side=BUY if side.upper() == 'BUY' else SELL,
                fee_rate_bps=0
            )
            
            # Create and sign order
            signed_order = await asyncio.to_thread(
                client.create_order,
                order_args
            )
            
            # Submit order
            response = await asyncio.to_thread(
                client.post_order,
                signed_order,
                OrderType.GTC
            )
            
            logger.info(f"✓ Polymarket order placed: {side} ${amount} @ ${price}")
            return response
        except Exception as e:
            logger.error(f"Polymarket order failed: {e}")
            raise
