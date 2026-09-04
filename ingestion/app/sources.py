"""What gets indexed: the repositories and the paths within them.

To index a different corpus, edit SOURCES here and set CORPUS_REPOS to match
(see README.md).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    repo: str  # owner/name
    source_type: str  # code | doc
    paths: tuple[str, ...]  # repo-relative roots; () means whole repo
    exclude: tuple[str, ...] = ()  # repo-relative prefixes to skip

    @property
    def url(self) -> str:
        return f"https://github.com/{self.repo}.git"


SOURCES = (
    Source(
        repo="saleor/saleor",
        source_type="code",
        paths=(
            "saleor/payment",
            "saleor/order",
            "saleor/checkout",
            "saleor/webhook",
            "saleor/account",
            "saleor/plugins",
            "saleor/graphql/payment",
            "saleor/graphql/order",
            "saleor/graphql/checkout",
        ),
    ),
    Source(
        repo="saleor/saleor-docs",
        source_type="doc",
        paths=("docs",),
        # 2014 generated GraphQL reference files: 174k lines, 80% of the
        # corpus, near-identical, and they would swamp every retrieval with
        # boilerplate. Real questions are answered out of docs/developer.
        exclude=("docs/api-reference",),
    ),
)