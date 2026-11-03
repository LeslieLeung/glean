"""OPML import/export preserving complete folder paths, including empty folders."""

from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree as ET

FolderPath = tuple[str, ...]


class OPMLFeed:
    def __init__(
        self,
        title: str,
        xml_url: str,
        html_url: str | None = None,
        folder: str | None = None,
        folder_path: FolderPath = (),
    ):
        self.title = title
        self.xml_url = xml_url
        self.html_url = html_url
        self.folder_path = folder_path or ((folder,) if folder else ())
        # Keep the original leaf-name API for existing consumers.
        self.folder = self.folder_path[-1] if self.folder_path else None


class OPMLParseResult:
    def __init__(self, feeds: list[OPMLFeed], folder_paths: list[FolderPath]):
        self.feeds = feeds
        self.folder_paths = folder_paths
        self.folders = list(dict.fromkeys(path[-1] for path in folder_paths))


def parse_opml(content: str) -> list[OPMLFeed]:
    return parse_opml_with_folders(content).feeds


def parse_opml_with_folders(content: str) -> OPMLParseResult:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise ValueError(f"Invalid OPML format: {error}") from error
    body = root.find("body")
    if root.tag != "opml" or body is None:
        raise ValueError("Invalid OPML format: expected an opml document with a body")

    feeds: list[OPMLFeed] = []
    folder_paths: list[FolderPath] = []

    def process_outline(outline: ET.Element, parent: FolderPath = ()) -> None:
        xml_url = outline.get("xmlUrl")
        title = outline.get("title") or outline.get("text", "")
        if xml_url:
            feeds.append(OPMLFeed(title, xml_url, outline.get("htmlUrl"), folder_path=parent))
            return
        if len(title) > 100:
            raise ValueError("Folder names must contain at most 100 characters")
        path = (*parent, title) if title else parent
        if len(path) > 5:
            raise ValueError("Maximum folder depth (5) exceeded")
        if path and path not in folder_paths:
            folder_paths.append(path)
        for child in outline.findall("outline"):
            process_outline(child, path)

    for outline in body.findall("outline"):
        process_outline(outline)
    return OPMLParseResult(feeds, folder_paths)


def generate_opml(
    feeds: list[dict[str, Any]],
    title: str = "Glean Subscriptions",
    folder_paths: list[FolderPath] | None = None,
) -> str:
    opml = ET.Element("opml", version="2.0")
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = title
    ET.SubElement(head, "dateCreated").text = datetime.now(UTC).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )
    body = ET.SubElement(opml, "body")
    folders: dict[FolderPath, ET.Element] = {(): body}

    def ensure_folder(path: FolderPath) -> ET.Element:
        if path not in folders:
            parent = ensure_folder(path[:-1])
            folders[path] = ET.SubElement(parent, "outline", text=path[-1], title=path[-1])
        return folders[path]

    for path in folder_paths or []:
        ensure_folder(path)
    for feed in feeds:
        path = tuple(feed.get("folder_path") or ())
        if not path and feed.get("folder"):
            path = (feed["folder"],)
        outline = ET.SubElement(
            ensure_folder(path),
            "outline",
            type="rss",
            text=feed.get("title") or "",
            title=feed.get("title") or "",
            xmlUrl=feed["url"],
        )
        if feed.get("site_url"):
            outline.set("htmlUrl", feed["site_url"])

    ET.indent(opml, space="  ")
    return ET.tostring(opml, encoding="utf-8", xml_declaration=True).decode("utf-8")
