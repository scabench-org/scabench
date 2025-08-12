import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper_factory import ScraperFactory, register_scraper
from base_scraper import BaseScraper


class MockScraper(BaseScraper):
    def fetch_contests(self, period_start, period_end):
        return []
    
    def fetch_report(self, contest_id):
        return None


class TestScraperFactory(unittest.TestCase):
    
    def setUp(self):
        ScraperFactory.clear()
    
    def tearDown(self):
        ScraperFactory.clear()
    
    def test_register_and_create(self):
        ScraperFactory.register("mock", MockScraper)
        
        scraper = ScraperFactory.create("mock")
        self.assertIsNotNone(scraper)
        self.assertIsInstance(scraper, MockScraper)
        self.assertEqual(scraper.platform, "mock")
    
    def test_create_unknown_platform(self):
        scraper = ScraperFactory.create("unknown")
        self.assertIsNone(scraper)
    
    def test_list_platforms(self):
        ScraperFactory.register("platform1", MockScraper)
        ScraperFactory.register("platform2", MockScraper)
        
        platforms = ScraperFactory.list_platforms()
        self.assertEqual(len(platforms), 2)
        self.assertIn("platform1", platforms)
        self.assertIn("platform2", platforms)
    
    def test_register_decorator(self):
        @register_scraper("decorated")
        class DecoratedScraper(BaseScraper):
            def fetch_contests(self, period_start, period_end):
                return []
            
            def fetch_report(self, contest_id):
                return None
        
        scraper = ScraperFactory.create("decorated")
        self.assertIsNotNone(scraper)
        self.assertIsInstance(scraper, DecoratedScraper)
    
    def test_case_insensitive(self):
        ScraperFactory.register("TestPlatform", MockScraper)
        
        scraper1 = ScraperFactory.create("testplatform")
        scraper2 = ScraperFactory.create("TESTPLATFORM")
        scraper3 = ScraperFactory.create("TestPlatform")
        
        self.assertIsNotNone(scraper1)
        self.assertIsNotNone(scraper2)
        self.assertIsNotNone(scraper3)


if __name__ == '__main__':
    unittest.main()