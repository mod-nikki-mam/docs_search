from fastapi import FastAPI, Request, Depends, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.exceptions import HTTPException
from database_handling import engine, get_db, Base
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from models import Doc, Repo
from chunk import chunk_general
import tempfile

app = FastAPI()


@app.on_event("startup")
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/ping_db")
async def ping_db(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    return {"ok": result.scalar() == 1}


@app.get("/", name="index", response_class=HTMLResponse)
async def index_page(request: Request, db: AsyncSession = Depends(get_db)):
    existing_repos: list[Repo] | None = (await db.execute(select(Repo))).scalars().all()
    return {"request": request, "repos": existing_repos}


@app.post("/ingest", name="ingest", response_class=HTMLResponse)
async def ingest_docs(
    request: Request, doc_url: str = Form(...), db: AsyncSession = Depends(get_db)
):
    pass
