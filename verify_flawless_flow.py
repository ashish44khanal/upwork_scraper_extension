
import asyncio
import httpx
import asyncpg
import os
from datetime import datetime, timedelta

# DB config
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "postgres",
    "database": "upwork_db"
}

# API config
API_URL = "http://localhost:3000/scrape/upwork_jobs"
TEST_JOB_URL = "https://www.upwork.com/nx/search/jobs/?contractor_tier=1&nav_dir=pop&q=real%20estate&sort=relevance%2Bdesc&page=1&per_page=5"

async def check_results():
    conn = await asyncpg.connect(**DB_CONFIG)
    
    print(f"🚀 Triggering scrape for: {TEST_JOB_URL}")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(API_URL, json={"page_url": TEST_JOB_URL, "extraction_mode": "manual"})
            resp.raise_for_status()
            task_info = resp.json()
            stream_id = task_info.get("id")
            print(f"✅ API Call Successful. Stream ID: {stream_id}")
        except Exception as e:
            print(f"❌ API Call Failed: {e}")
            await conn.close()
            return

    # 1. Wait for JobCard
    print("⏳ Waiting for JobCard to be captured...")
    start_time = datetime.now()
    captured_count = 0
    while (datetime.now() - start_time) < timedelta(minutes=5):
        # We look for cards saved by the scraper with the original_task_id
        row = await conn.fetchrow(
            "SELECT COUNT(*) FROM job_cards WHERE metadata_json->>'original_task_id' = $1",
            stream_id
        )
        if row and row[0] > 0:
            captured_count = row[0]
            print(f"✨ Found {captured_count} cards captured in DB!")
            break
        await asyncio.sleep(5)
    
    if captured_count == 0:
        print("❌ Timeout waiting for JobCard capture.")
        await conn.close()
        return

    # 2. Wait for ExtractedJob
    print("⏳ Waiting for Extraction to complete...")
    extracted_count = 0
    while (datetime.now() - start_time) < timedelta(minutes=10):
        # We join with job_cards to find entries linked to our stream_id
        row = await conn.fetchrow(
            "SELECT COUNT(*) FROM extracted_jobs ej "
            "JOIN job_cards jc ON jc.event_id = ej.event_id "
            "WHERE jc.metadata_json->>'original_task_id' = $1",
            stream_id
        )
        if row and row[0] > 0:
            extracted_count = row[0]
            print(f"💎 Found {extracted_count} jobs extracted in DB!")
            if extracted_count >= captured_count:
                print("✅ Flow is COMPLETED and FLAWLESS!")
                break
        await asyncio.sleep(10)
    
    if extracted_count == 0:
        print("❌ Timeout waiting for extraction.")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_results())
