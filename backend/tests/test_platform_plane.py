"""
Integration tests for the platform plane (Phase 10).

These tests hit a RUNNING backend on http://localhost:8000. They
auto-load credentials from backend/.env and skip gracefully if the
required values are missing.

Setup (one-time, in backend/.env — already gitignored):

    PLATFORM_TEST_ADMIN_EMAIL=969cey@gmail.com
    PLATFORM_TEST_ADMIN_PASSWORD=<your admin password>
    PLATFORM_TEST_TARGET_USER_ID=<uuid of a tenant user>
    PLATFORM_TEST_TARGET_USER_EMAIL=alice@agritech.dev
    PLATFORM_TEST_TARGET_USER_PASSWORD=<alice's password>

Run:
    cd backend
    py.bat -m pytest tests/test_platform_plane.py -v
"""
import os
import uuid
from pathlib import Path

# Load backend/.env so test creds are visible without shell config.
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH, override=False)

import pytest
import requests


BASE_URL = os.getenv("PLATFORM_TEST_BASE_URL", "http://localhost:8000/api/v1")

ADMIN_EMAIL = os.getenv("PLATFORM_TEST_ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("PLATFORM_TEST_ADMIN_PASSWORD")
TARGET_USER_ID = os.getenv("PLATFORM_TEST_TARGET_USER_ID")
TARGET_USER_EMAIL = os.getenv("PLATFORM_TEST_TARGET_USER_EMAIL")
TARGET_USER_PASSWORD = os.getenv("PLATFORM_TEST_TARGET_USER_PASSWORD")


pytestmark = pytest.mark.skipif(
    not (ADMIN_EMAIL and ADMIN_PASSWORD and TARGET_USER_ID),
    reason=(
        "Platform tests need PLATFORM_TEST_ADMIN_EMAIL, "
        "PLATFORM_TEST_ADMIN_PASSWORD, and PLATFORM_TEST_TARGET_USER_ID "
        "in backend/.env. See test_platform_plane.py header."
    ),
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def admin_token() -> str:
    r = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def target_user_headers() -> dict:
    if not (TARGET_USER_EMAIL and TARGET_USER_PASSWORD):
        pytest.skip("Need PLATFORM_TEST_TARGET_USER_EMAIL/PASSWORD for this test")
    r = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": TARGET_USER_EMAIL, "password": TARGET_USER_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Target login failed: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def support_session(admin_headers):
    """Create an active support session for the target user; end it after."""
    r = requests.post(
        f"{BASE_URL}/platform/support-sessions",
        headers=admin_headers,
        json={"target_user_id": TARGET_USER_ID, "reason": "pytest run"},
        timeout=15,
    )
    assert r.status_code == 201, f"Session creation failed: {r.status_code} {r.text}"
    data = r.json()
    yield data
    # Always end the session, even if the test failed.
    try:
        requests.post(
            f"{BASE_URL}/platform/support-sessions/{data['session']['id']}/end",
            headers=admin_headers,
            timeout=10,
        )
    except Exception:
        pass


def _find_target_tenant(admin_headers) -> dict | None:
    """Locate the tenant that owns the target user."""
    r = requests.get(f"{BASE_URL}/platform/tenants", headers=admin_headers, timeout=10)
    if r.status_code != 200:
        return None
    for t in r.json():
        r2 = requests.get(
            f"{BASE_URL}/platform/tenants/{t['id']}/users",
            headers=admin_headers,
            timeout=10,
        )
        if r2.status_code == 200 and any(u["id"] == TARGET_USER_ID for u in r2.json()):
            return t
    return None


# ============================================================================
# Platform stats
# ============================================================================

class TestPlatformStats:
    def test_tenant_user_cannot_reach_platform(self, target_user_headers):
        r = requests.get(
            f"{BASE_URL}/platform/stats",
            headers=target_user_headers,
            timeout=10,
        )
        assert r.status_code == 403
        assert "Platform user role required" in r.text

    def test_returns_valid_shape(self, admin_headers):
        r = requests.get(f"{BASE_URL}/platform/stats", headers=admin_headers, timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        for key in (
            "tenants_total", "tenants_active", "tenants_suspended",
            "users_total", "users_active",
            "farms_total", "plots_total", "devices_total",
            "diagnoses_total", "diagnoses_last_30d", "diagnoses_today",
        ):
            assert key in body, f"Missing field: {key}"
            assert isinstance(body[key], int), f"Non-int value for {key}"
        assert body["tenants_total"] == body["tenants_active"] + body["tenants_suspended"]

    def test_anonymous_rejected(self):
        r = requests.get(f"{BASE_URL}/platform/stats", timeout=10)
        assert r.status_code == 401


# ============================================================================
# Tenant list
# ============================================================================

class TestTenantList:
    def test_enriched_tenants(self, admin_headers):
        r = requests.get(f"{BASE_URL}/platform/tenants", headers=admin_headers, timeout=10)
        assert r.status_code == 200
        tenants = r.json()
        assert isinstance(tenants, list)
        if tenants:
            for key in (
                "id", "name", "slug", "is_active",
                "user_count", "farm_count", "plot_count",
                "diagnoses_last_30d",
            ):
                assert key in tenants[0], f"Missing field: {key}"

    def test_tenant_users_endpoint_returns_target(self, admin_headers):
        tenant = _find_target_tenant(admin_headers)
        assert tenant is not None, "Cannot locate target user in any tenant"
        r = requests.get(
            f"{BASE_URL}/platform/tenants/{tenant['id']}/users",
            headers=admin_headers,
            timeout=10,
        )
        assert r.status_code == 200
        users = r.json()
        assert any(u["id"] == TARGET_USER_ID for u in users)
        for u in users:
            assert "id" in u and "email" in u and "is_active" in u


# ============================================================================
# Suspension
# ============================================================================

class TestSuspension:
    def test_full_cycle(self, admin_headers, target_user_headers):
        tenant = _find_target_tenant(admin_headers)
        assert tenant is not None
        tenant_id = tenant["id"]
        was_active = tenant["is_active"]

        try:
            # Baseline
            r = requests.get(f"{BASE_URL}/plots", headers=target_user_headers, timeout=10)
            assert r.status_code == 200

            # Suspend
            r = requests.post(
                f"{BASE_URL}/platform/tenants/{tenant_id}/suspend",
                headers=admin_headers,
                json={"reason": "pytest suspend cycle"},
                timeout=10,
            )
            assert r.status_code == 200, r.text
            assert r.json()["is_active"] is False

            # Tenant user now blocked
            r = requests.get(f"{BASE_URL}/plots", headers=target_user_headers, timeout=10)
            assert r.status_code == 403
            assert "suspended" in r.text.lower()

            # Idempotent suspend
            r = requests.post(
                f"{BASE_URL}/platform/tenants/{tenant_id}/suspend",
                headers=admin_headers,
                json={"reason": "pytest - idempotent check"},
                timeout=10,
            )
            assert r.status_code == 200
            assert r.json()["is_active"] is False

            # Reactivate
            r = requests.post(
                f"{BASE_URL}/platform/tenants/{tenant_id}/reactivate",
                headers=admin_headers,
                timeout=10,
            )
            assert r.status_code == 200
            assert r.json()["is_active"] is True

            # User unblocked
            r = requests.get(f"{BASE_URL}/plots", headers=target_user_headers, timeout=10)
            assert r.status_code == 200

        finally:
            # Restore original state if we crashed mid-test
            if not was_active:
                requests.post(
                    f"{BASE_URL}/platform/tenants/{tenant_id}/suspend",
                    headers=admin_headers,
                    json={"reason": "pytest cleanup"},
                    timeout=10,
                )

    def test_suspend_requires_reason(self, admin_headers):
        tenant = _find_target_tenant(admin_headers)
        r = requests.post(
            f"{BASE_URL}/platform/tenants/{tenant['id']}/suspend",
            headers=admin_headers,
            json={},
            timeout=10,
        )
        assert r.status_code == 422  # Pydantic validation


# ============================================================================
# Support sessions + impersonation
# ============================================================================

class TestSupportSessions:
    def test_create_returns_impersonation_token(self, support_session):
        assert "session" in support_session
        assert "access_token" in support_session
        assert support_session["token_type"] == "bearer"
        assert support_session["expires_in"] > 0
        assert support_session["impersonated_user"]["id"] == TARGET_USER_ID
        assert support_session["session"]["ended_at"] is None

    def test_impersonation_works_on_tenant_routes(self, support_session):
        headers = {"Authorization": f"Bearer {support_session['access_token']}"}
        r = requests.get(f"{BASE_URL}/plots", headers=headers, timeout=10)
        assert r.status_code == 200

    def test_impersonation_does_not_grant_platform_access(self, support_session):
        """Security guarantee: impersonation cannot escalate to platform plane."""
        headers = {"Authorization": f"Bearer {support_session['access_token']}"}
        r = requests.get(f"{BASE_URL}/platform/stats", headers=headers, timeout=10)
        assert r.status_code == 403
        assert "Platform user role required" in r.text

    def test_ended_session_revokes_token(self, admin_headers, support_session):
        headers = {"Authorization": f"Bearer {support_session['access_token']}"}
        session_id = support_session["session"]["id"]

        # Token works before end
        assert requests.get(f"{BASE_URL}/plots", headers=headers, timeout=10).status_code == 200

        # End session
        r = requests.post(
            f"{BASE_URL}/platform/support-sessions/{session_id}/end",
            headers=admin_headers,
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["ended_at"] is not None

        # Token now rejected
        r = requests.get(f"{BASE_URL}/plots", headers=headers, timeout=10)
        assert r.status_code == 403
        assert "ended" in r.text.lower()

        # Idempotent end
        r = requests.post(
            f"{BASE_URL}/platform/support-sessions/{session_id}/end",
            headers=admin_headers,
            timeout=10,
        )
        assert r.status_code == 200

    def test_cannot_impersonate_platform_user(self, admin_headers):
        r = requests.get(f"{BASE_URL}/auth/me", headers=admin_headers, timeout=10)
        admin_id = r.json()["id"]

        r = requests.post(
            f"{BASE_URL}/platform/support-sessions",
            headers=admin_headers,
            json={"target_user_id": admin_id, "reason": "pytest"},
            timeout=10,
        )
        assert r.status_code == 400
        assert "platform user" in r.text.lower()

    def test_cannot_impersonate_missing_user(self, admin_headers):
        fake = str(uuid.uuid4())
        r = requests.post(
            f"{BASE_URL}/platform/support-sessions",
            headers=admin_headers,
            json={"target_user_id": fake, "reason": "pytest"},
            timeout=10,
        )
        assert r.status_code == 404

    def test_list_sessions(self, admin_headers, support_session):
        r = requests.get(
            f"{BASE_URL}/platform/support-sessions",
            headers=admin_headers,
            timeout=10,
        )
        assert r.status_code == 200
        ids = [s["id"] for s in r.json()]
        assert support_session["session"]["id"] in ids

    def test_list_sessions_active_only(self, admin_headers, support_session):
        r = requests.get(
            f"{BASE_URL}/platform/support-sessions?active_only=true",
            headers=admin_headers,
            timeout=10,
        )
        assert r.status_code == 200
        for s in r.json():
            assert s["ended_at"] is None