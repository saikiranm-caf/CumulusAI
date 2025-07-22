import os, json, asyncio
from aio_pika import connect_robust, Message, IncomingMessage
from dotenv import load_dotenv
from app import get_location  # your synchronous lookup function

load_dotenv()
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
RPC_QUEUE    = "location_rpc"

# module‐level variable for publishing
_publish_channel = None

async def on_request(msg: IncomingMessage):
    async with msg.process():
        # parse the incoming RPC request
        payload = json.loads(msg.body.decode())
        lat = payload.get("lat")
        lon = payload.get("lon")
        time = payload.get("time")
        user_id = payload.get("user_id")
        age = payload.get("age")
        gender = payload.get("gender")
        motion_state = payload.get("motion_state")

        # Validate required parameters
        if not all([lat, lon, time, user_id, age, gender]):
            raise ValueError("Missing required parameters: lat, lon, time, user_id, age, or gender")

        # Call your sync business logic with all parameters
        result = await asyncio.to_thread(get_location, lat, lon, time, user_id, age, gender, motion_state)

        # Publish the reply back on the shared channel’s default_exchange
        await _publish_channel.default_exchange.publish(
            Message(
                body=json.dumps(result).encode(),
                correlation_id=msg.correlation_id
            ),
            routing_key=msg.reply_to
        )

async def main():
    global _publish_channel

    # 1. Connect & open a channel
    conn = await connect_robust(RABBITMQ_URL)
    _publish_channel = await conn.channel()

    # 2. Declare your RPC queue
    queue = await _publish_channel.declare_queue(RPC_QUEUE, durable=True)

    # 3. Start consuming
    await queue.consume(on_request)
    print(f"🟢 [location-service] RPC server listening on '{RPC_QUEUE}'")

    # 4. Block forever
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())