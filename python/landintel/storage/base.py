from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class StoredObject:
    storage_path: str
    size_bytes: int


class StorageAdapter(ABC):
    @abstractmethod
    def put_bytes(self, storage_path: str, payload: bytes, *, content_type: str) -> StoredObject:
        raise NotImplementedError

    @abstractmethod
    def get_bytes(self, storage_path: str) -> bytes:
        raise NotImplementedError
