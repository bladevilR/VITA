from __future__ import annotations

import logging
import os

import faiss
import numpy as np

from .config import get_settings


logger = logging.getLogger("workstation_vita.vector")


class VectorStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.index = None
        self.id_map = None
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.settings.index_file):
            raise FileNotFoundError(f"未找到向量索引文件：{self.settings.index_file}")
        if not os.path.exists(self.settings.id_map_file):
            raise FileNotFoundError(f"未找到向量编号映射文件：{self.settings.id_map_file}")
        self.index = faiss.read_index(self.settings.index_file)
        self.id_map = np.load(self.settings.id_map_file, allow_pickle=True)
        logger.info("Vector store loaded: %s vectors", self.index.ntotal)

    @property
    def count(self) -> int:
        return int(self.index.ntotal if self.index is not None else 0)

    def search(self, embedding: list[float], top_k: int) -> list[str]:
        if self.index is None or self.id_map is None:
            return []
        distances, indices = self.index.search(np.array([embedding], dtype="float32"), k=top_k)
        return [str(ticket_id) for ticket_id in self.id_map[indices[0]]]
