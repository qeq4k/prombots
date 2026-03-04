"""
Handlers для бота
"""
from .user_commands import router as user_commands_router
from .new_features import router as new_features_router
from .reactions import router as reactions_router
from .menu_buttons import router as menu_buttons_router
from .callbacks import router as callbacks_router
from .search_admin import router as search_admin_router
from .search_only import router as search_only_router

__all__ = [
    "user_commands_router",
    "new_features_router",
    "reactions_router",
    "menu_buttons_router",
    "callbacks_router",
    "search_admin_router",
    "search_only_router",
]
