# book-blog-service/rpc.py

import os
import json
import asyncio

import aio_pika
from aio_pika import connect_robust, Message, IncomingMessage
from dotenv import load_dotenv
from fastapi import HTTPException

# Import your FastAPI handler from app.py
from app import get_blogs  

load_dotenv()

RABBITMQ_URL   = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
RPC_QUEUE_NAME = "blogs_rpc"

# Module-level channel for publishing replies
_publish_channel: aio_pika.Channel = None

async def on_request(message: IncomingMessage):
    async with message.process():
        try:
            payload    = json.loads(message.body)
            query      = payload.get("query", "technology")
            language   = payload.get("language", "en")
            max_results = payload.get("max_results", 10)

            # Call your existing handler
            response = get_blogs(
                query=query,
                language=language,
                max_results=max_results
            )

        except HTTPException as he:
            response = {"error": he.detail, "status_code": he.status_code}
        except Exception as e:
            response = {"error": str(e)}

        # Publish the reply via the shared channel’s default_exchange
        await _publish_channel.default_exchange.publish(
            Message(
                body=json.dumps(response).encode(),
                correlation_id=message.correlation_id
            ),
            routing_key=message.reply_to
        )

async def main():
    global _publish_channel

    # 1) Connect & open a channel
    connection       = await connect_robust(RABBITMQ_URL)
    _publish_channel = await connection.channel()

    # 2) Declare the RPC queue
    queue = await _publish_channel.declare_queue(RPC_QUEUE_NAME, durable=True)

    # 3) Start consuming RPC requests
    await queue.consume(on_request)
    print(f"🟢 [book-blog-service] RPC server listening on '{RPC_QUEUE_NAME}'")

    # 4) Keep the service running
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
