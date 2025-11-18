# Kazoo Game Bot

Простой Telegram-бот для игры с казу:
- при `/start` приветствует и показывает кнопки **Поехали** и **Помощь**;
- по кнопке **Поехали/Следующая песня/Начать сначала** показывает случайный трек;
- трек = текст вида `Исполнитель — Название`, количество баллов и подсказка, скрытая спойлером;
- админка на FastAPI: добавление/редактирование треков, рассылки, бэкап/restore базы.


## 1. Быстрый запуск локально

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# отредактируй .env: TELEGRAM_BOT_TOKEN, ADMIN_PASSWORD, SESSION_SECRET

python main.py
```

Бот будет работать через long polling.  
Админка: `http://localhost:8080/admin_web`

Логин в админку = пароль из `ADMIN_PASSWORD` в `.env`.


## 2. Основные файлы

- `main.py` — запуск бота (Aiogram 3) и веб-сервера (FastAPI + Uvicorn).
- `admin_web.py` — админка (треки, рассылки, бэкап/restore).
- `db.py` — работа с SQLite (aiosqlite).
- `messages.py` — тексты сообщений бота.
- `templates/` — HTML-шаблоны админки.
- `uploads/db.sqlite3` — база данных (создаётся автоматически при первом запуске).


## 3. Деплой на Railway (кратко)

1. Залей код в GitHub.
2. В Railway создай новый проект "Deploy from GitHub repo".
3. В переменные окружения Railway добавь:
   - `TELEGRAM_BOT_TOKEN` — токен бота;
   - `ADMIN_PASSWORD` — пароль входа в админку;
   - `SESSION_SECRET` — любая строка, лучше длинная случайная;
   - (по желанию) `ADMIN_IDS` — ID админов через запятую.
4. Railway сам выставит `PORT`, внутри контейнера он уже учитывается.
5. После деплоя бот начнёт принимать апдейты, админка будет по адресу:
   `https://<твой-проект>.railway.app/admin_web`
