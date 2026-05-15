import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.db import get_async_session_factory, init_db, close_db
from bot.redis_client import get_redis_client

# ... other imports

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await initialize()
    yield
    # Shutdown
    await shutdown()

app = FastAPI(lifespan=lifespan)

async def initialize():
    try:
        await init_db()
        redis = get_redis_client()
        # ... other init
    except Exception as e:
        logging.error(f'Initialization failed: {e}')
        raise

async def shutdown():
    await close_db()

# Health checks
@app.get('/health')
def health():
    return {'status': 'ok'}

@app.get('/health/detailed')
async def health_detailed():
    redis = get_redis_client()
    redis_ok = await redis.ping()
    db_ok = True  # check db
    return {
        'status': 'ok',
        'redis': 'up' if redis_ok else 'down',
        'database': 'up' if db_ok else 'down',
        'timestamp': asyncio.get_event_loop().time()
    }

# ... rest of the app
