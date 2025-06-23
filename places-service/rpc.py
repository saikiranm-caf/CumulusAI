# places-service/rpc.py

import os
import json
import asyncio

import aio_pika
from aio_pika import connect_robust, Message, IncomingMessage
from dotenv import load_dotenv
from fastapi import HTTPException

# Your existing FastAPI handler
from app import places_api  

load_dotenv()

RABBITMQ_URL   = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
RPC_QUEUE_NAME = "places_rpc"

# Module-level channel for publishing replies
_publish_channel: aio_pika.Channel = None

async def on_request(message: IncomingMessage):
    async with message.process():
        try:
            payload = json.loads(message.body)
            lat     = payload.get("lat")
            lon     = payload.get("lon")
            query   = payload.get("query")
            if lat is None or lon is None or not query:
                raise ValueError("Missing one of: lat, lon, query")

            # Call your existing function; returns a list of place dicts
            places = places_api(lat=lat, lon=lon, query=query)
            result = {"places": places}

        except HTTPException as he:
            result = {"error": he.detail, "status_code": he.status_code}
        except Exception as e:
            result = {"error": str(e)}

        # Publish the response on the shared channel’s default_exchange
        await _publish_channel.default_exchange.publish(
            Message(
                body=json.dumps(result).encode(),
                correlation_id=message.correlation_id
            ),
            routing_key=message.reply_to
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
    print(f"🟢 [places-service] RPC server listening on '{RPC_QUEUE_NAME}'")

    # 4) Keep the service running
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
