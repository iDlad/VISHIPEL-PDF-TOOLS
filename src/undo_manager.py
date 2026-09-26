"""
/src/undo_manager.py
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class UndoManager:

    def __init__(self) -> None:
        self._undo_stack: List[Dict[str, Any]] = []
        self._redo_stack: List[Dict[str, Any]] = []

    @staticmethod
    def _clone_snapshot(snapshot: dict) -> dict:

        return {
            "order": list(snapshot["order"]),
            "rotations": dict(snapshot["rotations"]),
            "marked": set(snapshot["marked"]),
        }

    def register(self, action_type: str, before_snapshot: dict, after_snapshot: dict) -> None:
        self._undo_stack.append({
            "action_type": action_type,
            "before": self._clone_snapshot(before_snapshot),
            "after": self._clone_snapshot(after_snapshot),
        })
        self._redo_stack.clear()

    def undo(self) -> Optional[dict]:

        if not self._undo_stack:
            return None
        entry = self._undo_stack.pop()
        self._redo_stack.append(entry)
        return self._clone_snapshot(entry["before"])

    def redo(self) -> Optional[dict]:

        if not self._redo_stack:
            return None
        entry = self._redo_stack.pop()
        self._undo_stack.append(entry)
        return self._clone_snapshot(entry["after"])

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()