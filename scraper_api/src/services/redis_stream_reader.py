import asyncio
import json
import logging
import os
import redis
import redis.asyncio as aioredis
from datetime import datetime

from src.core.config import settings
from src.core.browser import BrowserManager
from src.core.database import AsyncSessionLocal
from src.models.job_card import JobCard
from src.services.upwork_scraper import UpworkScraper

logger = logging.getLogger(__name__)

class RedisStreamReader:
    """
    Consumer for Redis streams. 
    Coordinates between the Singleton Browser, Session Manager, and Scraper.
    Saves results to Postgres and propagates events.
    """
    def __init__(self):
        self.redis_client = None
        
        # Concurrency control
        self.semaphore = asyncio.Semaphore(8)
        
        # Redis config
        self.stream_name = settings.REDIS_STREAM_NAME
        self.group_name = settings.REDIS_GROUP_NAME
        self.consumer_name = settings.REDIS_CONSUMER_NAME

    async def connect(self):
        """Initializes Redis connection and consumer group."""
        try:
            self.redis_client = aioredis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                decode_responses=True
            )
            logger.info(f"Connected to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}")
            
            try:
                await self.redis_client.xgroup_create(self.stream_name, self.group_name, id="0", mkstream=True)
                logger.info(f"Created consumer group {self.group_name}")
            except redis.ResponseError as e:
                if "BUSYGROUP" not in str(e): raise e
        except Exception as e:
            logger.error(f"Redis connection failure: {e}")
            raise

    async def _on_card_data(self, **kwargs):
        """Callback to handle extracted card HTML and save to Postgres."""
        try:
            stream_id = kwargs.get("stream_id") # e.g., 1771075644552-0
            page_num = kwargs.get("page_num")
            card_index = kwargs.get("card_index")
            raw_html = kwargs.get("raw_html")
            url = kwargs.get("url")
            
            # 1. Construct Predictable ID
            # Redis stream IDs are timestamp-sequence (e.g., 1771075644552-0)
            # We create a sequence for this card to avoid collisions within the same task.
            base_ms = stream_id.split("-")[0]
            # Redis IDs must be milliseconds-sequence. Page/Card combined into sequence.
            # Using (page * 100) + index ensures uniqueness for up to 100 cards/page.
            sequence = (int(page_num) * 100) + int(card_index)
            predictable_id = f"{base_ms}-{sequence}"
            
            # 2. Save to Postgres first
            async with AsyncSessionLocal() as session:
                new_card = JobCard(
                    event_id=predictable_id,  # Use predictable ID for lookup
                    url=url,
                    status="captured",
                    html_content=raw_html,
                    metadata_json={
                        "original_task_id": stream_id,
                        "page_num": page_num,
                        "card_index": card_index
                    }
                )
                session.add(new_card)
                await session.commit()
                await session.refresh(new_card)
                card_db_id = new_card.id
            
            logger.info(f"✅ Saved card {card_index} to DB with predictable ID: {predictable_id}")

            # 3. Publish event to extraction stream with the EXACT same ID
            event_data = {
                "event_id": predictable_id,
                "card_db_id": str(card_db_id),
                "original_stream_id": stream_id,
                "card_index": str(card_index),
                "page_num": str(page_num),
                "url": url,
                "status": "card_captured",
                "timestamp": datetime.now().isoformat()
            }
            
            # Try with predictable ID first, fallback to '*' if it fails (e.g. ID already exists)
            try:
                msg_id = await self.redis_client.xadd(
                    settings.EXTRACTION_STREAM_NAME, 
                    event_data,
                    id=predictable_id
                )
            except redis.ResponseError as re:
                if "equal or smaller" in str(re):
                    logger.warning(f"⚠️ ID collision for {predictable_id}, falling back to auto-increment")
                    msg_id = await self.redis_client.xadd(
                        settings.EXTRACTION_STREAM_NAME, 
                        event_data,
                        id="*"
                    )
                else:
                    raise re
            
            logger.info(f"📤 Published extraction event: {msg_id}")

        except Exception as e:
            logger.error(f"Card processing or DB saving error: {e}")

    async def process_message(self, message_id, data):
        """Executes a scraping task for a single stream message."""
        async with self.semaphore:
            logger.info(f"🚀 Processing task {message_id}")
            logger.info(f"Task Data: {data}")
            
            # If 'pages' isn't provided, we pass None to let the scraper auto-detect
            url = data.get("page_url")
            raw_pages = data.get("pages")
            pages = int(raw_pages) if raw_pages else None
            
            # Allow resuming from a specific page (None allows URL-based detection)
            start_page_raw = data.get("start_page")
            start_page = int(start_page_raw) if start_page_raw else None
            
            logger.info(f"Requested Pages: {pages if pages else 'Auto-detect'} (Start at: {start_page or 'URL-based'})")
            
            # Create an independent browser instance for this specific task
            browser_manager = BrowserManager(headless=False, session_id=message_id)
            scraper = UpworkScraper(browser_manager)
            
            try:
                await scraper.scrape_jobs(
                    product_url=url,
                    no_of_pages_to_scrape=pages,
                    start_at_page=start_page,
                    on_card_data_async=lambda **kwargs: self._on_card_data(
                        stream_id=message_id, 
                        **kwargs
                    )
                )
                
                await self.redis_client.xack(self.stream_name, self.group_name, message_id)
                logger.info(f"✅ Completed task {message_id}")
            except Exception as e:
                logger.error(f"❌ Task {message_id} failed: {e}")
            finally:
                # Ensure the independent browser is closed
                await browser_manager.close()

    async def run(self):
        """Main loop: listens for new messages in the stream."""
        await self.connect()
        
        logger.info(f"📡 Listening for tasks on stream: {self.stream_name}")
            
        try:
            while True:
                messages = await self.redis_client.xreadgroup(
                    groupname=self.group_name,
                    consumername=self.consumer_name,
                    streams={self.stream_name: ">"},
                    count=1,
                    block=5000
                )
                if not messages: continue
                
                for stream, msgs in messages:
                    for message_id, data in msgs:
                        asyncio.create_task(self.process_message(message_id, data))
        finally:
            # Global cleanup of redis connection
            if self.redis_client:
                await self.redis_client.close()

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    await RedisStreamReader().run()

if __name__ == "__main__":
    asyncio.run(main())
