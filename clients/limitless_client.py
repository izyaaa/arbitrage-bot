"""Optimized Limitless Exchange CLOB API client"""
import asyncio
import aiohttp
import logging
import hmac
import hashlib
import json
from typing import Dict, List, Optional
from decimal import Decimal
from tenacity import retry, stop_after_attempt, wait_exponential
from datetime import datetime

logger = logging.getLogger(__name__)


class LimitlessClient:
    """High-performance async Limitless Exchange client"""
    
    def __init__(
        self, 
        api_key: str,
        api_secret: str,
        host: str = "https://api.limitless.exchange/api-v1"
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.host = host
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazy initialization of aiohttp session with thread safety"""
        if self._session is None or self._session.closed:
            async with self._lock:
                if self._session is None or self._session.closed:
                    self._session = aiohttp.ClientSession(
                        timeout=aiohttp.ClientTimeout(total=30)
                    )
                    logger.info("Limitless client session initialized")
        return self._session
    
    def _generate_signature(self, method: str, endpoint: str, params: Dict = None, body: Dict = None) -> str:
        """Generate HMAC signature for authenticated requests"""
        timestamp = str(int(datetime.utcnow().timestamp() * 1000))
        
        # Create signature payload (adjust based on actual Limitless requirements)
        message = f"{timestamp}{method}{endpoint}"
        if params:
            message += json.dumps(params, sort_keys=True)
        if body:
            message += json.dumps(body, sort_keys=True)
        
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature, timestamp
    
    def _get_headers(self, method: str, endpoint: str, params: Dict = None, body: Dict = None, authenticated: bool = True) -> Dict:
        """Generate request headers"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        if authenticated:
            signature, timestamp = self._generate_signature(method, endpoint, params, body)
            headers.update({
                "X-API-Key": self.api_key,
                "X-Timestamp": timestamp,
                "X-Signature": signature
            })
        
        return headers
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8)
    )
    async def get_markets(self, active_only: bool = True) -> List[Dict]:
        """Fetch all markets from Limitless Exchange"""
        try:
            session = await self._get_session()
            endpoint = "/markets"
            url = f"{self.host}{endpoint}"
            
            params = {"active": active_only} if active_only else {}
            headers = self._get_headers("GET", endpoint, params=params, authenticated=False)
            
            async with session.get(url, params=params, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()
                logger.info(f"Fetched {len(data)} markets from Limitless")
                return data
        except Exception as e:
            logger.error(f"Error fetching Limitless markets: {e}")
            return []
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8)
    )
    async def get_active_hourly_markets(self, asset: str = "BTC") -> List[Dict]:
        """Fetch active hourly price prediction markets"""
        try:
            markets = await self.get_markets(active_only=True)
            
            # Filter for hourly markets (adjust filters based on actual market structure)
            return [
                m for m in markets
                if asset in m.get('title', '') or asset in m.get('question', '')
                and 'hourly' in m.get('title', '').lower() or 'UTC' in m.get('title', '')
                and m.get('active', False)
            ]
        except Exception as e:
            logger.error(f"Error fetching hourly markets: {e}")
            return []
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8)
    )
    async def get_orderbook(self, market_id: str) -> Dict:
        """Get orderbook for a specific market"""
        try:
            session = await self._get_session()
            endpoint = f"/markets/{market_id}/orderbook"
            url = f"{self.host}{endpoint}"
            
            headers = self._get_headers("GET", endpoint, authenticated=False)
            
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            logger.warning(f"Error fetching orderbook for {market_id}: {e}")
            return {}
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8)
    )
    async def get_market_prices(self, market_id: str) -> Dict:
        """Get orderbook prices for a market"""
        try:
            orderbook = await self.get_orderbook(market_id)
            
            # Parse orderbook structure (adjust based on actual API response)
            yes_book = orderbook.get('yes', {}) or orderbook.get('bids', {})
            no_book = orderbook.get('no', {}) or orderbook.get('asks', {})
            
            return {
                'yes_ask': Decimal(str(yes_book['asks'][0]['price'])) if yes_book.get('asks') else None,
                'yes_bid': Decimal(str(yes_book['bids'][0]['price'])) if yes_book.get('bids') else None,
                'no_ask': Decimal(str(no_book['asks'][0]['price'])) if no_book.get('asks') else None,
                'no_bid': Decimal(str(no_book['bids'][0]['price'])) if no_book.get('bids') else None,
                'market_id': market_id,
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.warning(f"Error fetching prices for {market_id}: {e}")
            return {}
    
    async def get_market_prices_batch(self, market_ids: List[str]) -> Dict[str, Dict]:
        """Fetch prices for multiple markets concurrently"""
        if not market_ids:
            return {}
        
        tasks = [self.get_market_prices(mid) for mid in market_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            mid: res for mid, res in zip(market_ids, results)
            if isinstance(res, dict) and res
        }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8)
    )
    async def place_order(
        self, 
        market_id: str,
        outcome: str,  # 'yes' or 'no'
        side: str,     # 'buy' or 'sell'
        amount: Decimal, 
        price: Decimal,
        order_type: str = "limit"  # 'limit' or 'market'
    ) -> Optional[Dict]:
        """Place order on Limitless Exchange"""
        try:
            session = await self._get_session()
            endpoint = "/orders"
            url = f"{self.host}{endpoint}"
            
            body = {
                "market_id": market_id,
                "outcome": outcome.lower(),
                "side": side.lower(),
                "amount": str(amount),
                "price": str(price),
                "type": order_type.lower()
            }
            
            headers = self._get_headers("POST", endpoint, body=body, authenticated=True)
            
            async with session.post(url, json=body, headers=headers) as response:
                response.raise_for_status()
                result = await response.json()
                logger.info(f"✓ Limitless order placed: {outcome.upper()} {side.upper()} ${amount} @ ${price}")
                return result
        except Exception as e:
            logger.error(f"Limitless order failed: {e}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8)
    )
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order"""
        try:
            session = await self._get_session()
            endpoint = f"/orders/{order_id}"
            url = f"{self.host}{endpoint}"
            
            headers = self._get_headers("DELETE", endpoint, authenticated=True)
            
            async with session.delete(url, headers=headers) as response:
                response.raise_for_status()
                logger.info(f"✓ Order {order_id} cancelled")
                return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8)
    )
    async def get_balance(self) -> Dict:
        """Get account balance"""
        try:
            session = await self._get_session()
            endpoint = "/account/balance"
            url = f"{self.host}{endpoint}"
            
            headers = self._get_headers("GET", endpoint, authenticated=True)
            
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return {}
    
    async def close(self):
        """Close the aiohttp session"""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("Limitless client session closed")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
