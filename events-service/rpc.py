# events-service/rpc.py

import os
import json
import asyncio # <-- Make sure this is imported

import aio_pika
from aio_pika import connect_robust, Message, IncomingMessage
from dotenv import load_dotenv
from fastapi import HTTPException

# Your FastAPI business logic
from app import get_events

load_dotenv()

RABBITMQ_URL    = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
RPC_QUEUE_NAME  = "events_rpc"

# Module-level channel for publishing responses
_publish_channel: aio_pika.Channel = None

async def on_request(message: IncomingMessage):
    async with message.process():
        try:
            payload = json.loads(message.body)
            state   = payload.get("state")
            country = payload.get("country")
            if not state or not country:
                raise ValueError("Both 'state' and 'country' must be provided")

            # IMPORTANT FIX: Use asyncio.to_thread to run the synchronous get_events function
            # This prevents blocking the event loop of aio_pika.
            events = await asyncio.to_thread(get_events, state=state, country=country)
            result = {"events": events}

        except HTTPException as he:
            result = {"error": he.detail, "status_code": he.status_code}
        except Exception as e:
            result = {"error": str(e)}

        # Publish the response back via the shared _publish_channel
        await _publish_channel.default_exchange.publish(
            Message(
                body=json.dumps(result).encode(),
                correlation_id=message.correlation_id,
            ),
            routing_key=message.reply_to,
        )

async def main():
    global _publish_channel

    # 1) Connect & open a channel
    connection         = await connect_robust(RABBITMQ_URL)
    _publish_channel   = await connection.channel()

    # 2) Declare the RPC queue
    queue = await _publish_channel.declare_queue(RPC_QUEUE_NAME, durable=True)

    # 3) Start consuming requests
    await queue.consume(on_request)
    print(f"🟢 [events-service] RPC server listening on '{RPC_QUEUE_NAME}' queue.")
    try:
        await asyncio.Future()  # runs forever
    finally:
        await connection.close()

if __name__ == "__main__":
    asyncio.run(main())