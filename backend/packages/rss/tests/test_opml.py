"""Tests for OPML parser and generator."""

from glean_rss.opml import generate_opml, parse_opml, parse_opml_with_folders


class TestParseOPML:
    """Test OPML parsing."""

    def test_parse_opml_simple(self) -> None:
        """Test parsing simple OPML without folders."""
        opml = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
            <head><title>Test</title></head>
            <body>
                <outline text="Feed 1" title="Feed 1" xmlUrl="https://example.com/feed1.xml" type="rss"/>
                <outline text="Feed 2" title="Feed 2" xmlUrl="https://example.com/feed2.xml" type="rss"/>
            </body>
        </opml>
        """
        feeds = parse_opml(opml)
        assert len(feeds) == 2
        assert feeds[0].title == "Feed 1"
        assert feeds[0].xml_url == "https://example.com/feed1.xml"
        assert feeds[0].folder is None
        assert feeds[1].title == "Feed 2"
        assert feeds[1].xml_url == "https://example.com/feed2.xml"
        assert feeds[1].folder is None

    def test_parse_opml_with_folders(self) -> None:
        """Test parsing OPML with folder structure."""
        opml = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
            <head><title>Test</title></head>
            <body>
                <outline text="Blog">
                    <outline text="Feed 1" title="Feed 1" xmlUrl="https://example.com/feed1.xml" type="rss"/>
                    <outline text="Feed 2" title="Feed 2" xmlUrl="https://example.com/feed2.xml" type="rss"/>
                </outline>
                <outline text="News">
                    <outline text="Feed 3" title="Feed 3" xmlUrl="https://example.com/feed3.xml" type="rss"/>
                </outline>
                <outline text="Root Feed" title="Root Feed" xmlUrl="https://example.com/root.xml" type="rss"/>
            </body>
        </opml>
        """
        result = parse_opml_with_folders(opml)

        # Check folders
        assert len(result.folders) == 2
        assert "Blog" in result.folders
        assert "News" in result.folders

        # Check feeds
        assert len(result.feeds) == 4

        # Blog feeds
        blog_feeds = [f for f in result.feeds if f.folder == "Blog"]
        assert len(blog_feeds) == 2
        assert blog_feeds[0].title == "Feed 1"
        assert blog_feeds[1].title == "Feed 2"

        # News feeds
        news_feeds = [f for f in result.feeds if f.folder == "News"]
        assert len(news_feeds) == 1
        assert news_feeds[0].title == "Feed 3"

        # Root feed (no folder)
        root_feeds = [f for f in result.feeds if f.folder is None]
        assert len(root_feeds) == 1
        assert root_feeds[0].title == "Root Feed"

    def test_parse_opml_empty_body(self) -> None:
        """Test parsing OPML with empty body."""
        opml = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
            <head><title>Test</title></head>
            <body></body>
        </opml>
        """
        result = parse_opml_with_folders(opml)
        assert len(result.feeds) == 0
        assert len(result.folders) == 0

    def test_parse_opml_invalid_xml(self) -> None:
        """Test parsing invalid XML raises ValueError."""
        import pytest

        with pytest.raises(ValueError, match="Invalid OPML format"):
            parse_opml("not xml at all")

    def test_parse_follow_opml_structure(self) -> None:
        """Test parsing Follow-style OPML with nested structure."""
        opml = """<?xml version="1.0" encoding="UTF-8"?>
        <opml version="2.0">
            <head><dateCreated>2025-12-01T08:46:59.809Z</dateCreated><title>Follow</title></head>
            <body>
                <outline text="Blog">
                    <outline text="美团技术团队" title="美团技术团队" xmlUrl="https://tech.meituan.com/feed/" htmlUrl="https://tech.meituan.com/feed/" type="rss"/>
                    <outline text="二丫讲梵" title="二丫讲梵" xmlUrl="https://wiki.eryajf.net/rss.xml" htmlUrl="https://wiki.eryajf.net/" type="rss"/>
                </outline>
                <outline text="Weekly">
                    <outline text="Golang Weekly" title="Golang Weekly" xmlUrl="https://cprss.s3.amazonaws.com/golangweekly.com.xml" htmlUrl="https://golangweekly.com/" type="rss"/>
                </outline>
                <outline text="影视飓风" title="影视飓风" xmlUrl="https://rsshub.app/bilibili/user/dynamic/946974" htmlUrl="https://space.bilibili.com/946974/dynamic" type="rss"/>
            </body>
        </opml>
        """
        result = parse_opml_with_folders(opml)

        # Check folders
        assert len(result.folders) == 2
        assert "Blog" in result.folders
        assert "Weekly" in result.folders

        # Check feeds
        assert len(result.feeds) == 4

        # Blog feeds
        blog_feeds = [f for f in result.feeds if f.folder == "Blog"]
        assert len(blog_feeds) == 2

        # Weekly feeds
        weekly_feeds = [f for f in result.feeds if f.folder == "Weekly"]
        assert len(weekly_feeds) == 1

        # Root feed (影视飓风)
        root_feeds = [f for f in result.feeds if f.folder is None]
        assert len(root_feeds) == 1
        assert root_feeds[0].title == "影视飓风"


class TestGenerateOPML:
    """Test OPML generation."""

    def test_generate_opml_simple(self) -> None:
        """Test generating simple OPML without folders."""
        feeds = [
            {
                "title": "Feed 1",
                "url": "https://example.com/feed1.xml",
                "site_url": "https://example.com",
            },
            {"title": "Feed 2", "url": "https://example.com/feed2.xml"},
        ]
        opml = generate_opml(feeds)

        assert "<?xml version=" in opml
        assert "encoding=" in opml
        assert "<opml" in opml
        assert 'xmlUrl="https://example.com/feed1.xml"' in opml
        assert 'xmlUrl="https://example.com/feed2.xml"' in opml
        assert 'htmlUrl="https://example.com"' in opml

    def test_generate_opml_with_folders(self) -> None:
        """Test generating OPML with folder structure."""
        feeds = [
            {"title": "Root Feed", "url": "https://example.com/root.xml"},
            {"title": "Feed 1", "url": "https://example.com/feed1.xml", "folder": "Blog"},
            {"title": "Feed 2", "url": "https://example.com/feed2.xml", "folder": "Blog"},
            {"title": "Feed 3", "url": "https://example.com/feed3.xml", "folder": "News"},
        ]
        opml = generate_opml(feeds)

        # Verify structure
        assert "<?xml version=" in opml
        assert "<opml" in opml

        # Root feed should be at top level
        assert 'title="Root Feed"' in opml

        # Folder outlines should exist
        assert 'text="Blog"' in opml
        assert 'text="News"' in opml

        # Feeds should be inside folders
        assert 'xmlUrl="https://example.com/feed1.xml"' in opml
        assert 'xmlUrl="https://example.com/feed3.xml"' in opml

    def test_generate_opml_roundtrip(self) -> None:
        """Test generating and parsing OPML preserves data."""
        original_feeds = [
            {"title": "Root Feed", "url": "https://example.com/root.xml"},
            {"title": "Feed 1", "url": "https://example.com/feed1.xml", "folder": "Blog"},
            {"title": "Feed 2", "url": "https://example.com/feed2.xml", "folder": "Blog"},
        ]

        # Generate and parse back
        opml = generate_opml(original_feeds)
        result = parse_opml_with_folders(opml)

        # Verify feeds count
        assert len(result.feeds) == 3

        # Verify folder
        assert "Blog" in result.folders

        # Verify folder assignment
        blog_feeds = [f for f in result.feeds if f.folder == "Blog"]
        assert len(blog_feeds) == 2

        root_feeds = [f for f in result.feeds if f.folder is None]
        assert len(root_feeds) == 1


class TestNestedOPML:
    def test_roundtrip_preserves_paths_same_leaf_names_and_empty_folders(self):
        paths = [("Tech",), ("Tech", "News"), ("Life",), ("Life", "News"), ("Empty / Folder",)]
        feeds = [
            {"title": "Tech", "url": "https://example.com/tech", "folder_path": ("Tech", "News")},
            {"title": "Life", "url": "https://example.com/life", "folder_path": ("Life", "News")},
        ]
        parsed = parse_opml_with_folders(generate_opml(feeds, folder_paths=paths))
        assert parsed.folder_paths == paths
        assert [(feed.xml_url, feed.folder_path) for feed in parsed.feeds] == [
            ("https://example.com/tech", ("Tech", "News")),
            ("https://example.com/life", ("Life", "News")),
        ]

    def test_rejects_non_opml_and_excessive_depth(self):
        import pytest

        with pytest.raises(ValueError, match="Invalid OPML"):
            parse_opml_with_folders("<rss><channel/></rss>")
        deep = '<outline text="Nested">' * 6 + "</outline>" * 6
        with pytest.raises(ValueError, match="depth"):
            parse_opml_with_folders(f"<opml><body>{deep}</body></opml>")
