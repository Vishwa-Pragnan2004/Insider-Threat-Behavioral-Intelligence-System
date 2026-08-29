"""
ITBIS — Identity Module: Redis Token Store
Implements IRefreshTokenStore using Redis.
"""

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.modules.identity.domain.repositories import IRefreshTokenStore


class RedisTokenStore(IRefreshTokenStore):
    """
    Stores refresh tokens in Redis.
    Uses the JTI as the key and the User ID as the value.
    Sets a TTL on the key matching the token's expiration.

    NOTE: The Redis client MUST be configured with decode_responses=True so
    that get() / smembers() return str, not bytes.
    """

    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client
        self._prefix = "refresh_token:"
        self._user_index_prefix = "user_tokens:"

    async def store(self, jti: str, user_id: str, ttl_seconds: int) -> None:
        key = f"{self._prefix}{jti}"
        user_key = f"{self._user_index_prefix}{user_id}"

        # Use a pipeline to batch the three writes atomically.
        # fakeredis supports pipeline(transaction=True) with the same semantics.
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.set(key, user_id, ex=ttl_seconds)  # store JTI → user_id with TTL
            pipe.sadd(user_key, jti)                # add JTI to user's set
            pipe.expire(user_key, ttl_seconds)       # renew set TTL
            await pipe.execute()

    async def is_valid(self, jti: str) -> bool:
        key = f"{self._prefix}{jti}"
        exists = await self.redis.exists(key)
        return exists > 0

    async def revoke(self, jti: str) -> None:
        key = f"{self._prefix}{jti}"

        # get() returns str when decode_responses=True, None if missing
        user_id = await self.redis.get(key)

        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.delete(key)
            if user_id:
                user_key = f"{self._user_index_prefix}{user_id}"
                pipe.srem(user_key, jti)
            await pipe.execute()

    async def revoke_all_for_user(self, user_id: str) -> None:
        user_key = f"{self._user_index_prefix}{user_id}"

        # smembers() returns Set[str] when decode_responses=True
        jtis: set[str] = await self.redis.smembers(user_key)

        if not jtis:
            return

        async with self.redis.pipeline(transaction=True) as pipe:
            for jti in jtis:
                pipe.delete(f"{self._prefix}{jti}")
            pipe.delete(user_key)
            await pipe.execute()
