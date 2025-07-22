import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    APP_NAME: str        = "recommendation-service"
    PORT: int            = int(os.getenv("PORT", 8007))
    GATEWAY_URL: str     = os.getenv("GATEWAY_URL", "http://localhost:8000")
    RABBITMQ_URL: str    = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
    QUEUE_NAME: str      = os.getenv("QUEUE_NAME", "recommendation_requests")
    LLM_MODEL: str       = os.getenv("LLM_MODEL", "mistral:7b-instruct")
    REDIS_URL: str       = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    MODEL_PATH: str      = os.getenv("MODEL_PATH", "C:/DevProjects/deviceai-microservices/training-service/recommendation_model.h5")

    class Config:
       env_file = ".env"
       env_file_encoding = "utf-8"


    # per-service RPC queue names
    WEATHER_RPC_QUEUE: str     = "weather_rpc"
    LOCATION_RPC_QUEUE: str    = "location_rpc"
    USER_PREFS_RPC_QUEUE: str  = "user_preferences_rpc"
    EVENTS_RPC_QUEUE: str      = "events_rpc"
    PLACES_RPC_QUEUE: str      = "places_rpc"
    BLOGS_RPC_QUEUE: str       = "blogs_rpc"

settings = Settings()
