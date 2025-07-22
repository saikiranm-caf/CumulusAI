# recommendation-service/consumer.py

import asyncio
import json
import aio_pika
import redis.asyncio as redis # Import async Redis client for consumer
from aio_pika import Message
from config import settings
from schemas import RecommendationRequest
from tasks import process_recommendation_task
import requests

# Initialize Redis client for the consumer process
# This client is separate from the one in main.py if consumer.py runs as a separate process.
consumer_redis_client: redis.Redis = None

async def init_consumer_redis():
    global consumer_redis_client
    consumer_redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await consumer_redis_client.ping()
        print("💡 Consumer connected to Redis")
    except redis.exceptions.ConnectionError as e:
        print(f"❌ Consumer could not connect to Redis: {e}. Ensure Redis server is running.")
        # If the consumer cannot connect to Redis, it cannot store results, so it might be
        # better to raise an exception or implement a retry mechanism here.
        raise ConnectionError(f"Consumer failed to connect to Redis on startup: {e}")

async def store_async_recommendation_in_redis(user_id: str, recommendation_text: str):
    """
    Stores the completed recommendation in Redis using the consumer's client.
    """
    if consumer_redis_client is None:
        print("❌ Redis client not initialized in consumer. Cannot store recommendation.")
        return # This case should ideally not be hit if init_consumer_redis raises an error
    
    try:
        # Store in Redis with a key like "recommendation:user_id"
        await consumer_redis_client.set(f"recommendation:{user_id}", recommendation_text)
        print(f"✅ Stored async result for user {user_id} in Redis")
    except redis.exceptions.ConnectionError as e:
        print(f"❌ Error storing recommendation for user {user_id} in Redis: {e}")
        # Consider re-queueing the message or logging to an error queue if storing fails
    except Exception as e:
        print(f"❌ Unexpected error storing recommendation for user {user_id}: {e}")


async def handle_message(msg: aio_pika.IncomingMessage):
    """
    Handles messages from the main recommendation_requests queue (non-RPC).
    Processes the request and stores the result in Redis.
    """
    async with msg.process():
        payload = json.loads(msg.body.decode())
        req = RecommendationRequest(**payload)

        # Process the request to get the prompt content
        prompt_content = await process_recommendation_task(req)

        print(f"🔥 Consumer calling LLM for user={req.user_id} with prompt:")
        print(prompt_content)

        llm_resp = await asyncio.to_thread( # Use to_thread for blocking HTTP call
            requests.post,
            "http://localhost:11434/api/generate",
            json={
                "model":  settings.LLM_MODEL, # Use LLM_MODEL from settings
                "prompt": prompt_content,
                "stream": False
            }
        )
        recommendation = llm_resp.json().get("response", "No suggestion available.")
        print(f"DEBUG: Raw LLM Response JSON: {llm_resp.json()}")
        print(f"DEBUG: Extracted Recommendation: {recommendation}")

        # This call will now store the recommendation directly in Redis via consumer's client
        await store_async_recommendation_in_redis(req.user_id, recommendation)


async def main():
    await init_consumer_redis() # Initialize Redis *before* connecting to RabbitMQ
    connection = await aio_pika.connect_robust(str(settings.RABBITMQ_URL))
    channel = await connection.channel()

    # Declare the main queue for non-RPC async requests
    queue = await channel.declare_queue(settings.QUEUE_NAME, durable=True)
    await queue.consume(handle_message)

    print(f"🟢 Consumer listening on `{settings.QUEUE_NAME}` for async requests")
    await asyncio.Future() # Keep the consumer running indefinitely


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Consumer stopped.")
        # Ensure consumer_redis_client is closed on graceful shutdown
        if consumer_redis_client:
            asyncio.run(consumer_redis_client.close())
    except Exception as e:
        print(f"Consumer error: {e}")
        if consumer_redis_client:
            asyncio.run(consumer_redis_client.close())