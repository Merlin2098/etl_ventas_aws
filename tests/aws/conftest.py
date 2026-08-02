from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
import warnings
from pathlib import Path

import boto3
import pytest
from dotenv import load_dotenv

_CREDS_FILE = Path(__file__).parent.parent.parent / "infra" / "env" / ".env.credentials"
load_dotenv(_CREDS_FILE)


def _enable_os_trust_store() -> bool:
    """Make botocore validate TLS via the OS trust store (Windows/macOS/Linux).

    Works around the Python 3.14 / OpenSSL 3 rejection of AWS intermediate certs
    without disabling verification. Only needed on 3.14+; earlier Pythons
    validate AWS certs fine. See ai/skills/aws/aws_smoke_testing.md.
    """
    if sys.version_info < (3, 14):
        return True
    try:
        import truststore
        import botocore.httpsession as hs
    except ImportError:
        return False
    if not getattr(hs, "_truststore_patched", False):
        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        hs.create_urllib3_context = lambda *a, **k: ctx
        hs._truststore_patched = True
    return True


_TRUST_OK = _enable_os_trust_store()


def _has_credentials() -> bool:
    return bool(
        os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY")
    )


@pytest.fixture(scope="session")
def aws_client():
    if not _has_credentials():
        pytest.skip(
            "AWS credentials not found — set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY or provide infra/env/.env.credentials"
        )

    verify = True
    if not _TRUST_OK:
        warnings.warn(
            "truststore unavailable on Python 3.14+ — falling back to verify=False. "
            "Install requirements.txt (pip install -r requirements.txt) to restore certificate verification.",
            stacklevel=2,
        )
        verify = False

    def _get(service: str):
        return boto3.client(
            service,
            aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            verify=verify,
        )

    return _get


@pytest.fixture(scope="session")
def tf_outputs() -> dict:
    result = subprocess.run(
        ["terraform", "-chdir=infra", "output", "-json"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)
