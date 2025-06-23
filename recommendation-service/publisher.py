import json
import aio_pika
from aio_pika import Message, DeliveryMode
from schemas import RecommendationRequest
from config import settings

async def publish_recommendation_request(payload: RecommendationRequest):
    connection = await aio_pika.connect_robust(str(settings.RABBITMQ_URL))
    async with connection:
        channel = await connection.channel()
        await channel.declare_queue(settings.QUEUE_NAME, durable=True)
        msg = aio_pika.Message(
            body=payload.json().encode("utf-8"),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await channel.default_exchange.publish(msg, routing_key=settings.QUEUE_NAME)
        print(f"📤 Published recommendation request for user={payload.user_id}")
