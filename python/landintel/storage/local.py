from pathlib import Path

from landintel.storage.base import StorageAdapter, StoredObject


class LocalFileStorageAdapter(StorageAdapter):
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, storage_path: str, payload: bytes, *, content_type: str) -> StoredObject:
        del content_type

        destination = self.root / storage_path
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists():
            existing = destination.read_bytes()
            if existing != payload:
                raise ValueError(f"Refusing to overwrite immutable raw asset at {destination}")
        else:
            destination.write_bytes(payload)

        return StoredObject(storage_path=storage_path, size_bytes=len(payload))

