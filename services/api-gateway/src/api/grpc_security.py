"""
gRPC Security
=============

Authentication interceptors and mTLS channel helpers for secure inter-service
communication.

Provides:
  - TokenAuthInterceptor: attaches a shared service token to outbound gRPC
    calls (client-side), and validates it on inbound calls (server-side).
  - secure_channel / secure_server_credentials: build mTLS-enabled channels and
    server credentials from PEM files.

Degrades gracefully: when no token / certs are configured, falls back to
insecure channels (suitable for local development).
"""

from __future__ import annotations

import collections
import logging
import os
from typing import Callable, Optional, Sequence, Tuple

import grpc

logger = logging.getLogger(__name__)

SERVICE_TOKEN_ENV = "GALILEO_SERVICE_TOKEN"
_AUTH_METADATA_KEY = "x-service-token"


class _ClientCallDetails(
    collections.namedtuple(
        "_ClientCallDetails",
        ("method", "timeout", "metadata", "credentials",
         "wait_for_ready", "compression"),
    ),
    grpc.ClientCallDetails,
):
    """Concrete ClientCallDetails so interceptors can rewrite metadata."""


# ---------------------------------------------------------------------------
# Client-side: attach service token to outbound calls
# ---------------------------------------------------------------------------
class TokenAuthClientInterceptor(
    grpc.UnaryUnaryClientInterceptor,
    grpc.UnaryStreamClientInterceptor,
):
    """Attaches a shared service token to outbound gRPC metadata."""

    def __init__(self, token: str):
        self._token = token

    def _augment(self, client_call_details):
        metadata = list(client_call_details.metadata or [])
        metadata.append((_AUTH_METADATA_KEY, self._token))
        # Rebuild the call details with the new metadata.
        return _ClientCallDetails(
            client_call_details.method,
            client_call_details.timeout,
            metadata,
            client_call_details.credentials,
            getattr(client_call_details, "wait_for_ready", None),
            getattr(client_call_details, "compression", None),
        )

    def intercept_unary_unary(self, continuation, client_call_details, request):
        return continuation(self._augment(client_call_details), request)

    def intercept_unary_stream(self, continuation, client_call_details, request):
        return continuation(self._augment(client_call_details), request)


# ---------------------------------------------------------------------------
# Server-side: validate inbound service token
# ---------------------------------------------------------------------------
class TokenAuthServerInterceptor(grpc.ServerInterceptor):
    """Rejects inbound calls that do not carry the expected service token.

    Methods listed in ``exempt_methods`` (e.g. health checks) bypass the check.
    """

    def __init__(self, token: str, exempt_methods: Optional[Sequence[str]] = None):
        self._token = token
        self._exempt = set(exempt_methods or [])

        def deny(_ignored_request, context):
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid service token")

        self._deny_handler = grpc.unary_unary_rpc_method_handler(deny)

    def intercept_service(self, continuation, handler_call_details):
        method = handler_call_details.method or ""
        # Allow exempt methods (health checks, reflection) through.
        if any(method.endswith(m) for m in self._exempt):
            return continuation(handler_call_details)

        metadata = dict(handler_call_details.invocation_metadata or [])
        token = metadata.get(_AUTH_METADATA_KEY)
        if token != self._token:
            logger.warning("Rejected gRPC call to %s: bad service token", method)
            return self._deny_handler
        return continuation(handler_call_details)


# ---------------------------------------------------------------------------
# Channel / credential helpers (mTLS)
# ---------------------------------------------------------------------------
def _read(path: Optional[str]) -> Optional[bytes]:
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as exc:
        logger.warning("Could not read cert file %s: %s", path, exc)
        return None


def make_client_channel(address: str) -> grpc.Channel:
    """Build a gRPC channel to ``address``.

    Uses mTLS if GALILEO_TLS_* env vars point to valid PEM files, otherwise an
    insecure channel. A token interceptor is layered on when
    GALILEO_SERVICE_TOKEN is set.
    """
    root_certs = _read(os.getenv("GALILEO_TLS_CA"))
    private_key = _read(os.getenv("GALILEO_TLS_CLIENT_KEY"))
    cert_chain = _read(os.getenv("GALILEO_TLS_CLIENT_CERT"))

    if root_certs and private_key and cert_chain:
        creds = grpc.ssl_channel_credentials(
            root_certificates=root_certs,
            private_key=private_key,
            certificate_chain=cert_chain,
        )
        channel = grpc.secure_channel(address, creds)
        logger.info("Created mTLS channel to %s", address)
    else:
        channel = grpc.insecure_channel(address)
        logger.debug("Created insecure channel to %s (no TLS configured)", address)

    token = os.getenv(SERVICE_TOKEN_ENV)
    if token:
        channel = grpc.intercept_channel(channel, TokenAuthClientInterceptor(token))
    return channel


def make_server_credentials() -> Optional[grpc.ServerCredentials]:
    """Build mTLS server credentials from env-configured PEM files.

    Returns None when TLS is not configured (caller should use an insecure
    port in that case).
    """
    root_certs = _read(os.getenv("GALILEO_TLS_CA"))
    private_key = _read(os.getenv("GALILEO_TLS_SERVER_KEY"))
    cert_chain = _read(os.getenv("GALILEO_TLS_SERVER_CERT"))

    if not (private_key and cert_chain):
        logger.debug("No server TLS configured; use an insecure port")
        return None

    require_client_auth = root_certs is not None
    creds = grpc.ssl_server_credentials(
        [(private_key, cert_chain)],
        root_certificates=root_certs,
        require_client_auth=require_client_auth,
    )
    logger.info("Created mTLS server credentials (mutual auth: %s)",
                require_client_auth)
    return creds


def server_auth_interceptors() -> Sequence[grpc.ServerInterceptor]:
    """Return the server interceptors to install (token auth if configured)."""
    token = os.getenv(SERVICE_TOKEN_ENV)
    if not token:
        return ()
    # Health checks are exempt so liveness probes work without the token.
    return (TokenAuthServerInterceptor(token, exempt_methods=["HealthCheck"]),)
