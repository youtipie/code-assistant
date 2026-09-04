"""Shared leaf package: settings, DB session lifecycle, ORM models, embeddings,
hybrid retrieval.

Deliberately empty -- import from the submodule that owns the thing, so that
importing one does not drag in the others. `agent` depends on this package but
must stay persistence-free, which a re-exporting root would quietly undo.
"""
