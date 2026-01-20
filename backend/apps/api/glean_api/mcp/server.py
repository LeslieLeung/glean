"""
Glean MCP Server.

FastMCP server for exposing Glean functionality to LLM clients.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from glean_database.session import get_session_context

from ..config import settings
from .auth import APITokenVerifier


@dataclass
class MCPContext:
    """MCP application context with database session factory."""

    session_factory: Any


@asynccontextmanager
async def mcp_lifespan(_server: FastMCP) -> AsyncIterator[MCPContext]:
    """
    Manage MCP server lifecycle.

    Provides the database session factory for tool operations.
    """
    yield MCPContext(session_factory=get_session_context)


def create_mcp_server() -> FastMCP:
    """
    Create and configure the MCP server.

    Returns:
        Configured FastMCP server instance.
    """
    # Configure authentication settings for token-based auth
    # URLs are configurable via MCP_ISSUER_URL and MCP_RESOURCE_SERVER_URL environment variables
    auth_settings = AuthSettings(
        issuer_url=AnyHttpUrl(settings.mcp_issuer_url),
        resource_server_url=AnyHttpUrl(settings.mcp_resource_server_url),
    )

    mcp = FastMCP(
        name="Glean MCP Server",
        instructions="""
Glean is a personal knowledge management tool and RSS reader.
Use these tools to search and retrieve articles from your subscribed feeds.

Available tools:
- search_entries: Search articles by keyword, optionally filtered by feed
- get_entry: Get full details of a specific article
- list_entries_by_date: List articles within a date range
- list_subscriptions: List your RSS feed subscriptions
        """.strip(),
        lifespan=mcp_lifespan,
        auth=auth_settings,
        token_verifier=APITokenVerifier(),
    )

    # Register tools
    from .tools.entries import get_entry, list_entries_by_date, search_entries
    from .tools.subscriptions import list_subscriptions

    mcp.tool()(search_entries)
    mcp.tool()(get_entry)
    mcp.tool()(list_entries_by_date)
    mcp.tool()(list_subscriptions)

    return mcp


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Get a database session for MCP tool operations."""
    async with get_session_context() as session:
        yield session
