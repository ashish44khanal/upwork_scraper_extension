
import asyncio
import redis.asyncio as aioredis

async def test_redis_features():
    redis_client = aioredis.Redis(host='localhost', port=6379, decode_responses=True)
    stream_name = "test_fault_stream"
    group_name = "test_group"
    consumer_name = "test_consumer"
    
    try:
        # 1. Test Trimming
        print("Testing Stream Trimming...")
        await redis_client.delete(stream_name)
        
        for i in range(15):
            await redis_client.xadd(stream_name, {"index": str(i)}, maxlen=10, approximate=False)
        
        length = await redis_client.xlen(stream_name)
        print(f"Total length after 15 additions with maxlen=10: {length}")
        assert length == 10
        
        # 2. Test XAUTOCLAIM
        print("\nTesting XAUTOCLAIM...")
        # Use a fresh stream for claiming test
        claim_stream = "test_claim_stream"
        await redis_client.delete(claim_stream)
        try:
            await redis_client.xgroup_create(claim_stream, group_name, id="0", mkstream=True)
        except:
            pass
            
        # Add and read without ACK
        msg_id = await redis_client.xadd(claim_stream, {"task": "test_stale"})
        await redis_client.xreadgroup(group_name, "another_worker", {claim_stream: ">"}, count=1)
        
        # Claim it immediately
        result = await redis_client.xautoclaim(claim_stream, group_name, consumer_name, 0, "0-0")
        claimed_msgs = result[1]
        print(f"msg_id: {msg_id}")
        print(f"Claimed message: {claimed_msgs[0][0] if claimed_msgs else 'NONE'}")
        assert claimed_msgs[0][0] == msg_id
        
        # 3. Test XPENDING (times_delivered)
        print("\nTesting Delivery Count...")
        pending = await redis_client.xpending_range(claim_stream, group_name, min=msg_id, max=msg_id, count=1)
        delivery_count = pending[0]['times_delivered']
        print(f"Times delivered: {delivery_count}")
        assert delivery_count >= 1

        print("\n✅ All Redis fault tolerance tests passed!")

    finally:
        await redis_client.delete(stream_name)
        await redis_client.delete("test_claim_stream")
        await redis_client.close()

if __name__ == "__main__":
    asyncio.run(test_redis_features())
