from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .auth import ensure_password_hash, password_is_hashed, verify_password
from .config import AdminWebSettings, load_admin_settings
from .images import remove_catalog_image_files
from src.catalog_media import catalog_media_path, process_catalog_image_bytes
from .repository import AdminRepository

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
CATALOG_CATEGORIES = ("style", "facade", "countertop", "hardware")
TIMEZONE_OPTIONS = (
    "Asia/Irkutsk",
    "Asia/Krasnoyarsk",
    "Asia/Novosibirsk",
    "Asia/Yekaterinburg",
    "Europe/Moscow",
    "UTC",
)


def create_app(settings: AdminWebSettings | None = None) -> FastAPI:
    cfg = settings or load_admin_settings()
    cfg.uploads_dir.mkdir(parents=True, exist_ok=True)
    repo = AdminRepository(cfg.database_url)
    repo.ensure_schema()

    def current_password_hash() -> str:
        stored = repo.get_admin_password_hash()
        if stored:
            return stored
        return ensure_password_hash(cfg.admin_password)

    app = FastAPI(title="АртКухня Admin", docs_url=None, redoc_url=None)
    app.add_middleware(SessionMiddleware, secret_key=cfg.session_secret, max_age=60 * 60 * 12)
    app.mount("/static", StaticFiles(directory=str(cfg.static_dir)), name="static")
    app.mount("/uploads", StaticFiles(directory=str(cfg.uploads_dir)), name="uploads")
    templates = Jinja2Templates(directory=str(cfg.templates_dir))

    def is_authenticated(request: Request) -> bool:
        return bool(request.session.get("authenticated"))

    def require_auth(request: Request) -> None:
        if not is_authenticated(request):
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/login", response_class=HTMLResponse, response_model=None)
    async def login_page(request: Request) -> HTMLResponse:
        if is_authenticated(request):
            return RedirectResponse(url="/", status_code=302)  # type: ignore[return-value]
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": None,
                "brand": "АртКухня",
                "show_default_hint": not repo.is_password_changed(),
            },
        )

    @app.post("/login")
    async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
        if username.strip() == cfg.admin_user and verify_password(password, current_password_hash()):
            request.session["authenticated"] = True
            request.session["username"] = username.strip()
            return RedirectResponse(url="/", status_code=302)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Неверный логин или пароль", "brand": "АртКухня", "show_default_hint": not repo.is_password_changed()},
            status_code=401,
        )

    @app.post("/logout")
    async def logout(request: Request):
        request.session.clear()
        return RedirectResponse(url="/login", status_code=302)

    @app.get("/", response_class=HTMLResponse, response_model=None)
    async def dashboard(request: Request):
        if not is_authenticated(request):
            return RedirectResponse(url="/login", status_code=302)
        settings_map = repo.list_settings()
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "username": request.session.get("username", cfg.admin_user),
                "brand": settings_map.get("brand_name", "АртКухня"),
                "city": settings_map.get("brand_city", "Иркутск"),
                "timezones": TIMEZONE_OPTIONS,
                "categories": CATALOG_CATEGORIES,
            },
        )

    @app.get("/api/summary")
    async def api_summary(request: Request) -> dict[str, Any]:
        require_auth(request)
        return repo.get_summary()

    @app.get("/api/settings")
    async def api_settings(request: Request) -> dict[str, str]:
        require_auth(request)
        return repo.list_settings()

    @app.put("/api/settings/{key}")
    async def api_set_setting(request: Request, key: str, payload: dict[str, Any]) -> dict[str, str]:
        require_auth(request)
        if key in {"admin_password_hash", "admin_password_changed", "managers_config"}:
            raise HTTPException(status_code=403, detail="use dedicated endpoint")
        value = str(payload.get("value", "")).strip()
        if not value:
            raise HTTPException(status_code=400, detail="value required")
        if key == "timezone" and value not in TIMEZONE_OPTIONS:
            raise HTTPException(status_code=400, detail="unsupported timezone")
        repo.set_setting(key, value)
        return {"key": key, "value": value}

    @app.get("/api/managers")
    async def api_get_managers(request: Request) -> dict[str, Any]:
        require_auth(request)
        return repo.get_managers_config()

    @app.put("/api/managers")
    async def api_set_managers(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        require_auth(request)
        if not isinstance(payload.get("managers"), list) or not payload["managers"]:
            raise HTTPException(status_code=400, detail="managers required")
        return repo.set_managers_config(payload)

    @app.get("/api/escalation-cases")
    async def api_escalation_cases(
        request: Request,
        q: str = "",
        kind: str = "",
        has_order: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        require_auth(request)
        return repo.list_escalation_cases(query=q, kind=kind, has_order=has_order, limit=limit)

    @app.get("/api/escalation-cases/{case_id}")
    async def api_escalation_case(request: Request, case_id: int) -> dict[str, Any]:
        require_auth(request)
        item = repo.get_escalation_case(case_id)
        if not item:
            raise HTTPException(status_code=404, detail="not found")
        return item

    @app.post("/api/change-password")
    async def api_change_password(request: Request, payload: dict[str, Any]) -> dict[str, bool]:
        require_auth(request)
        current_password = str(payload.get("current_password", ""))
        new_password = str(payload.get("new_password", ""))
        confirm_password = str(payload.get("confirm_password", ""))
        if not current_password or not new_password:
            raise HTTPException(status_code=400, detail="fill all fields")
        if new_password != confirm_password:
            raise HTTPException(status_code=400, detail="passwords do not match")
        if len(new_password) < 4:
            raise HTTPException(status_code=400, detail="password too short")
        if not verify_password(current_password, current_password_hash()):
            raise HTTPException(status_code=400, detail="wrong current password")
        repo.set_admin_password_hash(ensure_password_hash(new_password))
        return {"ok": True}

    @app.get("/api/faq")
    async def api_faq(request: Request, q: str = "") -> list[dict[str, Any]]:
        require_auth(request)
        return repo.list_faq(q)

    @app.put("/api/faq/{key}")
    async def api_faq_upsert(request: Request, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        require_auth(request)
        answer = str(payload.get("answer", "")).strip()
        if not answer:
            raise HTTPException(status_code=400, detail="answer required")
        is_active = bool(payload.get("is_active", True))
        repo.upsert_faq(key, answer, is_active=is_active)
        return {"key": key.lower(), "answer": answer, "is_active": is_active}

    @app.get("/api/escalation")
    async def api_escalation(request: Request, q: str = "") -> list[dict[str, Any]]:
        require_auth(request)
        return repo.list_escalation(q)

    @app.put("/api/escalation/{keyword}")
    async def api_escalation_upsert(request: Request, keyword: str, payload: dict[str, Any]) -> dict[str, Any]:
        require_auth(request)
        is_active = bool(payload.get("is_active", True))
        repo.upsert_escalation(keyword, is_active)
        return {"keyword": keyword.lower(), "is_active": is_active}

    @app.get("/api/product-classes")
    async def api_product_classes(request: Request, q: str = "") -> list[dict[str, Any]]:
        require_auth(request)
        return repo.list_product_classes(q)

    @app.put("/api/product-classes/{code}")
    async def api_product_class_upsert(request: Request, code: str, payload: dict[str, Any]) -> dict[str, Any]:
        require_auth(request)
        price_from = float(payload.get("price_from", 0))
        is_active = bool(payload.get("is_active", True))
        repo.upsert_product_class(code, price_from, is_active=is_active)
        return {"code": code.lower(), "price_from": price_from, "is_active": is_active}

    @app.get("/api/countertops")
    async def api_countertops(request: Request, q: str = "") -> list[dict[str, Any]]:
        require_auth(request)
        return repo.list_countertops(q)

    @app.put("/api/countertops/{code}")
    async def api_countertop_upsert(request: Request, code: str, payload: dict[str, Any]) -> dict[str, Any]:
        require_auth(request)
        price_from = float(payload.get("price_from", 0))
        is_active = bool(payload.get("is_active", True))
        repo.upsert_countertop(code, price_from, is_active=is_active)
        return {"code": code.lower(), "price_from": price_from, "is_active": is_active}

    @app.get("/api/service-fees")
    async def api_service_fees(request: Request) -> list[dict[str, Any]]:
        require_auth(request)
        return repo.list_service_fees()

    @app.put("/api/service-fees/{code}")
    async def api_service_fee_upsert(request: Request, code: str, payload: dict[str, Any]) -> dict[str, Any]:
        require_auth(request)
        value = float(payload.get("value", 0))
        is_active = bool(payload.get("is_active", True))
        repo.upsert_service_fee(code, value, is_active=is_active)
        return {"code": code, "value": value, "is_active": is_active}

    @app.get("/api/catalog/{category}")
    async def api_catalog(request: Request, category: str, q: str = "", active_only: bool = False):
        require_auth(request)
        if category not in CATALOG_CATEGORIES:
            raise HTTPException(status_code=404, detail="unknown category")
        return repo.list_catalog(category, query=q, active_only=active_only)

    @app.post("/api/catalog/{category}")
    async def api_catalog_create(request: Request, category: str, payload: dict[str, Any]):
        require_auth(request)
        if category not in CATALOG_CATEGORIES:
            raise HTTPException(status_code=404, detail="unknown category")
        item_id = repo.upsert_catalog_item(
            item_id=None,
            category=category,
            code=str(payload.get("code", "")),
            title=str(payload.get("title", "")),
            description=str(payload.get("description", "")),
            price_from=_optional_float(payload.get("price_from")),
            is_active=bool(payload.get("is_active", True)),
            sort_order=int(payload.get("sort_order", 0)),
        )
        return {"id": item_id}

    @app.put("/api/catalog/item/{item_id}")
    async def api_catalog_update(request: Request, item_id: int, payload: dict[str, Any]):
        require_auth(request)
        category = str(payload.get("category", ""))
        if category not in CATALOG_CATEGORIES:
            raise HTTPException(status_code=400, detail="invalid category")
        updated_id = repo.upsert_catalog_item(
            item_id=item_id,
            category=category,
            code=str(payload.get("code", "")),
            title=str(payload.get("title", "")),
            description=str(payload.get("description", "")),
            price_from=_optional_float(payload.get("price_from")),
            is_active=bool(payload.get("is_active", True)),
            sort_order=int(payload.get("sort_order", 0)),
        )
        return {"id": updated_id}

    @app.get("/catalog/media/{item_id}/{size}.jpg")
    async def catalog_media_public(item_id: int, size: str) -> Response:
        if size not in {"thumb", "master"}:
            raise HTTPException(status_code=404, detail="not found")
        data = repo.get_catalog_image_bytes(item_id, size)
        if not data:
            raise HTTPException(status_code=404, detail="not found")
        return Response(
            content=data,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.post("/api/catalog/item/{item_id}/image")
    async def api_catalog_upload(
        request: Request,
        item_id: int,
        file: UploadFile = File(...),
    ):
        require_auth(request)
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="only jpeg/png/webp allowed")
        item = repo.get_catalog_item(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="catalog item not found")
        raw = await file.read()
        if cfg.uploads_dir.exists():
            remove_catalog_image_files(
                cfg.uploads_dir,
                item.get("image_path"),
                item.get("image_thumb_path"),
            )
        try:
            processed = process_catalog_image_bytes(raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid image file") from exc

        repo.set_catalog_image(
            item_id,
            image_master=processed.master,
            image_thumb=processed.thumb,
            image_width=processed.width,
            image_height=processed.height,
        )
        return {
            "image_path": catalog_media_path(item_id, "master"),
            "image_thumb_path": catalog_media_path(item_id, "thumb"),
            "image_width": processed.width,
            "image_height": processed.height,
        }

    @app.get("/api/audit")
    async def api_audit(request: Request, limit: int = 50) -> list[dict[str, Any]]:
        require_auth(request)
        return repo.list_audit(limit=limit)

    @app.get("/api/orders")
    async def api_orders(request: Request, q: str = "", limit: int = 50) -> list[dict[str, Any]]:
        require_auth(request)
        return repo.list_orders(query=q, limit=limit)

    @app.get("/api/orders/{order_id}")
    async def api_order_detail(request: Request, order_id: int) -> dict[str, Any]:
        require_auth(request)
        order = repo.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="order not found")
        dialogs = repo.list_order_dialogs(order_id)
        return {"order": order, "dialogs": dialogs}

    return app


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
