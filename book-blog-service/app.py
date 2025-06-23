from fastapi import FastAPI, Query
from typing import List
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

NEWS_API_KEY = os.getenv("NEWS_API_KEY", "your_api_key_here")

port = int(os.getenv("PORT", 8006))

@app.get("/blogs")
def get_blogs(query: str = "technology", language: str = "en", max_results: int = 10):
    print(f"🔥Control at blogs")
    url = (
        f"https://newsapi.org/v2/everything?q={query}"
        f"&language={language}&sortBy=publishedAt&pageSize={max_results}&apiKey={NEWS_API_KEY}"
    )
    response = requests.get(url)
    data = response.json()

    if data.get("status") != "ok":
        return {"error": "Failed to fetch data from NewsAPI"}

    articles = data.get("articles", [])
    return {
        "total_results": len(articles),
        "blogs": [
            {
                "title": article.get("title"),
                "description": article.get("description"),
                "url": article.get("url"),
                "image": article.get("urlToImage"),
                "published": article.get("publishedAt"),
                "source": article.get("source", {}).get("name"),
            }
            for article in articles
        ],
    }
