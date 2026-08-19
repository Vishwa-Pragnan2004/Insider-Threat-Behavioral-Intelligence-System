"""
ITBIS — Identity Module: Redis Token Store
Implements IRefreshTokenStore using Redis.
"""

from typing import cast

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.modules.identity.domain.repositories import IRefreshTokenStore


class RedisTokenStore(IRefreshTokenStore):
    """
    Stores refresh tokens in Redis.
    Uses the JTI as the key and the User ID as the value.
    Sets a TTL on the key matching the token's expiration.
    """

    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client
        self._prefix = "refresh_token:"
        self._user_index_prefix = "user_tokens:"

    async def store(self, jti: str, user_id: str, ttl_seconds: int) -> None:
        key = f"{self._prefix}{jti}"
        user_key = f"{self._user_index_prefix}{user_id}"

        # Use a transaction (pipeline) to ensure both keys are set
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.setex(key, ttl_seconds, user_id)
            pipe.sadd(user_key, jti)
            pipe.expire(user_key, ttl_seconds)  # Renew user index TTL
            await pipe.execute()

    async def is_valid(self, jti: str) -> bool:
        key = f"{self._prefix}{jti}"
        exists = await self.redis.exists(key)
        return exists > 0

    async def revoke(self, jti: str) -> None:
        key = f"{self._prefix}{jti}"
        
        # We need the user_id to clean up the set
        user_id_bytes = await self.redis.get(key)
        
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.delete(key)
            if user_id_bytes:
                user_id_str = cast(bytes, user_id_bytes).decode('utf-8')
                user_key = f"{self._user_index_prefix}{user_id_str}"
                pipe.srem(user_key, jti)
            await pipe.execute()

    async def revoke_all_for_user(self, user_id: str) -> None:
        user_key = f"{self._user_index_prefix}{user_id}"
        
        # Get all JTIs for this user
        jtis = await self.redis.smembers(user_key)
        
        if not jtis:
            return
            
        # Delete all tokens and the index
        async with self.redis.pipeline(transaction=True) as pipe:
            for jti_bytes in jtis:
                jti_str = cast(bytes, jti_bytes).decode('utf-8')
                pipe.delete(f"{self._prefix}{jti_str}")
            pipe.delete(user_key)
            await pipe.execute()
