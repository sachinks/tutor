"""Shared request dependencies: the engine and provider created at start-up (see main.create_app)."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine

from ..providers.base import ModelProvider


def _engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.engine
    return engine


def _provider(request: Request) -> ModelProvider:
    provider: ModelProvider = request.app.state.provider
    return provider


Engine = Annotated[AsyncEngine, Depends(_engine)]
Provider = Annotated[ModelProvider, Depends(_provider)]
