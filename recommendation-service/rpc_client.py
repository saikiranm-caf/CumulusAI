# recommendation-service/rpc_client.py
import os, json, uuid, asyncio
import aio_pika
from config import settings

# Increase the default timeout for RPC calls, especially for potentially slow services.
# A 120-second (2 minute) timeout should be sufficient, given event scraping can take time.
async def rpc_call(queue_name: str, payload: dict, timeout: float = 120.0): # Increased timeout
    conn = await aio_pika.connect_robust(str(settings.RABBITMQ_URL))
    channel = await conn.channel()
    callback_q = await channel.declare_queue(exclusive=True)
    corr_id   = str(uuid.uuid4())
    future    = asyncio.get_running_loop().create_future()

    async def on_response(msg: aio_pika.IncomingMessage):
        if msg.correlation_id == corr_id:
            # Check if the future is already done (e.g., due to a timeout)
            if not future.done():
                future.set_result(json.loads(msg.body))
            else:
                print(f"DEBUG: Received late RPC response for {corr_id}, future already done.")
                # You might want to log the message body here for debugging if needed
                # print(f"DEBUG: Late message body: {msg.body.decode()}")

    await callback_q.consume(on_response)

    await channel.default_exchange.publish(
        aio_pika.Message(
            body=json.dumps(payload).encode(),
            correlation_id=corr_id,
            reply_to=callback_q.name,
        ),
        routing_key=queue_name,
    )
    return await asyncio.wait_for(future, timeout)