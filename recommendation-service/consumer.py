import asyncio
import json
import aio_pika
from aio_pika import Message
from config import settings
from schemas import RecommendationRequest
from tasks import process_recommendation_task
from main import store_async_recommendation # Import the new function from main.py
import requests

async def handle_message(msg: aio_pika.IncomingMessage):
    """
    Handles messages from the main recommendation_requests queue (non-RPC).
    Processes the request and stores the result in main.py's in-memory store.
    """
    async with msg.process():
        payload = json.loads(msg.body.decode())
        req = RecommendationRequest(**payload)
        
        # Process the request to get the prompt content
        prompt_content = await process_recommendation_task(req)

        # Call the LLM with the generated prompt
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
        
        # Store the result back in the main application's in-memory store
        await store_async_recommendation(req.user_id, recommendation)


async def on_request(message: aio_pika.IncomingMessage):
    """
    Handles RPC requests (e.g., from RPC client in other services).
    Processes the request, calls LLM, and sends the result back as an RPC reply.
    """
    async with message.process():
        payload = json.loads(message.body)
        req = RecommendationRequest(**payload)

        # Process the request to get the prompt content
        prompt_content = await process_recommendation_task(req)

        # Call the LLM with the generated prompt
        print(f"🔥 Consumer calling LLM for RPC user={req.user_id} with prompt:")
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

        # build a new AMQP message, echoing that same correlation_id
        reply = Message(
            body=json.dumps({"recommendation": recommendation}).encode(), # Return a dict with 'recommendation' key
            correlation_id=message.correlation_id
        )

        # publish back to whatever queue the client asked us to reply to
        await message.channel.default_exchange.publish(
            reply,
            routing_key=message.reply_to
        )
        print(f"✅ Replied to RPC request for user {req.user_id}")

async def main():
    connection = await aio_pika.connect_robust(str(settings.RABBITMQ_URL))
    channel = await connection.channel()

    # Declare the main queue for non-RPC async requests
    queue = await channel.declare_queue(settings.QUEUE_NAME, durable=True)
    await queue.consume(handle_message)

    # Declare RPC queue for recommendation service (if it needs to receive RPC calls)
    # Based on the current setup, it only acts as an HTTP server and RabbitMQ consumer.
    # If other services were to make RPC calls to 'recommendation-service',
    # you would need an RPC queue declared here, similar to other RPC services.
    # For now, let's assume it primarily consumes from QUEUE_NAME and publishes results.

    print(f"🟢 Consumer listening on `{settings.QUEUE_NAME}` for async requests")
    print(f"🟢 Consumer ready for RPC requests (if any configured)") # Keep this as a note
    await asyncio.Future()  # keep running

if __name__ == "__main__":
    asyncio.run(main())