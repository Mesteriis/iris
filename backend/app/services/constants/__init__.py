__all__ = [
    "MType",
    "AssetType",
    "ASSET_EMBEDDING_LENS_MAP",
    "ModelType",  # Алиас для совместимости
]

from .assets import AssetType
from .embedding import ASSET_EMBEDDING_LENS_MAP
from .models import MType

# Алиас для совместимости с Clone моделями
ModelType = MType
