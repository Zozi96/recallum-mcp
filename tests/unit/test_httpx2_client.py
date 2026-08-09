"""Assert the supported TestClient path uses httpx2 (task 9.7)."""

from __future__ import annotations

import warnings

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import StarletteDeprecationWarning


def test_httpx2_is_the_supported_test_client_transport():
    assert httpx2.__version__
    app = FastAPI()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", StarletteDeprecationWarning)
        with TestClient(app) as client:
            assert client.get("/docs").status_code == 200

    deprecated = [
        w
        for w in caught
        if issubclass(w.category, StarletteDeprecationWarning)
        and "httpx" in str(w.message).lower()
    ]
    assert deprecated == [], f"unexpected TestClient/httpx deprecations: {deprecated}"


def test_starlette_httpx_deprecation_fails_under_pytest_filter():
    with pytest.raises(StarletteDeprecationWarning):
        warnings.warn(
            "Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.",
            StarletteDeprecationWarning,
            stacklevel=1,
        )
