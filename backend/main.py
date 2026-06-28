from fastapi import FastAPI, Request, Depends, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from models import Doc, Repo
from jinja import Jinja2Templates
from typing import Any
import vecdb
import os

app = FastAPI()

app.mount("/static", StaticFiles(directory="../frontend/public/"), name="static")
templates = Jinja2Templates(directory="../frontend/templates")

LOCAL_DOCS_FOLDER = "./docs_local/"
LOCAL_DB = "./database/"
QDRANT_URL = ""
QDRANT_API = ""


@app.on_event("startup")
async def create_collection():
    app.state.db = vecdb.VectorDB(LOCAL_DB, url=QDRANT_URL, api=QDRANT_API)
    app.state.db.sync_from_roots(LOCAL_DOCS_FOLDER)


@app.get("/get_repo_list", name="get_repo_list")
async def get_repo_list(request: Request):
    existing_repos: list[Repo] | None = os.scandir(LOCAL_DOCS_FOLDER)
    return existing_repos


@app.get("/", name="index", response_class=HTMLResponse)
async def index_page(request: Request):
    return templates.TemplateResponse(
        "index.html", {"request": request, "repos": get_repo_list}
    )


@app.post("/search")
async def search(query: str, k: int = 3, hybrid: bool = True) -> list[dict[str, Any]]:
    return app.state.db.search(query=query, k=k, hybrid=hybrid)


@app.post("/re_sync")
async def re_sync():
    app.state.db.sync_from_roots(LOCAL_DOCS_FOLDER)


@app.post("/ingest_docs", name="ingest")
async def ingest_docs(request: Request, doc_url: str = Form(...)):
    pass
