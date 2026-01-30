#!/usr/bin/env python3
"""
E2E test for Upwork scraper: product URL + session (login / cookies).

Run locally (browser + network required). Env vars are read from .env:
  python test_upwork_scraper.py
"""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (scraper_api/.env)
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")


async def test_scrape():
    from src.services.upwork_scraper import UpworkScraper

    if not os.getenv("GEMINI_API_KEY"):
        print("Set GEMINI_API_KEY")
        return 1
    if not os.getenv("UPWORK_USERNAME") or not os.getenv("UPWORK_PASSWORD"):
        print("Set UPWORK_USERNAME and UPWORK_PASSWORD for login test")
        return 1

    scraper = UpworkScraper(headless=False)  # headless=True for CI
    try:
        product_url = "https://www.upwork.com/nx/search/jobs/?q=python"
        print("Testing scrape_jobs(product_url, num_jobs=1)...")
        results = await scraper.scrape_jobs(product_url, num_jobs=1)
        print(f"Results: {len(results)} job(s)")
        if results:
            print("First job title:", results[0].get("job_title"))
        return 0 if results else 1
    except Exception as e:
        print("Error:", type(e).__name__, e)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        await scraper.close()


if __name__ == "__main__":
    exit(asyncio.run(test_scrape()))
