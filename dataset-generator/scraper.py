#!/usr/bin/env python3

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from models import Dataset, Project
from scraper_factory import ScraperFactory
# Import scrapers to trigger registration
from scrapers import code4rena_scraper, cantina_scraper, sherlock_scraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ScraperOrchestrator:
    
    def __init__(self, output_dir: str = "datasets"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def scrape(
        self,
        platforms: Optional[List[str]] = None,
        months: int = 12,
        output_file: Optional[str] = None,
        test_mode: bool = False,
        test_data_dir: str = None
    ) -> Dataset:
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months * 30)
        
        period_start = start_date.strftime('%Y-%m-%d')
        period_end = end_date.strftime('%Y-%m-%d')
        
        dataset_id = f"scabench_{start_date.strftime('%Y-%m')}_to_{end_date.strftime('%Y-%m')}"
        
        dataset = Dataset(
            dataset_id=dataset_id,
            period_start=period_start,
            period_end=period_end
        )
        
        if platforms is None:
            platforms = ScraperFactory.list_platforms()
        
        logger.info(f"Starting scrape for platforms: {platforms}")
        logger.info(f"Period: {period_start} to {period_end}")
        
        for platform in platforms:
            logger.info(f"Processing platform: {platform}")
            
            scraper = ScraperFactory.create(platform, test_mode=test_mode, test_data_dir=test_data_dir)
            if not scraper:
                logger.error(f"No scraper available for platform: {platform}")
                continue
            
            try:
                contests = scraper.fetch_contests(start_date, end_date)
                logger.info(f"Found {len(contests)} contests for {platform}")
                
                for contest in contests:
                    contest_id = contest.get('id')
                    if not contest_id:
                        continue
                    
                    logger.info(f"Fetching report for contest: {contest_id}")
                    report_data = scraper.fetch_report(contest_id)
                    
                    if report_data:
                        # report_data is already a dict from project.to_dict()
                        # We need to reconstruct the Project object from the dict
                        from models import Codebase, Vulnerability
                        
                        project = Project(
                            project_id=report_data['project_id'],
                            name=report_data['name'],
                            platform=report_data['platform']
                        )
                        
                        # Add codebases
                        for cb_dict in report_data.get('codebases', []):
                            codebase = Codebase(**cb_dict)
                            project.codebases.append(codebase)
                        
                        # Add vulnerabilities
                        for vuln_dict in report_data.get('vulnerabilities', []):
                            vulnerability = Vulnerability(**vuln_dict)
                            project.vulnerabilities.append(vulnerability)
                        
                        dataset.projects.append(project)
                        logger.info(f"Added project: {project.project_id}")
                    
            except Exception as e:
                logger.error(f"Error processing platform {platform}: {e}")
                continue
        
        if output_file:
            output_path = self.output_dir / output_file
        else:
            output_path = self.output_dir / f"{dataset_id}.json"
        
        with open(output_path, 'w') as f:
            f.write(dataset.to_json())
        
        logger.info(f"Dataset saved to: {output_path}")
        logger.info(f"Total projects: {len(dataset.projects)}")
        
        return dataset


def main():
    parser = argparse.ArgumentParser(
        description='Scrape security contest data from multiple platforms'
    )
    
    parser.add_argument(
        '--list-platforms',
        action='store_true',
        help='List available platforms and exit'
    )
    
    parser.add_argument(
        '--platforms',
        nargs='+',
        choices=['code4rena', 'sherlock', 'cantina'],
        help='Platforms to scrape (default: all)'
    )
    
    parser.add_argument(
        '--months',
        type=int,
        default=12,
        help='Number of months to look back (default: 12)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Output filename (default: auto-generated based on period)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='datasets',
        help='Output directory (default: datasets)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--test-mode',
        action='store_true',
        help='Use local test data instead of fetching from web'
    )
    
    parser.add_argument(
        '--test-data-dir',
        type=str,
        default='test/testdata',
        help='Directory containing test data files (default: test/testdata)'
    )
    
    args = parser.parse_args()
    
    # Handle --list-platforms
    if args.list_platforms:
        print("Available platforms:")
        for platform in ScraperFactory.list_platforms():
            print(f"  - {platform}")
        sys.exit(0)
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    orchestrator = ScraperOrchestrator(output_dir=args.output_dir)
    
    try:
        dataset = orchestrator.scrape(
            platforms=args.platforms,
            months=args.months,
            output_file=args.output,
            test_mode=args.test_mode,
            test_data_dir=args.test_data_dir
        )
        
        print(f"\nScraping completed successfully!")
        print(f"Dataset ID: {dataset.dataset_id}")
        print(f"Total projects: {len(dataset.projects)}")
        
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()