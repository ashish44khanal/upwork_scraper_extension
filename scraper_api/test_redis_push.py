import asyncio
import redis.asyncio as redis
import os
import time
import json
from dotenv import load_dotenv
from pathlib import Path

# Load env
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_env_path)

async def test_redis_pipeline():
    # Load settings from project
    from src.core.config import settings
    
    stream_name = settings.REDIS_STREAM_NAME
    extraction_stream = settings.EXTRACTION_STREAM_NAME  # Now upwork_job_extraction_stream
    host = settings.REDIS_HOST
    port = settings.REDIS_PORT
    
    r = redis.Redis(host=host, port=port, decode_responses=True)
    
    try:
        # 1. Clear previous stream data (optional but good for testing)
        # await r.delete(extraction_stream)
        
        # 2. Push job to scraper stream
        # Using a small search query or few pages for testing
        data = {
            "extraction_mode": "manual",
            "page_url": "https://www.upwork.com/nx/search/jobs/?q=fastapi&sort=recency",
            "pages": "1"
        }
        
        msg_id = await r.xadd(stream_name, data)
        print(f"🚀 Pushed search request to {stream_name} with ID: {msg_id}")
        
        # 3. Watch extraction stream for PER-CARD events
        print(f"⏳ Waiting for events in {extraction_stream} (polling for 120s)...")
        
        start_time = time.time()
        cards_found = 0
        last_id = "0"
        
        while time.time() - start_time < 120:
            messages = await r.xread({extraction_stream: last_id}, count=10, block=2000)
            if messages:
                for stream, msgs in messages:
                    for ext_id, ext_data in msgs:
                        last_id = ext_id
                        if ext_data.get("original_stream_id") == msg_id:
                            cards_found += 1
                            print(f"✅ Card Found! Event {ext_id}")
                            print(f"   - Card Index: {ext_data.get('card_index')}")
                            print(f"   - HTML: {ext_data.get('html_path')}")
                            print(f"   - Screenshot: {ext_data.get('screenshot_path')}")
            
            if cards_found > 0:
                # We could break if we know how many cards to expect, but let's just wait a bit
                pass
                
            await asyncio.sleep(1)
        
        print(f"\n📊 Test finished. Total cards captured: {cards_found}")
        if cards_found == 0:
            print("❌ FAILURE: No cards captured.")
        else:
            print("✅ SUCCESS: Pipeline working correctly.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await r.close()

if __name__ == "__main__":
    asyncio.run(test_redis_pipeline())
