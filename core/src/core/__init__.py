"""Shared leaf package: settings, DB session lifecycle, ORM models, embeddings,
hybrid retrieval.

Deliberately empty. Import from the submodule that owns the thing --
`core.settings`, `core.db`, `core.models`, `core.embedding`,
`core.retrieval.search` -- so that importing one does not drag in the others.
`agent` depends on this package but must stay persistence-free, which a
re-exporting package root would quietly undo.
"""
