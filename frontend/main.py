from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Button, Input, Label, Markdown, Select, Static

URL = "http://localhost:8000"
SEARCH_URL = URL + "/search"
RESYNC_URL = URL + "/resync"
REPO_LIST_URL = URL + "/get_repo_list"


class ResultCard(Static):
    class Selected(Message):
        def __init__(self, source: str) -> None:
            self.source = source
            super().__init__()

    def __init__(self, source: str | None, text: str, score: float) -> None:
        super().__init__()
        self._source = source or ""
        self._text = text
        self._score = score

    def on_mount(self) -> None:
        from rich.text import Text

        t = Text()
        t.append(f"Score: {self._score:.4f}", style="bold #A7C7E7")
        t.append("\n")
        if self._source:
            t.append(f"{self._source}", style="italic #FFB5C2")
            t.append("\n")
        preview = self._text[:300].replace("\n", " ")
        t.append(f"{preview}...", style="#FFFFFF")
        self.update(t)

    def on_click(self) -> None:
        if self._source:
            self.post_message(self.Selected(self._source))


class DocSearchApp(App):
    CSS_PATH = "./src/style.css"
    ENABLE_TRANSPARENT_BACKGROUND = True
    BINDINGS = [("control+c", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        with Horizontal():
            with VerticalScroll(id="sidebar"):
                yield Label(" Docs", id="sidebar-title")
            with VerticalScroll(id="content-area"):
                yield Label("None", id="placeholder-label")
        with Horizontal(id="bottom-bar"):
            yield Input(placeholder="Search docs...", id="search-input")
            yield Button("Hybrid", id="hybrid-btn", classes="toggle-active")
            yield Select(
                [(str(n), n) for n in (3, 5, 10, 15, 20)],
                prompt="K value",
                value=5,
                id="k-select",
            )
            yield Button("Resync", id="resync-btn")
            yield Button("Search", id="search-btn")

    def on_mount(self) -> None:
        self.screen.styles.background = "transparent"
        self._load_repos()

    def _fetch_repos(self) -> list[dict]:
        req = urllib.request.Request(REPO_LIST_URL)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    @work(thread=True)
    def _load_repos(self) -> None:
        try:
            repos = self._fetch_repos()
            self.call_from_thread(self._show_repos, repos)
        except Exception:
            pass

    def _show_repos(self, repos: list[dict]) -> None:
        sidebar = self.query_one("#sidebar")
        for e in list(sidebar.query(".repo-label")):
            e.remove()
        for repo in repos:
            label = Static(repo["name"], classes="repo-label")
            label._repo_path = repo.get("path", "")
            sidebar.mount(label)

    def _show_error(self, msg: str) -> None:
        content = self.query_one("#content-area")
        content.remove_children()
        content.mount(Label(msg, classes="error-msg"))

    def _show_status(self, msg: str) -> None:
        content = self.query_one("#content-area")
        content.remove_children()
        content.mount(Label(msg, classes="status-msg"))

    def action_quit(self) -> None:
        self.exit()

    @on(Input.Submitted, "#search-input")
    def on_search_input_submitted(self) -> None:
        self.on_search_pressed()

    @on(Button.Pressed, "#hybrid-btn")
    def on_hybrid_toggle(self) -> None:
        btn = self.query_one("#hybrid-btn", Button)
        btn.classes = (
            "toggle-inactive" if btn.classes == "toggle-active" else "toggle-active"
        )

    @on(Button.Pressed, "#search-btn")
    def on_search_pressed(self) -> None:
        query = self.query_one("#search-input", Input).value
        if not query.strip():
            return
        hybrid = self.query_one("#hybrid-btn", Button).classes == "toggle-active"
        k = self.query_one("#k-select", Select).value
        self._show_status("Searching...")
        self._do_search(query, hybrid, k)

    @work(thread=True)
    def _do_search(self, query: str, hybrid: bool, k: int) -> None:
        try:
            data = urllib.parse.urlencode(
                {"query": query, "hybrid": hybrid, "k": k}
            ).encode()
            req = urllib.request.Request(SEARCH_URL, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                results = json.loads(resp.read())
            self.call_from_thread(self._show_results, results)
        except urllib.error.URLError as e:
            self.call_from_thread(self._show_error, f"Connection error: {e.reason}")
        except Exception as e:
            self.call_from_thread(self._show_error, f"Error: {e}")

    def _show_results(self, results: list[dict]) -> None:
        content = self.query_one("#content-area")
        content.remove_children()
        if not results:
            content.mount(Label("No results found", classes="status-msg"))
            return
        for r in results:
            card = ResultCard(
                source=r.get("source"),
                text=r.get("text", ""),
                score=r.get("score", 0.0),
            )
            card.classes = "result-card"
            content.mount(card)

    def on_result_card_selected(self, msg: ResultCard.Selected) -> None:
        self._show_source(msg.source)

    def _show_source(self, source_path: str) -> None:
        content = self.query_one("#content-area")
        content.remove_children()
        try:
            path = Path(source_path)
            file_text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            content.mount(Label(f"Cannot read file: {e}", classes="error-msg"))
            return

        back_btn = Button(" Back to results", id="back-btn")
        content.mount(back_btn)
        header = Label(f" {source_path}", id="source-header")
        content.mount(header)
        content.mount(Markdown(file_text))

    @on(Button.Pressed, "#back-btn")
    def on_back_pressed(self) -> None:
        content = self.query_one("#content-area")
        content.remove_children()
        content.mount(Label("None", id="placeholder-label"))

    @on(Button.Pressed, "#resync-btn")
    def on_resync_pressed(self) -> None:
        self._show_status("Resyncing...")
        self._do_resync()

    @work(thread=True)
    def _do_resync(self) -> None:
        try:
            req = urllib.request.Request(RESYNC_URL, data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                json.loads(resp.read())
            repos = self._fetch_repos()
            self.call_from_thread(self._show_repos, repos)
            self.call_from_thread(self._show_status, "Resync complete")
        except urllib.error.URLError as e:
            self.call_from_thread(self._show_error, f"Resync error: {e.reason}")
        except Exception as e:
            self.call_from_thread(self._show_error, f"Resync error: {e}")


if __name__ == "__main__":
    app = DocSearchApp()
    app.run()
