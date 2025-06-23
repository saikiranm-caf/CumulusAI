# weather-service/rpc.py

import os
import json
import asyncio
from aio_pika import connect_robust, Message, IncomingMessage
from dotenv import load_dotenv
from app import get_weather  # your sync function returning a dict

load_dotenv()
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
RPC_QUEUE    = "weather_rpc"

# Will hold our publishing channel
_publish_channel = None

async def on_request(msg: IncomingMessage):
    async with msg.process():
        # 1️⃣ parse request
        request = json.loads(msg.body.decode())
        lat, lon = request["lat"], request["lon"]

        # 2️⃣ call your sync business logic
        reply_data = get_weather(lat, lon)

        # 3️⃣ publish on the global channel’s default_exchange
        await _publish_channel.default_exchange.publish(
            Message(
                body=json.dumps(reply_data).encode(),
                correlation_id=msg.correlation_id,
            ),
            routing_key=msg.reply_to,
        )

async def main():
    global _publish_channel

    # 1️⃣ connect & create channel
    conn    = await connect_robust(RABBITMQ_URL)
    _publish_channel = await conn.channel()

    # 2️⃣ declare RPC queue
    queue = await _publish_channel.declare_queue(RPC_QUEUE, durable=True)

    # 3️⃣ start consuming
    await queue.consume(on_request)
    print(f"🛰️ weather-service RPC listening on `{RPC_QUEUE}`")

    # 4️⃣ keep the process alive
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
