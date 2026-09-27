"""Pure-ASGI middleware (no ``BaseHTTPMiddleware``: streaming-safe, contextvar-safe).

Order, outermost first (wired in ``ticketward.main.create_app``):
request_id -> security_headers -> CORS (dev only) -> body_limit (per route, 413) ->
content_type (JSON only, 415) -> unhandled errors.
"""
