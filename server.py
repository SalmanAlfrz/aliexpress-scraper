import time
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from scraper import close_browser, init_browser, scrape

ALLOWED_HOSTS = {"pt.aliexpress.com", "www.aliexpress.com", "aliexpress.com"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_browser()
    print("\n  AliExpress Brasil Scraper")
    print("  POST http://localhost:3001/api/aliexpress/sync")
    print("  GET  http://localhost:3001/health\n")
    yield
    await close_browser()


app = FastAPI(title="AliExpress Brasil Scraper", lifespan=lifespan)


class ScrapeRequest(BaseModel):
    url: str


@app.post("/api/aliexpress/sync")
async def sync_scrape(req: ScrapeRequest):
    parsed = urlparse(req.url)

    if parsed.hostname not in ALLOWED_HOSTS:
        return {"success": False, "error": f"Host \"{parsed.hostname}\" not allowed"}

    t = time.time()
    try:
        result = await scrape(req.url)
        return {**result, "duration_ms": int((time.time() - t) * 1000)}
    except Exception as e:
        return {"success": False, "error": str(e), "duration_ms": int((time.time() - t) * 1000)}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=3001, reload=True)
