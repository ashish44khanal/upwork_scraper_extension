import asyncio
import json
import logging
import os
import redis
import redis.asyncio as aioredis
from datetime import datetime

from src.core.config import settings
from src.core.browser import BrowserManager
from src.services.session_manager import UpworkSessionManager
from src.services.upwork_scraper import UpworkScraper

logger = logging.getLogger(__name__)

class RedisStreamReader:
    """
    Consumer for Redis streams. 
    Coordinates between the Singleton Browser, Session Manager, and Scraper.
    """
    def __init__(self):
        self.redis_client = None
        self.browser_manager = BrowserManager(headless=False)
        self.session_manager = UpworkSessionManager(self.browser_manager)
        
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
        """Callback to handle extracted card HTML."""
        try:
            stream_id = kwargs.get("stream_id")
            page_num = kwargs.get("page_num")
            card_index = kwargs.get("card_index")
            filtered_html = kwargs.get("filtered_html")
            
            filename_base = f"{stream_id}_p{page_num}_c{card_index}"
            os.makedirs(settings.STORAGE_DIR, exist_ok=True)
            html_path = os.path.abspath(os.path.join(settings.STORAGE_DIR, f"{filename_base}.html"))
            
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(filtered_html)
            
            event_data = {
                "original_stream_id": stream_id,
                "card_index": str(card_index),
                "page_num": str(page_num),
                "html_path": html_path,
                "url": kwargs.get("url"),
                "extraction_mode": kwargs.get("extraction_mode", "manual"),
                "status": "card_captured",
                "timestamp": datetime.now().isoformat()
            }
            
            await self.redis_client.xadd(settings.EXTRACTION_STREAM_NAME, event_data)
        except Exception as e:
            logger.error(f"Card processing error: {e}")

    async def process_message(self, message_id, data):
        """Executes a scraping task for a single stream message."""
        async with self.semaphore:
            logger.info(f"🚀 Processing task {message_id}")
            
            url = data.get("page_url")
            pages = int(data.get("pages", settings.DEFAULT_SCRAPE_PAGES))
            mode = data.get("extraction_mode", "manual")

            scraper = UpworkScraper(self.browser_manager, self.session_manager)
            
            try:
                async def callback(**kwargs):
                    await self._on_card_data(
                        stream_id=message_id, 
                        extraction_mode=mode, 
                        **kwargs
                    )

                await scraper.scrape_jobs(
                    product_url=url,
                    no_of_pages_to_scrape=pages,
                    on_card_data_async=callback
                )
                
                await self.redis_client.xack(self.stream_name, self.group_name, message_id)
                logger.info(f"✅ Completed task {message_id}")
            except Exception as e:
                logger.error(f"❌ Task {message_id} failed: {e}")

    async def run(self):
        """Main loop: listens for new messages in the stream."""
        await self.connect()
        
        # Browser Warmup
        logger.info("🛠️  Warming up persistent session...")
        temp_tab = await self.browser_manager.create_tab()
        try:
            await self.session_manager.verify_or_login(temp_tab)
        finally:
            await temp_tab.close()
            
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
            await self.browser_manager.close_all()

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    await RedisStreamReader().run()

if __name__ == "__main__":
    asyncio.run(main())
