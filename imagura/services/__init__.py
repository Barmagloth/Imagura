"""Application services for loading, texture ownership, and other orchestration."""

__all__ = [
    "AnimatedContentCache",
    "AsyncContentLoader",
    "IdleDetector",
    "LargeTextureCache",
    "ThumbnailService",
    "TextureManager",
]


def __getattr__(name: str):
    if name == "AnimatedContentCache":
        from .animated_content_cache import AnimatedContentCache
        return AnimatedContentCache
    if name in {"AsyncContentLoader", "IdleDetector"}:
        from .loader import AsyncContentLoader, IdleDetector
        return {"AsyncContentLoader": AsyncContentLoader, "IdleDetector": IdleDetector}[name]
    if name == "TextureManager":
        from .textures import TextureManager
        return TextureManager
    if name == "LargeTextureCache":
        from .large_texture_cache import LargeTextureCache
        return LargeTextureCache
    if name == "ThumbnailService":
        from .thumbnails import ThumbnailService
        return ThumbnailService
    raise AttributeError(name)
