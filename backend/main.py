import os
import docker
from qdrant_client import QdrantClient
from typing import Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import HTTPException

import vecdb

LOCAL_DOCS_FOLDER = "./docs_local/"
LOCAL_DB = "./database/"
QDRANT_URL = "http://localhost:6333/"
QDRANT_API = "wGjDSdoW8@2t@A"


@asynccontextmanager
async def lifespan(app):
    docker_client = docker.from_env()
    try:
        container = docker_client.containers.get(
            "qdrant_docs_search"
        )  # check if previos container exists and use that instead of deleting data
        if container.status != "running":
            container.start()
    except docker.errors.NotFound:
        container = docker_client.containers.run(
            "qdrant/qdrant",
            name="qdrant_docs_search",
            ports={"6333/tcp": 6333, "6334/tcp": 6334},
            volumes={
                "/home/claude/docs_search/qdrant_storage": {
                    "bind": "/qdrant/storage",
                    "mode": "rw",
                }
            },
            detach=True,
        )
    # wait for Qdrant to accept connections
    import time

    for _ in range(10):
        try:
            QdrantClient(url="http://localhost:6333").get_collections()
            break
        except Exception as e:
            print(e)
            time.sleep(1)
    app.state.db = vecdb.VectorDB(LOCAL_DB, url=QDRANT_URL, api_key=QDRANT_API)
    app.state.db.sync_from_roots(LOCAL_DOCS_FOLDER)
    yield
    app.state.db.close()
    container.stop()


app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/get_repo_list", name="get_repo_list")
async def get_repo_list():
    repos = []
    if os.path.isdir(LOCAL_DOCS_FOLDER):
        for entry in os.scandir(LOCAL_DOCS_FOLDER):
            if entry.is_dir():
                repos.append({"name": entry.name, "path": entry.path})
    return repos


@app.post("/search")
async def search(
    query: str = Form(...), k: int = Form(3), hybrid: bool = Form(True)
) -> list[dict[str, Any]]:
    return app.state.db.search(query=query, k=k, hybrid=hybrid)


@app.post("/re_sync")
@app.post("/resync")
async def re_sync():
    app.state.db.sync_from_roots(LOCAL_DOCS_FOLDER)
    return {"status": "ok"}
