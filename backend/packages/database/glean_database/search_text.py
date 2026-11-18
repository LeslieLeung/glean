"""Search projections shared by models and migration backfills."""

from html.parser import HTMLParser


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "template"):
            self.hidden += 1
        if tag in ("p", "div", "br", "li", "h1", "h2", "h3", "tr"):
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "template"):
            self.hidden = max(0, self.hidden - 1)
        if tag in ("p", "div", "li", "h1", "h2", "h3", "tr"):
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def html_text(value: str | None) -> str:
    parser = _TextParser()
    parser.feed(value or "")
    return " ".join("".join(parser.parts).split())


def bookmark_search_text(
    title: str, excerpt: str | None, url: str | None, source: str | None, content: str | None
) -> str:
    return "\n".join((title, html_text(excerpt), url or "", source or "", html_text(content)))
