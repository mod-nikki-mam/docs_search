# docs-search

A personal TUI frontend for searching local documentation repositories via a FastAPI + Qdrant backend

## Dependencies

- [textual](https://github.com/Textualize/textual) — terminal UI framework
- [FastAPI](fastapi.tiangolo.com)
- qdrant running as docker
- gitpython for (upcoming) ingestion

No external HTTP clients — uses only `urllib` from stdlib.

## Backend

a FastAPI server running on `localhost:8000` with these endpoints:

| Endpoint | Method | Description |
|---|---|---|
| `/search` | POST | Hybrid/semantic search (`query`, `hybrid`, `k`) |
| `/resync` | POST | Rescan docs directories |
| `/get_repo_list` | GET | List available doc repos |
| /ingest | POST | (upcoming) handle ingestion of documentation from git repos |


## Features

- sidebar with available doc repositories
- hybrid search toggle (neon pink when active, dim when off)(doesnt work properly yet)
- k-value selector (3 / 5 / 10 / 15 / 20)
- enter to search, Ctrl+C to quit (no confirmation prompt)
- click a result to view the source file rendered as markdown
- transparent terminal background with neon pink / blue theme

## Usage
its not a complete app yet,to test you'll have to run the backend/main.py server and frontend/main.py textual app

## status

this is a personal project and still in its infancy,im making it cause TUI docs searchers are pretty looking and suck are reading docs

## upcoming:
  - better markdown rendering(textual's seems slower than python's markdown?)
  - jump to chunk in document(currently just opens the source document)
  - naive status bar when resyncing
  - git ingestion: the main reason i started this project was to easily view docs by just pasting a link in
 - webui with jinja

## long term(currently out of scope):
 - smarter ingestion,the ability to paste in any doc site URL and have a crawler get most relevant docs
