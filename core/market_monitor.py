"""Optimized market monitoring with intelligent matching"""
import asyncio
import logging
import re
from typing import Dict, List, Tuple, Optional
from decimal import Decimal
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketMatch:
    """Immutable market match data structure"""
    limitless: Dict
    polymarket: Dict
    strike_limitless: Decimal
    strike_polymarket: Decimal
    strike_diff: Decimal
    time: str
    
    @property
    def limitless_id(self) -> str:
        return self.limitless['id']
    
    @property
    def polymarket_condition_id(self) -> str:
        return self.polymarket['condition_id']


class MarketMonitor:
    """High-performance market monitoring with caching"""
    
    # Pre-compiled regex patterns (class-level for efficiency)
    STRIKE_REGEX = re.compile(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)')
    TIME_REGEX = re.compile(r'(\d{1,2}:\d{2})\s*UTC')
    
    def __init__(
        self, 
        limitless_client, 
        polymarket_client, 
        max_strike_diff: Decimal
    ):
        self.limitless = limitless_client
        self.polymarket = polymarket_client
        self.max_strike_diff = max_strike_diff
    
    @lru_cache(maxsize=200)
    def parse_strike_and_time(self, title: str) -> Optional[Tuple[Decimal, str]]:
        """Parse strike price and time from market title (cached)"""
        strike_match = self.STRIKE_REGEX.search(title)
        time_match = self.TIME_REGEX.search(title)
        
        if not (strike_match and time_match):
            return None
        
        try:
            strike_str = strike_match.group(1).replace(',', '')
            strike = Decimal(strike_str)
            time_str = time_match.group(1)
            return (strike, time_str)
        except (ValueError, IndexError) as e:
            logger.debug(f"Parse error for '{title}': {e}")
            return None
    
    def _build_time_strike_map(
        self, 
        markets: List[Dict], 
        title_key: str
    ) -> Dict[str, List[Tuple[Decimal, Dict]]]:
        """Build efficient lookup map: time -> [(strike, market)]"""
        time_map = {}
        
        for market in markets:
            title = market.get(title_key, '')
            parsed = self.parse_strike_and_time(title)
            
            if parsed:
                strike, time_slot = parsed
                if time_slot not in time_map:
                    time_map[time_slot] = []
                time_map[time_slot].append((strike, market))
        
        return time_map
    
    async def find_matching_markets(self) -> List[MarketMatch]:
        """Find matching markets across platforms with parallel fetching"""
        try:
            # Fetch from both platforms concurrently
            lim_task = asyncio.create_task(self.limitless.get_active_hourly_markets())
            poly_task = asyncio.create_task(self.polymarket.get_active_hourly_markets())
            
            lim_markets, poly_markets = await asyncio.gather(
                lim_task, 
                poly_task,
                return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(lim_markets, Exception):
                logger.error(f"Limitless fetch failed: {lim_markets}")
                return []
            if isinstance(poly_markets, Exception):
                logger.error(f"Polymarket fetch failed: {poly_markets}")
                return []
            
            logger.debug(f"Found {len(lim_markets)} Limitless, {len(poly_markets)} Polymarket markets")
            
            # Build lookup maps for O(1) matching
            lim_map = self._build_time_strike_map(lim_markets, 'title')
            poly_map = self._build_time_strike_map(poly_markets, 'question')
            
            # Match markets by time, then by strike proximity
            matches = []
            
            for time_slot in lim_map:
                if time_slot not in poly_map:
                    continue
                
                # Match all combinations within strike threshold
                for lim_strike, lim_market in lim_map[time_slot]:
                    for poly_strike, poly_market in poly_map[time_slot]:
                        strike_diff = abs(lim_strike - poly_strike)
                        
                        if strike_diff <= self.max_strike_diff:
                            match = MarketMatch(
                                limitless=lim_market,
                                polymarket=poly_market,
                                strike_limitless=lim_strike,
                                strike_polymarket=poly_strike,
                                strike_diff=strike_diff,
                                time=time_slot
                            )
                            matches.append(match)
                            
                            logger.info(
                                f"✓ Match: {time_slot} UTC | "
                                f"Limitless ${lim_strike} vs Polymarket ${poly_strike} "
                                f"(diff: ${strike_diff})"
                            )
            
            logger.info(f"Total matches found: {len(matches)}")
            return matches
        
        except Exception as e:
            logger.error(f"Error finding matching markets: {e}", exc_info=True)
            return []
