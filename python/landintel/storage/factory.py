from landintel.config import Settings
from landintel.domain.enums import StorageBackend
from landintel.storage.base import StorageAdapter
from landintel.storage.local import LocalFileStorageAdapter
from landintel.storage.supabase import SupabaseStorageAdapter


def build_storage(settings: Settings) -> StorageAdapter:
    if settings.storage_backend == StorageBackend.LOCAL:
        return LocalFileStorageAdapter(settings.storage_local_root)
    if settings.storage_backend == StorageBackend.SUPABASE:
        return SupabaseStorageAdapter(settings)
    raise ValueError(f"Unsupported storage backend: {settings.storage_backend}")

