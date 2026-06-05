"""
gRPC Security Tests
==================

Tests the token auth interceptors and channel/credential helpers.
"""

import os

import grpc
import pytest

from api.grpc_security import (
    TokenAuthClientInterceptor,
    TokenAuthServerInterceptor,
    make_client_channel,
    make_server_credentials,
    server_auth_interceptors,
    _AUTH_METADATA_KEY,
)


class _FakeCallDetails:
    def __init__(self, method, metadata=None):
        self.method = method
        self.timeout = None
        self.metadata = metadata or []
        self.credentials = None
        self.wait_for_ready = None
        self.compression = None


class _FakeHandlerCallDetails:
    def __init__(self, method, metadata=None):
        self.method = method
        self.invocation_metadata = metadata or []


class TestServerInterceptor:

    def test_rejects_missing_token(self):
        interceptor = TokenAuthServerInterceptor("secret")
        called = {"continued": False}

        def continuation(details):
            called["continued"] = True
            return "real_handler"

        details = _FakeHandlerCallDetails("/galileo.data.DataService/QueryGravity")
        handler = interceptor.intercept_service(continuation, details)
        # Missing token -> deny handler returned, continuation NOT called.
        assert called["continued"] is False
        assert handler is interceptor._deny_handler

    def test_accepts_valid_token(self):
        interceptor = TokenAuthServerInterceptor("secret")
        called = {"continued": False}

        def continuation(details):
            called["continued"] = True
            return "real_handler"

        details = _FakeHandlerCallDetails(
            "/galileo.data.DataService/QueryGravity",
            metadata=[(_AUTH_METADATA_KEY, "secret")],
        )
        handler = interceptor.intercept_service(continuation, details)
        assert called["continued"] is True
        assert handler == "real_handler"

    def test_exempt_method_bypasses_auth(self):
        interceptor = TokenAuthServerInterceptor("secret",
                                                 exempt_methods=["HealthCheck"])
        called = {"continued": False}

        def continuation(details):
            called["continued"] = True
            return "real_handler"

        details = _FakeHandlerCallDetails(
            "/galileo.data.DataService/HealthCheck")  # no token
        handler = interceptor.intercept_service(continuation, details)
        # Exempt -> continuation called despite missing token.
        assert called["continued"] is True


class TestClientInterceptor:

    def test_augments_metadata(self):
        interceptor = TokenAuthClientInterceptor("tok123")
        details = _FakeCallDetails("/svc/Method", metadata=[("existing", "v")])
        new_details = interceptor._augment(details)
        keys = dict(new_details.metadata)
        assert keys[_AUTH_METADATA_KEY] == "tok123"
        assert keys["existing"] == "v"


class TestChannelHelpers:

    def test_insecure_channel_without_tls(self, monkeypatch):
        # No TLS env vars -> insecure channel.
        for var in ("GALILEO_TLS_CA", "GALILEO_TLS_CLIENT_KEY",
                    "GALILEO_TLS_CLIENT_CERT", "GALILEO_SERVICE_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        channel = make_client_channel("localhost:50051")
        assert channel is not None

    def test_no_server_creds_without_tls(self, monkeypatch):
        for var in ("GALILEO_TLS_CA", "GALILEO_TLS_SERVER_KEY",
                    "GALILEO_TLS_SERVER_CERT"):
            monkeypatch.delenv(var, raising=False)
        assert make_server_credentials() is None

    def test_no_interceptors_without_token(self, monkeypatch):
        monkeypatch.delenv("GALILEO_SERVICE_TOKEN", raising=False)
        assert server_auth_interceptors() == ()

    def test_interceptor_present_with_token(self, monkeypatch):
        monkeypatch.setenv("GALILEO_SERVICE_TOKEN", "abc")
        interceptors = server_auth_interceptors()
        assert len(interceptors) == 1
        assert isinstance(interceptors[0], TokenAuthServerInterceptor)
