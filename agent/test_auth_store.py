import tempfile
from pathlib import Path
from auth_store import save_token, load_token

with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / "test.dpapi"
    expected = {"access_token": "test-value-not-real", "expires_in": 100}
    save_token(path, expected)
    restored = load_token(path)
    assert restored == expected
    assert b"test-value-not-real" not in path.read_bytes()
print("PASS Windows DPAPI: OAuth token data encrypted for current account")
