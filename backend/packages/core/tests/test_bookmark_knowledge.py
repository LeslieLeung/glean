"""Personal knowledge persists independently of source content and owner boundaries."""

from typing import Any, cast

import pytest
from sqlalchemy import select

from glean_core.schemas.bookmark import (
    AnnotationCreate,
    AnnotationUpdate,
    BookmarkCreate,
    BookmarkNoteUpdate,
    BookmarkUpdate,
)
from glean_core.services.bookmark_knowledge_service import (
    BookmarkKnowledgeService,
    RevisionConflictError,
)
from glean_core.services.bookmark_service import BookmarkService
from glean_database.models import Bookmark, BookmarkAnnotation, BookmarkNote
from glean_database.search_text import html_text

from .test_bookmark_library import UndoCache, setup_library


def anchor(**changes):
    values = {
        "exact": "Preserved body",
        "prefix": "",
        "suffix": "",
        "start": 0,
        "end": 14,
        "content_hash": "a" * 64,
    }
    values.update(changes)
    return AnnotationCreate(**values)


async def test_notes_revision_empty_and_ownership(db_session):
    user, other, _, entry = await setup_library(db_session)
    saved, _ = await BookmarkService(db_session).create_bookmark(
        user.id, BookmarkCreate(entry_id=entry.id)
    )
    knowledge = BookmarkKnowledgeService(db_session)
    assert (await knowledge.get_note(saved.id, user.id)).revision == 0
    first = await knowledge.save_note(
        saved.id, user.id, BookmarkNoteUpdate(body="**我的备注**", revision=0)
    )
    assert first.revision == 1
    with pytest.raises(RevisionConflictError):
        await knowledge.save_note(
            saved.id, user.id, BookmarkNoteUpdate(body="Lost edit", revision=0)
        )
    assert (await knowledge.get_note(saved.id, user.id)).body == "**我的备注**"
    for operation in [
        knowledge.get_note(saved.id, other.id),
        knowledge.save_note(saved.id, other.id, BookmarkNoteUpdate(body="Attack", revision=1)),
        knowledge.list_annotations(saved.id, other.id),
        knowledge.create_annotation(saved.id, other.id, anchor()),
    ]:
        with pytest.raises(ValueError, match="not found"):
            await operation
    cleared = await knowledge.save_note(saved.id, user.id, BookmarkNoteUpdate(body="", revision=1))
    assert cleared.revision == 2 and cleared.body == ""


async def test_annotations_revision_scope_and_deletion(db_session):
    user, other, _, entry = await setup_library(db_session)
    service = BookmarkService(db_session)
    saved, _ = await service.create_bookmark(user.id, BookmarkCreate(entry_id=entry.id))
    second, _ = await service.create_bookmark(
        user.id, BookmarkCreate(url="https://example.org/another")
    )
    knowledge = BookmarkKnowledgeService(db_session)
    first = await knowledge.create_annotation(saved.id, user.id, anchor(body="想法"))
    assert first.revision == 1
    assert (await knowledge.list_annotations(saved.id, user.id))[0].body == "想法"
    for bookmark_id, owner in [(second.id, user.id), (saved.id, other.id)]:
        with pytest.raises(ValueError, match="not found"):
            await knowledge.update_annotation(
                bookmark_id, owner, first.id, AnnotationUpdate(body="Attack", revision=1)
            )
    updated = await knowledge.update_annotation(
        saved.id, user.id, first.id, AnnotationUpdate(body="新想法", color="pink", revision=1)
    )
    assert updated.color == "pink" and updated.revision == 2
    with pytest.raises(RevisionConflictError):
        await knowledge.delete_annotation(saved.id, user.id, first.id, 1)
    await knowledge.delete_annotation(saved.id, user.id, first.id, 2)
    assert await knowledge.list_annotations(saved.id, user.id) == []
    with pytest.raises(ValueError, match="content"):
        await knowledge.create_annotation(second.id, user.id, anchor())


