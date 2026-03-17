from fastapi import APIRouter, HTTPException
from typing import List, Any
from src.services.upwork_scraper import UpworkScraper
from src.core.browser import close_browser
from datetime import datetime

router = APIRouter()

@router.post("/upwork")
async def scrape_upwork(product_url: str, no_of_pages_to_scrape: int = 1, headless: bool = False):
    """
    Scrape jobs from Upwork at the given product URL.
    Returns the raw HTML chunks of identified job cards.
    """
    try:
        session_id = f"api_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        scraper = UpworkScraper(session_id=session_id)
        
        try:
            all_results = []
            async def sync_callback(**kwargs):
                all_results.append({
                    "page_num": kwargs.get("page_num"),
                    "card_index": kwargs.get("card_index"),
                    "html": kwargs.get("raw_html")
                })
    
            await scraper.scrape_jobs(
                product_url=product_url,
                no_of_pages_to_scrape=no_of_pages_to_scrape,
                on_card_data_async=sync_callback
            )
            
            if not all_results:
                raise HTTPException(
                    status_code=404,
                    detail="No jobs found or scraper was blocked."
                )
                
            return {
                "status": "success",
                "session_id": session_id,
                "count": len(all_results),
                "data": all_results
            }
        except HTTPException:
            raise
        except Exception as e:
            import traceback
            print(f"Upwork critical API error: {e}")
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Automation failure: {str(e)}"
            )
        # We don't close the browser here anymore because it's a singleton
        # but if we wanted to force a cleanup we could call close_browser()
    except Exception as outer_e:
        raise HTTPException(
            status_code=500,
            detail=f"API entry point failure: {str(outer_e)}"
        )
