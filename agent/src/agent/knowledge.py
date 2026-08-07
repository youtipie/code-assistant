"""Names of the knowledge MCP server and its tools.

`tool_rules` (which decides whether a call is allowed) and `rendering` (which
turns its result into text for the model) both dispatch on these, so they live
here rather than being spelled out in both. Tool names appearing inside prompt
prose stay as prose -- there they are English, not identifiers.
"""

from __future__ import annotations

OWN_SERVER = "knowledge"

SEARCH_DOCS = "search_docs"
SEARCH_CODE = "search_code"
OUTLINE = "outline"
READ_FILE = "read_file"

SEARCH_TOOLS = (SEARCH_DOCS, SEARCH_CODE)
