import os
import tempfile
import zipfile
from typing import Optional, List

from fastapi import FastAPI, Request, UploadFile, Form, File
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    PlainTextResponse,
    FileResponse,
    Response,
)
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_303_SEE_OTHER
from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto

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
    create_broadcast_file,
    delete_broadcast,
)

TEMPLATES = Jinja2Templates(directory="templates")


def get_admin_password() -> str:
    pwd = os.getenv("ADMIN_PASSWORD", "")
    if not pwd:
        raise RuntimeError("ADMIN_PASSWORD не задан")
    return pwd


async def ensure_admin(request: Request) -> Optional[Response]:
    if not request.session.get("is_admin"):
        return RedirectResponse("/admin_web/login", status_code=HTTP_303_SEE_OTHER)
    return None


def create_app(bot: Bot) -> FastAPI:
    app = FastAPI()

    secret_key = os.getenv("SESSION_SECRET", "dev-secret-change-me")
    app.add_middleware(SessionMiddleware, secret_key=secret_key)
    app.state.bot = bot

    # ---------- AUTH ----------

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

    # ---------- TRACKS ----------

    @app.get("/admin_web", response_class=HTMLResponse)
    async def index(request: Request):
        if (resp := await ensure_admin(request)) is not None:
            return resp

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
        if (resp := await ensure_admin(request)) is not None:
            return resp

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
        if (resp := await ensure_admin(request)) is not None:
            return resp

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
        if (resp := await ensure_admin(request)) is not None:
            return resp

        await delete_track(track_id)
        return RedirectResponse("/admin_web", status_code=HTTP_303_SEE_OTHER)

    # ---------- BROADCASTS ----------

    @app.get("/admin_web/broadcasts", response_class=HTMLResponse)
    async def broadcasts_page(request: Request):
        if (resp := await ensure_admin(request)) is not None:
            return resp

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

    @app.post("/admin_web/broadcasts/{broadcast_id}/delete")
    async def broadcasts_delete(request: Request, broadcast_id: int):
        if (resp := await ensure_admin(request)) is not None:
            return resp

        await delete_broadcast(broadcast_id)
        return RedirectResponse("/admin_web/broadcasts", status_code=HTTP_303_SEE_OTHER)

    @app.get("/admin_web/broadcasts/new", response_class=HTMLResponse)
    async def broadcasts_new_form(request: Request):
        if (resp := await ensure_admin(request)) is not None:
            return resp

        return TEMPLATES.TemplateResponse(
            "broadcasts_new.html",
            {"request": request, "error": None},
        )

    async def _save_files_for_broadcast(
        broadcast_id: int,
        files: List[UploadFile],
        kind: str,
    ) -> List[str]:
        saved_paths: List[str] = []
        base_dir = os.path.join("uploads", "broadcasts", str(broadcast_id), kind)
        os.makedirs(base_dir, exist_ok=True)

        for up in files:
            if not up or not up.filename:
                continue
            data = await up.read()
            if not data:
                continue

            filename = up.filename.replace("/", "_").replace("\\", "_")
            path = os.path.join(base_dir, filename)
            with open(path, "wb") as f:
                f.write(data)

            rel_path = path
            await create_broadcast_file(broadcast_id, kind, rel_path)
            saved_paths.append(rel_path)

        return saved_paths

    @app.post("/admin_web/broadcasts/new", response_class=HTMLResponse)
    async def broadcasts_new_submit(
        request: Request,
        title: str = Form(""),
        text: str = Form(""),
        images: List[UploadFile] = File(default=[]),
        videos: List[UploadFile] = File(default=[]),
        files: List[UploadFile] = File(default=[]),
    ):
        if (resp := await ensure_admin(request)) is not None:
            return resp

        title = title.strip()
        body = text.strip()

        has_any_media = any(
            (images and len(images) > 0, videos and len(videos) > 0, files and len(files) > 0)
        )

        if not title and not body and not has_any_media:
            return TEMPLATES.TemplateResponse(
                "broadcasts_new.html",
                {"request": request, "error": "Нужно заполнить заголовок/текст или добавить медиа"},
            )

        if title and body:
            full_text = f"{title}\n\n{body}".strip()
        else:
            full_text = (title or body).strip()

        bot: Bot = request.app.state.bot
        users = await get_all_users()
        if not users:
            return TEMPLATES.TemplateResponse(
                "broadcasts_new.html",
                {"request": request, "error": "Нет пользователей для рассылки"},
            )

        bid = await create_broadcast(full_text)

        image_paths = await _save_files_for_broadcast(bid, images, "photo") if images else []
        video_paths = await _save_files_for_broadcast(bid, videos, "video") if videos else []
        file_paths = await _save_files_for_broadcast(bid, files, "file") if files else []

        sent = 0
        failed = 0

        for uid in users:
            user_failed = False
            caption_used = False  # уже прикрепляли текст как caption?

            # 1) Картинки — как и было: текст в подписи к первой
            try:
                if image_paths:
                    if len(image_paths) == 1:
                        await bot.send_photo(
                            uid,
                            FSInputFile(image_paths[0]),
                            caption=full_text or None,
                        )
                        if full_text:
                            caption_used = True
                    else:
                        media = []
                        for i, p in enumerate(image_paths):
                            cap = full_text if i == 0 and full_text else None
                            if cap:
                                caption_used = True
                            media.append(
                                InputMediaPhoto(
                                    media=FSInputFile(p),
                                    caption=cap,
                                )
                            )
                        await bot.send_media_group(uid, media)

            except Exception as e:
                print(f"[broadcast] photo/text error for {uid}: {e}")
                user_failed = True

            # 2) Видео — если нет картинок, текст идёт как подпись к первому видео
            for i, p in enumerate(video_paths):
                cap = None
                if full_text and not caption_used and i == 0:
                    cap = full_text
                    caption_used = True
                try:
                    await bot.send_video(uid, FSInputFile(p), caption=cap)
                except Exception as e:
                    # fallback: пробуем как документ (вдруг слишком большой/нестандартный контейнер)
                    print(f"[broadcast] video error for {uid}, fallback to document: {e}")
                    try:
                        await bot.send_document(uid, FSInputFile(p), caption=cap)
                    except Exception as e2:
                        print(f"[broadcast] video-document error for {uid}: {e2}")
                        user_failed = True

            # 3) Файлы (аудио/доки) — если нет ни картинок, ни видео, текст идёт в подписи к первому файлу
            audio_exts = {".mp3", ".ogg", ".wav", ".m4a"}
            for i, p in enumerate(file_paths):
                cap = None
                if full_text and not caption_used and i == 0:
                    cap = full_text
                    caption_used = True

                ext = os.path.splitext(p)[1].lower()
                try:
                    if ext in audio_exts:
                        await bot.send_audio(uid, FSInputFile(p), caption=cap)
                    else:
                        await bot.send_document(uid, FSInputFile(p), caption=cap)
                except Exception as e:
                    print(f"[broadcast] file error for {uid}: {e}")
                    user_failed = True

            # 4) Если ни одной медиа не было вообще — отправляем просто текст
            if not caption_used and not (image_paths or video_paths or file_paths) and full_text:
                try:
                    await bot.send_message(uid, full_text)
                except Exception as e:
                    print(f"[broadcast] text-only error for {uid}: {e}")
                    user_failed = True

            if user_failed:
                failed += 1
            else:
                sent += 1

        await mark_broadcast_sent(bid)
        return RedirectResponse(
            f"/admin_web/broadcasts?sent={sent}&failed={failed}",
            status_code=HTTP_303_SEE_OTHER,
        )

    # ---------- BACKUP / RESTORE ----------

    @app.get("/admin_web/backup")
    async def backup(request: Request):
        if (resp := await ensure_admin(request)) is not None:
            return resp

        base = "uploads"
        os.makedirs(base, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(suffix=".zip")
        os.close(fd)

        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if os.path.isdir(base):
                for root_dir, _dirs, files in os.walk(base):
                    for name in files:
                        full = os.path.join(root_dir, name)
                        rel = os.path.relpath(full, start=".")
                        zf.write(full, arcname=rel)

        return FileResponse(
            tmp_path,
            filename="kazoo-backup.zip",
            media_type="application/zip",
        )

    @app.post("/admin_web/restore")
    async def restore(request: Request, archive: UploadFile):
        if (resp := await ensure_admin(request)) is not None:
            return resp

        if not archive or not archive.filename:
            return RedirectResponse(
                "/admin_web?restore=missing",
                status_code=HTTP_303_SEE_OTHER,
            )

        base = "uploads"
        os.makedirs(base, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        with open(tmp_path, "wb") as f:
            f.write(await archive.read())

        with zipfile.ZipFile(tmp_path, "r") as zf:
            for member in zf.infolist():
                member_path = os.path.normpath(member.filename)
                if not member_path.startswith("uploads"):
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

    # ---------- HEALTH ----------

    @app.api_route("/health", methods=["GET", "HEAD"])
    async def health_edge():
        return PlainTextResponse("ok")

    @app.get("/healthz")
    async def healthz():
        return PlainTextResponse("ok")

    return app
