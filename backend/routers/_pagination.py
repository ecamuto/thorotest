"""Shared limit/offset pagination for list endpoints.

Responses stay plain JSON arrays (backward compatible); the total row count
for the filtered query is exposed in the X-Total-Count response header so
clients can render "showing N of M" / page controls.
"""
from fastapi import Response

# Hard ceiling on rows returned by any list endpoint. Also the default, so
# legacy clients that never send limit/offset keep working but can no longer
# pull an unbounded table into memory.
MAX_LIMIT = 1000


def paginate(q, response: Response, limit: int, offset: int) -> list:
    """Apply offset/limit to a SQLAlchemy query and set X-Total-Count."""
    response.headers["X-Total-Count"] = str(q.count())
    return q.offset(offset).limit(min(limit, MAX_LIMIT)).all()
