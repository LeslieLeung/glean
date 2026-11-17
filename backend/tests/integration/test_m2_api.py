"""
Integration tests for M2 API endpoints.

Tests for folders, tags, and bookmarks APIs.
"""

import pytest
from httpx import AsyncClient


class TestFolderAPI:
    """Test folder API endpoints."""

    @pytest.mark.asyncio
    async def test_create_folder(self, client: AsyncClient, auth_headers: dict):
        """Test creating a folder."""
        response = await client.post(
            "/api/folders",
            json={"name": "Test Folder", "type": "bookmark"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Folder"
        assert data["type"] == "bookmark"
        assert data["parent_id"] is None

    @pytest.mark.asyncio
    async def test_create_subfolder(self, client: AsyncClient, auth_headers: dict):
        """Test creating a subfolder."""
        # Create parent folder
        parent_response = await client.post(
            "/api/folders",
            json={"name": "Parent Folder", "type": "feed"},
            headers=auth_headers,
        )
        assert parent_response.status_code == 201
        parent_id = parent_response.json()["id"]

        # Create child folder
        response = await client.post(
            "/api/folders",
            json={"name": "Child Folder", "type": "feed", "parent_id": parent_id},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["parent_id"] == parent_id

    @pytest.mark.asyncio
    async def test_get_folders_tree(self, client: AsyncClient, auth_headers: dict):
        """Test getting folders as a tree."""
        # Create some folders
        await client.post(
            "/api/folders",
            json={"name": "Folder A", "type": "bookmark"},
            headers=auth_headers,
        )
        await client.post(
            "/api/folders",
            json={"name": "Folder B", "type": "bookmark"},
            headers=auth_headers,
        )

        # Get tree
        response = await client.get("/api/folders?type=bookmark", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "folders" in data
        assert len(data["folders"]) >= 2

    @pytest.mark.asyncio
    async def test_update_folder(self, client: AsyncClient, auth_headers: dict):
        """Test updating a folder."""
        # Create folder
        create_response = await client.post(
            "/api/folders",
            json={"name": "Original Name", "type": "bookmark"},
            headers=auth_headers,
        )
        folder_id = create_response.json()["id"]

        # Update folder
        response = await client.patch(
            f"/api/folders/{folder_id}",
            json={"name": "Updated Name"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_delete_folder(self, client: AsyncClient, auth_headers: dict):
        """Test deleting a folder."""
        # Create folder
        create_response = await client.post(
            "/api/folders",
            json={"name": "To Delete", "type": "bookmark"},
            headers=auth_headers,
        )
        folder_id = create_response.json()["id"]

        # Delete folder
        response = await client.delete(f"/api/folders/{folder_id}", headers=auth_headers)
        assert response.status_code == 204

        # Verify deleted
        get_response = await client.get(f"/api/folders/{folder_id}", headers=auth_headers)
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_folder_type_mismatch(self, client: AsyncClient, auth_headers: dict):
        """Test that parent and child folders must have the same type."""
        # Create parent folder with type "feed"
        parent_response = await client.post(
            "/api/folders",
            json={"name": "Feed Folder", "type": "feed"},
            headers=auth_headers,
        )
        parent_id = parent_response.json()["id"]

        # Try to create child folder with type "bookmark"
        response = await client.post(
            "/api/folders",
            json={"name": "Bookmark Child", "type": "bookmark", "parent_id": parent_id},
            headers=auth_headers,
        )
        assert response.status_code == 400


class TestTagAPI:
    """Test tag API endpoints."""

    @pytest.mark.asyncio
    async def test_create_tag(self, client: AsyncClient, auth_headers: dict):
        """Test creating a tag."""
        response = await client.post(
            "/api/tags",
            json={"name": "Python", "color": "#3B82F6"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Python"
        assert data["color"] == "#3B82F6"

    @pytest.mark.asyncio
    async def test_create_duplicate_tag(self, client: AsyncClient, auth_headers: dict):
        """Test that duplicate tag names are rejected."""
        # Create first tag
        await client.post(
            "/api/tags",
            json={"name": "UniqueTag"},
            headers=auth_headers,
        )

        # Try to create duplicate
        response = await client.post(
            "/api/tags",
            json={"name": "UniqueTag"},
            headers=auth_headers,
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_get_tags_with_counts(self, client: AsyncClient, auth_headers: dict):
        """Test getting tags with usage counts."""
        # Create tag
        await client.post(
            "/api/tags",
            json={"name": "TestTag"},
            headers=auth_headers,
        )

        # Get tags
        response = await client.get("/api/tags", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "tags" in data
        for tag in data["tags"]:
            assert "bookmark_count" in tag
            assert "entry_count" in tag

    @pytest.mark.asyncio
    async def test_update_tag(self, client: AsyncClient, auth_headers: dict):
        """Test updating a tag."""
        # Create tag
        create_response = await client.post(
            "/api/tags",
            json={"name": "OldName", "color": "#000000"},
            headers=auth_headers,
        )
        tag_id = create_response.json()["id"]

        # Update tag
        response = await client.patch(
            f"/api/tags/{tag_id}",
            json={"name": "NewName", "color": "#FFFFFF"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "NewName"
        assert data["color"] == "#FFFFFF"

    @pytest.mark.asyncio
    async def test_delete_tag(self, client: AsyncClient, auth_headers: dict):
        """Test deleting a tag."""
        # Create tag
        create_response = await client.post(
            "/api/tags",
            json={"name": "ToDelete"},
            headers=auth_headers,
        )
        tag_id = create_response.json()["id"]

        # Delete tag
        response = await client.delete(f"/api/tags/{tag_id}", headers=auth_headers)
        assert response.status_code == 204


class TestBookmarkAPI:
    """Test bookmark API endpoints."""

    @pytest.mark.asyncio
    async def test_create_bookmark_external_url(self, client: AsyncClient, auth_headers: dict):
        """Test creating a bookmark for an external URL."""
        response = await client.post(
            "/api/bookmarks",
            json={
                "url": "https://example.com/article",
                "title": "Test Article",
                "excerpt": "Test excerpt",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["url"] == "https://example.com/article"
        assert data["title"] == "Test Article"
        assert data["entry_id"] is None

    @pytest.mark.asyncio
    async def test_create_bookmark_with_folder_and_tag(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test creating a bookmark with folder and tag associations."""
        # Create folder
        folder_response = await client.post(
            "/api/folders",
            json={"name": "Bookmarks Folder", "type": "bookmark"},
            headers=auth_headers,
        )
        folder_id = folder_response.json()["id"]

        # Create tag
        tag_response = await client.post(
            "/api/tags",
            json={"name": "Important"},
            headers=auth_headers,
        )
        tag_id = tag_response.json()["id"]

        # Create bookmark with folder and tag
        response = await client.post(
            "/api/bookmarks",
            json={
                "url": "https://example.com/important",
                "title": "Important Article",
                "folder_ids": [folder_id],
                "tag_ids": [tag_id],
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert len(data["folders"]) == 1
        assert data["folders"][0]["id"] == folder_id
        assert len(data["tags"]) == 1
        assert data["tags"][0]["id"] == tag_id

    @pytest.mark.asyncio
    async def test_get_bookmarks_with_filters(self, client: AsyncClient, auth_headers: dict):
        """Test getting bookmarks with filtering."""
        # Create folder
        folder_response = await client.post(
            "/api/folders",
            json={"name": "Filter Test Folder", "type": "bookmark"},
            headers=auth_headers,
        )
        folder_id = folder_response.json()["id"]

        # Create bookmark in folder
        await client.post(
            "/api/bookmarks",
            json={
                "url": "https://example.com/filtered",
                "title": "Filtered Article",
                "folder_ids": [folder_id],
            },
            headers=auth_headers,
        )

        # Get bookmarks filtered by folder
        response = await client.get(f"/api/bookmarks?folder_id={folder_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_update_bookmark(self, client: AsyncClient, auth_headers: dict):
        """Test updating a bookmark."""
        # Create bookmark
        create_response = await client.post(
            "/api/bookmarks",
            json={"url": "https://example.com/update", "title": "Original Title"},
            headers=auth_headers,
        )
        bookmark_id = create_response.json()["id"]

        # Update bookmark
        response = await client.patch(
            f"/api/bookmarks/{bookmark_id}",
            json={"title": "Updated Title", "excerpt": "New excerpt"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["excerpt"] == "New excerpt"

    @pytest.mark.asyncio
    async def test_delete_bookmark(self, client: AsyncClient, auth_headers: dict):
        """Test deleting a bookmark."""
        # Create bookmark
        create_response = await client.post(
            "/api/bookmarks",
            json={"url": "https://example.com/delete", "title": "To Delete"},
            headers=auth_headers,
        )
        bookmark_id = create_response.json()["id"]

        # Delete bookmark
        response = await client.delete(f"/api/bookmarks/{bookmark_id}", headers=auth_headers)
        assert response.status_code == 204

        # Verify deleted
        get_response = await client.get(f"/api/bookmarks/{bookmark_id}", headers=auth_headers)
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_remove_bookmark_folder(self, client: AsyncClient, auth_headers: dict):
        """Test adding and removing folder from bookmark."""
        # Create folder
        folder_response = await client.post(
            "/api/folders",
            json={"name": "Add/Remove Folder", "type": "bookmark"},
            headers=auth_headers,
        )
        folder_id = folder_response.json()["id"]

        # Create bookmark
        create_response = await client.post(
            "/api/bookmarks",
            json={"url": "https://example.com/addremove", "title": "Test"},
            headers=auth_headers,
        )
        bookmark_id = create_response.json()["id"]

        # Add folder
        add_response = await client.post(
            f"/api/bookmarks/{bookmark_id}/folders",
            json={"folder_id": folder_id},
            headers=auth_headers,
        )
        assert add_response.status_code == 200
        assert len(add_response.json()["folders"]) == 1

        # Remove folder
        remove_response = await client.delete(
            f"/api/bookmarks/{bookmark_id}/folders/{folder_id}", headers=auth_headers
        )
        assert remove_response.status_code == 200
        assert len(remove_response.json()["folders"]) == 0

    @pytest.mark.asyncio
    async def test_add_remove_bookmark_tag(self, client: AsyncClient, auth_headers: dict):
        """Test adding and removing tag from bookmark."""
        # Create tag
        tag_response = await client.post(
            "/api/tags",
            json={"name": "Add/Remove Tag"},
            headers=auth_headers,
        )
        tag_id = tag_response.json()["id"]

        # Create bookmark
        create_response = await client.post(
            "/api/bookmarks",
            json={"url": "https://example.com/tagtest", "title": "Test"},
            headers=auth_headers,
        )
        bookmark_id = create_response.json()["id"]

        # Add tag
        add_response = await client.post(
            f"/api/bookmarks/{bookmark_id}/tags",
            json={"tag_id": tag_id},
            headers=auth_headers,
        )
        assert add_response.status_code == 200
        assert len(add_response.json()["tags"]) == 1

        # Remove tag
        remove_response = await client.delete(
            f"/api/bookmarks/{bookmark_id}/tags/{tag_id}", headers=auth_headers
        )
        assert remove_response.status_code == 200
        assert len(remove_response.json()["tags"]) == 0

    @pytest.mark.asyncio
    async def test_bookmark_validation(self, client: AsyncClient, auth_headers: dict):
        """Test bookmark validation - either entry_id or url required."""
        # Try to create bookmark without url or entry_id
        response = await client.post(
            "/api/bookmarks",
            json={"title": "No Source"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_bookmark_url_only_triggers_metadata_fetch(
        self, client: AsyncClient, auth_headers: dict, test_mock_redis
    ):
        """Test creating a bookmark with only URL triggers async metadata fetch."""
        # Clear any previous jobs
        test_mock_redis.enqueued_jobs.clear()

        # Create bookmark with only URL (no title)
        response = await client.post(
            "/api/bookmarks",
            json={"url": "https://example.com/article-without-title"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()

        # URL should be used as temporary title
        assert data["url"] == "https://example.com/article-without-title"
        assert data["title"] == "https://example.com/article-without-title"

        # Check that metadata fetch task was queued
        assert len(test_mock_redis.enqueued_jobs) == 1
        job_name, job_args = test_mock_redis.enqueued_jobs[0]
        assert job_name == "fetch_bookmark_metadata_task"
        assert job_args[0] == data["id"]

    @pytest.mark.asyncio
    async def test_create_bookmark_with_title_still_fetches_content(
        self, client: AsyncClient, auth_headers: dict, test_mock_redis
    ):
        """Custom metadata still permits fetching the full article body."""
        # Clear any previous jobs
        test_mock_redis.enqueued_jobs.clear()

        # Create bookmark with title and excerpt
        response = await client.post(
            "/api/bookmarks",
            json={
                "url": "https://example.com/complete-bookmark",
                "title": "Complete Bookmark",
                "excerpt": "This is a complete bookmark with all info",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()

        assert data["title"] == "Complete Bookmark"
        assert data["excerpt"] == "This is a complete bookmark with all info"

        # Custom metadata is preserved, but body extraction still runs.
        assert test_mock_redis.enqueued_jobs == [("fetch_bookmark_metadata_task", (data["id"],))]


class TestTagBatchOperations:
    """Test tag batch operations."""

    @pytest.mark.asyncio
    async def test_batch_add_tag(self, client: AsyncClient, auth_headers: dict):
        """Test batch adding tags to bookmarks."""
        # Create tag
        tag_response = await client.post(
            "/api/tags",
            json={"name": "BatchTag"},
            headers=auth_headers,
        )
        tag_id = tag_response.json()["id"]

        # Create bookmarks
        bookmark_ids = []
        for i in range(3):
            response = await client.post(
                "/api/bookmarks",
                json={"url": f"https://example.com/batch{i}", "title": f"Batch {i}"},
                headers=auth_headers,
            )
            bookmark_ids.append(response.json()["id"])

        # Batch add tag
        response = await client.post(
            "/api/tags/batch",
            json={
                "action": "add",
                "tag_id": tag_id,
                "target_type": "bookmark",
                "target_ids": bookmark_ids,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["affected"] == 3

    @pytest.mark.asyncio
    async def test_batch_remove_tag(self, client: AsyncClient, auth_headers: dict):
        """Test batch removing tags from bookmarks."""
        # Create tag
        tag_response = await client.post(
            "/api/tags",
            json={"name": "BatchRemoveTag"},
            headers=auth_headers,
        )
        tag_id = tag_response.json()["id"]

        # Create bookmarks with tag
        bookmark_ids = []
        for i in range(2):
            response = await client.post(
                "/api/bookmarks",
                json={
                    "url": f"https://example.com/batchremove{i}",
                    "title": f"Remove {i}",
                    "tag_ids": [tag_id],
                },
                headers=auth_headers,
            )
            bookmark_ids.append(response.json()["id"])

        # Batch remove tag
        response = await client.post(
            "/api/tags/batch",
            json={
                "action": "remove",
                "tag_id": tag_id,
                "target_type": "bookmark",
                "target_ids": bookmark_ids,
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["affected"] == 2
