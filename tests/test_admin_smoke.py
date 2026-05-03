import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

# Устанавливаем переменные окружения до импорта приложения
import os
os.environ["SECRET_KEY"] = "test_secret_key_for_admin_at_least_32_chars"
os.environ["ADMIN_PASSWORD"] = "testpass"
os.environ["BOT_TOKEN"] = "dummy"
os.environ["ADMIN_ID"] = "1"
os.environ["MAIN_GROUP_ID"] = "-100"
os.environ["THREAD_SALES"] = "1"
os.environ["THREAD_ASSORTMENT"] = "2"
os.environ["THREAD_ARRIVAL"] = "3"
os.environ["THREAD_PREORDER"] = "4"
os.environ["DATABASE_URL"] = "postgresql://none/none"

# Мокаем пул БД на уровне модуля до импорта приложения
import bot.db
bot.db.get_pool = AsyncMock()

from web_admin.main import app  # noqa: E402
from web_admin.auth import login, logout  # noqa: E402

client = TestClient(app)


def test_login_page():
    response = client.get("/admin/auth/login")
    assert response.status_code == 200
    assert "Вход в админку" in response.text


def test_login_failure():
    response = client.post("/admin/auth/login", data={"password": "wrong"})
    assert response.status_code == 200
    assert "Неверный пароль" in response.text


def test_login_success():
    response = client.post("/admin/auth/login", data={"password": "testpass"})
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/dashboard"


def test_dashboard_redirect_when_not_authenticated():
    response = client.get("/admin/dashboard", follow_redirects=False)
    assert response.status_code == 307 or response.status_code == 303


def test_dashboard_authenticated():
    with client:
        client.post("/admin/auth/login", data={"password": "testpass"})
        response = client.get("/admin/dashboard")
        assert response.status_code == 200
        assert "Дашборд" in response.text


def test_clients_page_authenticated():
    with client:
        client.post("/admin/auth/login", data={"password": "testpass"})
        response = client.get("/admin/clients")
        assert response.status_code == 200
        assert "Клиенты" in response.text


def test_assortment_page_authenticated():
    with client:
        client.post("/admin/auth/login", data={"password": "testpass"})
        response = client.get("/admin/assortment")
        assert response.status_code == 200
        assert "Ассортимент" in response.text


def test_sold_page_authenticated():
    with client:
        client.post("/admin/auth/login", data={"password": "testpass"})
        response = client.get("/admin/sold")
        assert response.status_code == 200
        assert "Проданные товары" in response.text


def test_stats_page_authenticated():
    with client:
        client.post("/admin/auth/login", data={"password": "testpass"})
        response = client.get("/admin/stats")
        assert response.status_code == 200
        assert "Статистика" in response.text


def test_logout():
    with client:
        client.post("/admin/auth/login", data={"password": "testpass"})
        response = client.get("/admin/auth/logout", follow_redirects=False)
        assert response.status_code == 303
        response = client.get("/admin/dashboard", follow_redirects=False)
        assert response.status_code == 307 or response.status_code == 303
