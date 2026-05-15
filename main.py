import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.db import get_async_session_factory, init_db, close_db, get_redis_client

# ... (остальной код main.py)