from fastapi import FastAPI, HTTPException
import requests
import os
from dotenv import load_dotenv
load_dotenv()  
app = FastAPI()

port = int(os.getenv("PORT", 8001))

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

@app.get("/weather")
def get_weather(lat: float, lon: float):
    print(f"🔥Control at weather")
    if not WEATHER_API_KEY:
        raise HTTPException(status_code=500, detail="Missing WEATHER_API_KEY environment variable")
    
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
    
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        weather = {
            "temperature": data["main"]["temp"],
            "description": data["weather"][0]["description"]
        }
        return weather
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
