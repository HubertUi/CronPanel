"""Request helpers for HTTP transport concerns."""

from fastapi import Request


def get_client_ip(request: Request) -> str | None:
    """Extract the client IP from the request.

    X-Forwarded-For is honored because production deployments sit behind a
    reverse proxy; until a trusted-proxy allowlist exists, this header must
    be treated as client-controlled data (documented limitation).
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first_hop = forwarded_for.split(",")[0].strip()
        if first_hop:
            return first_hop
    return request.client.host if request.client else None
