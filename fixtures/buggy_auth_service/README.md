# Buggy authentication service

This is Exagium's first offline coding-agent fixture. It contains a deterministic concurrency bug:
two overlapping authentication requests can return the same user even when their tokens belong to
different identities.

The fixture intentionally uses only the Python standard library, so an isolated Exagium worktree
can validate it without installing packages or using the network.

Run the ground-truth validation from the Exagium repository root:

```powershell
python -m unittest discover -s fixtures/buggy_auth_service/tests -v
```

The committed baseline must fail the concurrent-request test. Agents are expected to repair the
implementation without weakening or removing the test.