async def test_full_content_note_annotation_and_keyword_intersection(db_session):
    user, other, _, entry = await setup_library(db_session)
    service = BookmarkService(db_session)
    saved, _ = await service.create_bookmark(user.id, BookmarkCreate(entry_id=entry.id))
    knowledge = BookmarkKnowledgeService(db_session)
    await knowledge.save_note(
        saved.id, user.id, BookmarkNoteUpdate(body="量子知识 100% _ literal", revision=0)
    )
    annotation = await knowledge.create_annotation(saved.id, user.id, anchor(body="重要批注"))
    for word, field in [
        ("Preserved", "content"),
        ("量子", "note"),
        ("重要", "annotation"),
        ("100%", "note"),
        ("_", "note"),
    ]:
        result = await service.get_bookmarks(user.id, search=word, sort="relevance")
        assert result.total == 1
        assert any(match.field == field for match in result.items[0].search_matches)
        assert (await service.get_bookmarks(other.id, search=word)).total == 0
    assert (await service.get_bookmarks(user.id, search="量子 Preserved 重要")).total == 1
    assert (await service.get_bookmarks(user.id, search="量子 不存在")).total == 0
    await knowledge.update_annotation(
        saved.id, user.id, annotation.id, AnnotationUpdate(body="替换内容", revision=1)
    )
    assert (await service.get_bookmarks(user.id, search="重要")).total == 0
    assert (await service.get_bookmarks(user.id, search="替换")).total == 1
    await service.update_bookmark(saved.id, user.id, BookmarkUpdate(title="New title"))
    assert (await service.get_bookmarks(user.id, search="New title")).total == 1
    # Worker writes go through the same projection listeners.
    bookmark = await db_session.get(Bookmark, saved.id)
    bookmark.content = (
        "<p>中文正文 &amp; entities</p><script>secretScript</script><style>secretStyle</style>"
    )
    await db_session.commit()
    assert (await service.get_bookmarks(user.id, search="中文正文")).total == 1
    assert (await service.get_bookmarks(user.id, search="secretScript")).total == 0
    assert (await service.get_bookmarks(user.id, search="secretStyle")).total == 0
    await knowledge.save_note(saved.id, user.id, BookmarkNoteUpdate(body="", revision=1))
    assert (await service.get_bookmarks(user.id, search="量子")).total == 0


async def test_undo_restores_personal_content_and_search(db_session):
    user, _, _, entry = await setup_library(db_session)
    service = BookmarkService(db_session, cast(Any, UndoCache()))
    saved, _ = await service.create_bookmark(user.id, BookmarkCreate(entry_id=entry.id))
    knowledge = BookmarkKnowledgeService(db_session)
    note = await knowledge.save_note(
        saved.id, user.id, BookmarkNoteUpdate(body="私人想法", revision=0)
    )
    annotation = await knowledge.create_annotation(saved.id, user.id, anchor(body="保留批注"))
    await service.delete_bookmark(saved.id, user.id)
    assert (
        await db_session.scalar(select(BookmarkNote).where(BookmarkNote.bookmark_id == saved.id))
        is None
    )
    assert (
        await db_session.scalar(
            select(BookmarkAnnotation).where(BookmarkAnnotation.bookmark_id == saved.id)
        )
        is None
    )
    await service.restore_bookmark(saved.id, user.id)
    assert await knowledge.get_note(saved.id, user.id) == note
    assert await knowledge.list_annotations(saved.id, user.id) == [annotation]
    assert (await service.get_bookmarks(user.id, search="私人想法 保留批注")).total == 1


async def test_relevance_prefers_titles_over_content(db_session):
    user, _, _, entry = await setup_library(db_session)
    service = BookmarkService(db_session)
    await service.create_bookmark(user.id, BookmarkCreate(entry_id=entry.id))
    title_hit, _ = await service.create_bookmark(
        user.id, BookmarkCreate(url="https://example.org/title", title="Preserved")
    )
    result = await service.get_bookmarks(user.id, search="Preserved", sort="relevance", per_page=1)
    assert result.items[0].id == title_hit.id and result.total == 2


async def test_knowledge_api_contract(client, auth_headers):
    response = await client.post(
        "/api/bookmarks",
        headers=auth_headers,
        json={"url": "https://example.org/knowledge", "title": "Knowledge"},
    )
    bookmark_id = response.json()["id"]
    note_path = f"/api/bookmarks/{bookmark_id}/note"
    assert (await client.get(note_path, headers=auth_headers)).json()["revision"] == 0
    assert (
        await client.put(note_path, headers=auth_headers, json={"body": "我的笔记", "revision": 0})
    ).status_code == 200
    assert (
        await client.put(note_path, headers=auth_headers, json={"body": "冲突", "revision": 0})
    ).status_code == 409
    assert (
        await client.put(note_path, headers=auth_headers, json={"body": "x"})
    ).status_code == 422
    annotations_path = f"/api/bookmarks/{bookmark_id}/annotations"
    assert (
        await client.post(annotations_path, headers=auth_headers, json=anchor().model_dump())
    ).status_code == 400
    bad = anchor().model_dump()
    bad["end"] = 2
    assert (await client.post(annotations_path, headers=auth_headers, json=bad)).status_code == 422
    assert (await client.get(note_path)).status_code in (401, 403)


def test_search_projection_removes_hidden_content_and_decodes_entities():
    assert (
        html_text("<p>A &amp; B</p><script>ignore</script><style>ignore</style><p>中文</p>")
        == "A & B 中文"
    )
