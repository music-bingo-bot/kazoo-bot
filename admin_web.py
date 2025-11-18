import os
import tempfile
import zipfile
from typing import Optional

from fastapi import FastAPI, Request, UploadFile, Form
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    PlainTextResponse,
    FileResponse,
)
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_303_SEE_OTHER
from aiogram import Bot

from db import (
    list_tracks,
    create_track,
    update_track,
    delete_track,
    list_broadcasts,
    create_broadcast,
    mark_broadcast_sent,
    get_all_users,
    get_track,
)


TEMPLATES = Jinja2Templates(directory="templates")


def get_admin_password() -> str:
    pwd = os.getenv("ADMIN_PASSWORD", "")
    if not pwd:
        raise RuntimeError("ADMIN_PASSWORD не задан")
    return pwd


async def ensure_admin(request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse("/admin_web/login", status_code=HTTP_303_SEE_OTHER)


def create_app(bot: Bot) -> FastAPI:
    app = FastAPI()

    secret_key = os.getenv("SESSION_SECRET", "dev-secret-change-me")
    app.add_middleware(SessionMiddleware, secret_key=secret_key)
    app.state.bot = bot

    # ---------- Auth ----------
    @app.get("/admin_web/login", response_class=HTMLResponse)
    async def login_form(request: Request):
        return TEMPLATES.TemplateResponse(
            "login.html",
            {"request": request, "error": None},
        )

    @app.post("/admin_web/login", response_class=HTMLResponse)
    async def login_post(request: Request, password: str = Form(...)):
        admin_password = get_admin_password()
        if password != admin_password:
            return TEMPLATES.TemplateResponse(
                "login.html",
                {"request": request, "error": "Неверный пароль"},
            )
        request.session["is_admin"] = True
        return RedirectResponse("/admin_web", status_code=HTTP_303_SEE_OTHER)

    @app.get("/admin_web/logout")
    async def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/admin_web/login", status_code=HTTP_303_SEE_OTHER)

    # ---------- Tracks ----------
@app.get("/admin_web", response_class=HTMLResponse)
async def index(request: Request):
    await require_admin(request)
    tracks = await list_tracks()
    restore_status = request.query_params.get("restore")

    return TEMPLATES.TemplateResponse(
        "index.html",
        {
            "request": request,
            "tracks": tracks,
            "restore_status": restore_status,
        },
    )

    @app.post("/admin_web/tracks/new")
    async def add_track(
        request: Request,
        title: str = Form(...),
        points: int = Form(...),
        hint: Optional[str] = Form(None),
    ):
        await ensure_admin(request)
        title = title.strip()
        if not title:
            return RedirectResponse("/admin_web", status_code=HTTP_303_SEE_OTHER)
        try:
            points_val = int(points)
        except ValueError:
            points_val = 1
        await create_track(title, points_val, hint.strip() if hint else None)
        return RedirectResponse("/admin_web", status_code=HTTP_303_SEE_OTHER)

    @app.post("/admin_web/tracks/{track_id}/edit")
    async def edit_track(
        request: Request,
        track_id: int,
        title: str = Form(...),
        points: int = Form(...),
        hint: Optional[str] = Form(None),
        is_active: Optional[str] = Form(None),
    ):
        await ensure_admin(request)
        row = await get_track(track_id)
        if not row:
            return RedirectResponse("/admin_web", status_code=HTTP_303_SEE_OTHER)

        try:
            points_val = int(points)
        except ValueError:
            points_val = 1

        await update_track(
            track_id=track_id,
            title=title.strip(),
            points=points_val,
            hint=hint.strip() if hint else None,
            is_active=bool(is_active),
        )
        return RedirectResponse("/admin_web", status_code=HTTP_303_SEE_OTHER)

    @app.post("/admin_web/tracks/{track_id}/delete")
    async def remove_track(request: Request, track_id: int):
        await ensure_admin(request)
        await delete_track(track_id)
        return RedirectResponse("/admin_web", status_code=HTTP_303_SEE_OTHER)

    # ---------- Broadcasts ----------
    @app.get("/admin_web/broadcasts", response_class=HTMLResponse)
    async def broadcasts_page(request: Request):
        await ensure_admin(request)
        broadcasts = await list_broadcasts()
        sent = request.query_params.get("sent")
        failed = request.query_params.get("failed")
        return TEMPLATES.TemplateResponse(
            "broadcasts_list.html",
            {
                "request": request,
                "broadcasts": broadcasts,
                "sent": sent,
                "failed": failed,
            },
        )

    @app.get("/admin_web/broadcasts/new", response_class=HTMLResponse)
    async def broadcasts_new_form(request: Request):
        await ensure_admin(request)
        return TEMPLATES.TemplateResponse(
            "broadcasts_new.html",
            {"request": request, "error": None},
        )

    @app.post("/admin_web/broadcasts/new", response_class=HTMLResponse)
    async def broadcasts_new_submit(request: Request, text: str = Form(...)):
        await ensure_admin(request)
        text = text.strip()
        if not text:
            return TEMPLATES.TemplateResponse(
                "broadcasts_new.html",
                {"request": request, "error": "Текст сообщения пустой"},
            )

        bot: Bot = request.app.state.bot
        users = await get_all_users()
        if not users:
            return TEMPLATES.TemplateResponse(
                "broadcasts_new.html",
                {"request": request, "error": "Нет пользователей для рассылки"},
            )

        bid = await create_broadcast(text)

        sent = 0
        failed = 0
        for uid in users:
            try:
                await bot.send_message(uid, text)
                sent += 1
            except Exception:
                failed += 1

        await mark_broadcast_sent(bid)
        return RedirectResponse(
            f"/admin_web/broadcasts?sent={sent}&failed={failed}",
            status_code=HTTP_303_SEE_OTHER,
        )

    # ---------- Backup / Restore ----------
@app.get("/admin_web/backup")
async def backup(request: Request):
    await ensure_admin(request)
    base = "uploads"
    os.makedirs(base, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)

    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if os.path.isdir(base):
            for root_dir, _dirs, files in os.walk(base):
                for name in files:
                    full = os.path.join(root_dir, name)
                    # в архиве будут пути вида: uploads/...
                    arc = os.path.relpath(full, start=os.path.dirname(base))
                    zf.write(full, arcname=arc)

    return FileResponse(
        tmp_path,
        filename="backup_uploads.zip",
        media_type="application/zip",
    )

@app.post("/admin_web/restore")
async def restore(request: Request, archive: UploadFile):
    await ensure_admin(request)

    if not archive or not archive.filename:
        # не выбрали файл
        return RedirectResponse(
            "/admin_web?restore=missing",
            status_code=HTTP_303_SEE_OTHER,
        )

    base = "uploads"
    os.makedirs(base, exist_ok=True)

    # сохраняем загруженный архив во временный файл
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp_path = tmp.name
    tmp.close()

    async with aiofiles.open(tmp_path, "wb") as f:
        while chunk := await archive.read(64 * 1024):
            await f.write(chunk)

    # распаковываем поверх (перезаписывает db.sqlite3 и т.п.)
    with zipfile.ZipFile(tmp_path, "r") as zf:
        for member in zf.infolist():
            target = os.path.normpath(os.path.join(".", member.filename))
            # безопасность: разрешаем только uploads/*
            if not target.startswith(("uploads", "./uploads")):
                continue
            zf.extract(member, ".")

    try:
        os.remove(tmp_path)
    except Exception:
        pass

    return RedirectResponse(
        "/admin_web?restore=ok",
        status_code=HTTP_303_SEE_OTHER,
    )

    # ---------- Health ----------
    @app.api_route("/health", methods=["GET", "HEAD"])
    async def health_edge():
        return PlainTextResponse("ok")

    @app.get("/healthz")
    async def healthz():
        return PlainTextResponse("ok")

    return app
