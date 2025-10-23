"""Secure credentials management with caching"""
import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()


class Credentials:
    """Centralized credentials manager"""
    
    @staticmethod
    @lru_cache(maxsize=1)
    def get_limitless_key() -> str:
        key = os.getenv('LIMITLESS_API_KEY', '')
        if not key:
            raise ValueError("LIMITLESS_API_KEY not found in environment")
        return key
    
    @staticmethod
    @lru_cache(maxsize=1)
    def get_limitless_private_key() -> str:
        key = os.getenv('LIMITLESS_PRIVATE_KEY', '')
        if not key:
            raise ValueError("LIMITLESS_PRIVATE_KEY not found in environment")
        return key
    
    @staticmethod
    @lru_cache(maxsize=1)
    def get_polymarket_private_key() -> str:
        key = os.getenv('POLYMARKET_PRIVATE_KEY', '')
        if not key:
            raise ValueError("POLYMARKET_PRIVATE_KEY not found in environment")
        return key
    
    @staticmethod
    @lru_cache(maxsize=1)
    def get_polymarket_api_key() -> str:
        return os.getenv('POLYMARKET_API_KEY', '')
