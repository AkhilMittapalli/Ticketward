"""Redis client factory (jobs, rate limits, cache; spec §7.1)."""

from redis.asyncio import Redis

from ticketward.core.config import Settings

_HEALTH_CHECK_INTERVAL_S = 30


def create_redis_client(settings: Settings) -> Redis:
    """Create a lazily-connecting Redis client.

    The password is passed separately from the URL (``TW_REDIS_PASSWORD`` or the
    ``tw_redis_password`` secret file) so it never appears in URLs or env dumps.

    Args:
        settings: Application settings.

    Returns:
        A ``redis.asyncio.Redis`` client; no connection is opened until first use.
    """
    return Redis.from_url(
        settings.redis_url,
        password=settings.redis_password.get_secret_value() if settings.redis_password else None,
        socket_connect_timeout=settings.redis_socket_timeout_s,
        socket_timeout=settings.redis_socket_timeout_s,
        health_check_interval=_HEALTH_CHECK_INTERVAL_S,
        client_name=settings.service_name,
    )
