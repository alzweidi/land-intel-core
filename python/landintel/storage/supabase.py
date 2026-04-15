import httpx

from landintel.config import Settings
from landintel.storage.base import StorageAdapter, StoredObject


class SupabaseStorageAdapter(StorageAdapter):
    def __init__(self, settings: Settings) -> None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ValueError("Supabase storage requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        self.base_url = settings.supabase_url.rstrip("/")
        self.bucket = settings.supabase_storage_bucket
        self.service_role_key = settings.supabase_service_role_key

    def put_bytes(self, storage_path: str, payload: bytes, *, content_type: str) -> StoredObject:
        url = f"{self.base_url}/storage/v1/object/{self.bucket}/{storage_path}"
        response = httpx.post(
            url,
            content=payload,
            headers={
                "Authorization": f"Bearer {self.service_role_key}",
                "apikey": self.service_role_key,
                "Content-Type": content_type,
                "x-upsert": "false",
            },
            timeout=30.0,
        )
        if response.status_code not in {200, 201}:
            raise RuntimeError(
                f"Supabase Storage upload failed: {response.status_code} {response.text[:300]}"
            )
        return StoredObject(storage_path=storage_path, size_bytes=len(payload))

