"""
/src/undo_logic.py

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import fitz  # PyMuPDF


@dataclass
class InsertUndoEntry:
    """1 lượt Chèn đã thực hiện — đủ thông tin để hoàn tác đúng lượt đó."""
    start_index: int   
    page_count: int     


class InsertUndoManager:

    def __init__(self) -> None:
        self._stack: List[InsertUndoEntry] = []

    def register(self, start_index: int, page_count: int = 1) -> None:

        self._stack.append(InsertUndoEntry(start_index=start_index, page_count=page_count))

    def can_undo(self) -> bool:
        return bool(self._stack)

    def undo(self, working_document: fitz.Document) -> bool:
        if not self._stack:
            return False
        entry = self._stack.pop()
        for _ in range(entry.page_count):
            working_document.delete_page(entry.start_index)
        return True

    def clear(self) -> None:
        self._stack.clear()