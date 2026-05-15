import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.db import get_async_session_factory, init_db, close_db, get_redis_client

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    # Include routers here
    # dp.include_router(...)
    print("✅ Бот готов к работе")
    asyncio.create_task(dp.start_polling(bot))
    yield
    # Shutdown
    await close_db()

app = FastAPI(lifespan=lifespan)

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Telegram Bot is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)