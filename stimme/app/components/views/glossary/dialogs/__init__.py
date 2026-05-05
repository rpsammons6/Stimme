"""Glossary dialog components — edit term, new glossary, save changes, conflict resolution."""

from .conflict_resolution import ConflictResolutionDialog
from .edit_term import EditTermDialog
from .new_glossary import NewGlossaryDialog
from .save_changes import SaveChangesDialog

__all__ = [
    "ConflictResolutionDialog",
    "EditTermDialog",
    "NewGlossaryDialog",
    "SaveChangesDialog",
]
