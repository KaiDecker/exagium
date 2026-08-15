from __future__ import annotations

import asyncio
import unittest

from fixtures.buggy_auth_service.auth_service import (
    AuthenticationError,
    AuthenticationService,
    InMemoryIdentityStore,
    User,
)


def service() -> AuthenticationService:
    return AuthenticationService(
        InMemoryIdentityStore(
            tokens={"token-alice": "alice", "token-bob": "bob", "token-disabled": "disabled"},
            users={
                "alice": User(id="alice", display_name="Alice"),
                "bob": User(id="bob", display_name="Bob"),
                "disabled": User(id="disabled", display_name="Disabled", active=False),
            },
        )
    )


class AuthenticationServiceTests(unittest.TestCase):
    def test_valid_token_returns_its_user(self) -> None:
        user = asyncio.run(service().authenticate("token-alice"))

        self.assertEqual(user.id, "alice")

    def test_invalid_and_inactive_users_are_rejected(self) -> None:
        auth = service()

        with self.assertRaises(AuthenticationError):
            asyncio.run(auth.authenticate("missing"))
        with self.assertRaises(AuthenticationError):
            asyncio.run(auth.authenticate("token-disabled"))

    def test_concurrent_requests_do_not_leak_identity(self) -> None:
        async def authenticate_both() -> list[User]:
            auth = service()
            return list(
                await asyncio.gather(
                    auth.authenticate("token-alice"),
                    auth.authenticate("token-bob"),
                )
            )

        users = asyncio.run(authenticate_both())

        self.assertEqual([user.id for user in users], ["alice", "bob"])


if __name__ == "__main__":
    unittest.main()
