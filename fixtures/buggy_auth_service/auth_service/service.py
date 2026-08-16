from __future__ import annotations

import asyncio
from dataclasses import dataclass


class AuthenticationError(Exception):
    """Token 无法映射到有效用户。"""


@dataclass(frozen=True, slots=True)
class User:
    id: str
    display_name: str
    active: bool = True


class InMemoryIdentityStore:
    def __init__(self, tokens: dict[str, str], users: dict[str, User]) -> None:
        self._tokens = tokens
        self._users = users

    async def user_id_for_token(self, token: str) -> str | None:
        # 这些调度点模拟 Web 服务中相互独立的数据库查询。
        await asyncio.sleep(0)
        return self._tokens.get(token)

    async def load_user(self, user_id: str) -> User | None:
        await asyncio.sleep(0)
        return self._users.get(user_id)


class AuthenticationService:
    def __init__(self, store: InMemoryIdentityStore) -> None:
        self._store = store
        self._candidate_user_id: str | None = None

    async def authenticate(self, token: str) -> User:
        self._candidate_user_id = await self._store.user_id_for_token(token)
        if self._candidate_user_id is None:
            raise AuthenticationError("invalid token")

        # 本应属于单次请求的状态被错误地保存在共享服务实例中；当前协程挂起时，
        # 另一个请求可以覆盖该状态，从而稳定复现竞态问题。
        await asyncio.sleep(0)
        user = await self._store.load_user(self._candidate_user_id)
        if user is None or not user.active:
            raise AuthenticationError("inactive or missing user")
        return user
