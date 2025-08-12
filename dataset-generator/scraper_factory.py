from typing import Dict, Type, Optional
from base_scraper import BaseScraper
import logging

logger = logging.getLogger(__name__)


class ScraperFactory:
    _scrapers: Dict[str, Type[BaseScraper]] = {}
    
    @classmethod
    def register(cls, platform: str, scraper_class: Type[BaseScraper]):
        cls._scrapers[platform.lower()] = scraper_class
        logger.info(f"Registered scraper for platform: {platform}")
    
    @classmethod
    def create(cls, platform: str, test_mode: bool = False, test_data_dir: str = None) -> Optional[BaseScraper]:
        platform_lower = platform.lower()
        if platform_lower not in cls._scrapers:
            logger.error(f"No scraper registered for platform: {platform}")
            return None
        
        scraper_class = cls._scrapers[platform_lower]
        return scraper_class(platform_lower, test_mode=test_mode, test_data_dir=test_data_dir)
    
    @classmethod
    def list_platforms(cls) -> list:
        return list(cls._scrapers.keys())
    
    @classmethod
    def clear(cls):
        cls._scrapers.clear()


def register_scraper(platform: str):
    def decorator(scraper_class: Type[BaseScraper]):
        ScraperFactory.register(platform, scraper_class)
        return scraper_class
    return decorator