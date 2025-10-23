"""Bot configuration with immutable settings"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Final


@dataclass(frozen=True)
class BotConfig:
    """Immutable bot configuration for arbitrage trading"""
    
    # Trading Parameters
    MIN_SPREAD_PCT: Final[Decimal] = Decimal('3.0')
    MAX_BET_AMOUNT: Final[Decimal] = Decimal('10.0')
    MAX_STRIKE_DIFF: Final[Decimal] = Decimal('200.0')
    SLIPPAGE_TOLERANCE: Final[Decimal] = Decimal('0.5')
    
    # Performance Settings
    POLL_INTERVAL: Final[int] = 12  # seconds
    CACHE_TTL: Final[int] = 8  # seconds
    MARKET_CACHE_TTL: Final[int] = 5  # seconds
    
    # Network Settings
    MAX_CONCURRENT_REQUESTS: Final[int] = 20
    REQUEST_TIMEOUT: Final[int] = 8
    MAX_RETRIES: Final[int] = 3
    RETRY_MIN_WAIT: Final[float] = 1.0
    RETRY_MAX_WAIT: Final[float] = 8.0
    
    # API Endpoints
    LIMITLESS_API_URL: Final[str] = "https://api.limitless.exchange/api-v1"
    POLYMARKET_HOST: Final[str] = "https://clob.polymarket.com"
    POLYMARKET_CHAIN_ID: Final[int] = 137
    
    # Connection Pool
    POOL_SIZE: Final[int] = 50
    POOL_PER_HOST: Final[int] = 30
    DNS_CACHE_TTL: Final[int] = 300
