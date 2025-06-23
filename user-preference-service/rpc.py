import os
import json
import asyncio

import aio_pika
from aio_pika import connect_robust, Message, IncomingMessage
from dotenv import load_dotenv

from service import fetch_user_preferences  # your data-access function

load_dotenv()

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
RPC_QUEUE    = "user_preferences_rpc"

# Module-level channel used to publish RPC responses
global _publish_channel
_publish_channel: aio_pika.Channel = None

async def on_request(message: IncomingMessage):
    """
    Handle incoming RPC requests for user preferences.
    Expected payload: { "user_id": <str> }
    Replies with: { "activities": [...] } or { "error": <msg> }
    """
    async with message.process():
        try:
            payload = json.loads(message.body)
            user_id = payload.get("user_id")
            # Fetch the activities list for the given user_id
            activities = fetch_user_preferences(user_id)
            # Wrap under "activities" key for consistency
            result = {"activities": activities}
        except Exception as e:
            result = {"error": str(e)}

        # Construct the response message
        response = Message(
            body=json.dumps(result).encode(),
            correlation_id=message.correlation_id
        )
        # Publish via the shared channel's default exchange
        await _publish_channel.default_exchange.publish(
            response,
            routing_key=message.reply_to
        )

async def main():
    global _publish_channel

    # 1) Connect to RabbitMQ and open a channel
    connection = await connect_robust(RABBITMQ_URL)
    _publish_channel = await connection.channel()

    # 2) Declare the RPC queue
    queue = await _publish_channel.declare_queue(RPC_QUEUE, durable=True)

    # 3) Start consuming incoming RPC requests
    await queue.consume(on_request)
    print(f"🟢 [user-preference-service] RPC server listening on '{RPC_QUEUE}'")

    # 4) Keep the service running
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
