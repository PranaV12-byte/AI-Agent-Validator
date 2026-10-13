"""Regression coverage for tenant-scoped ERROR audit filters and exports."""

from __future__ import annotations

import csv
import io
from uuid import UUID

from fastapi.testclient import TestClient


def _headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}


def _tenant_id(client: TestClient, auth: dict) -> UUID:
    response = client.get("/api/v1/auth/me", headers=_headers(auth))
    assert response.status_code == 200
    return UUID(response.json()["id"])


def test_error_action_lists_and_exports_with_tenant_isolation(
    client: TestClient, make_tenant, seed_audit_logs
) -> None:
    tenant_a = make_tenant()
    tenant_b = make_tenant()
    tenant_a_id = _tenant_id(client, tenant_a)
    tenant_b_id = _tenant_id(client, tenant_b)

    seed_audit_logs(tenant_a_id, n=2, action="ERROR")
    seed_audit_logs(tenant_a_id, n=1, action="ALLOWED")
    seed_audit_logs(tenant_b_id, n=1, action="ERROR")

    list_a = client.get(
        "/api/v1/audit/?action=ERROR&limit=20", headers=_headers(tenant_a)
    )
    list_b = client.get(
        "/api/v1/audit/?action=ERROR&limit=20", headers=_headers(tenant_b)
    )

    assert list_a.status_code == 200
    assert list_b.status_code == 200
    logs_a = list_a.json()["logs"]
    logs_b = list_b.json()["logs"]
    assert list_a.json()["total"] == 2
    assert list_b.json()["total"] == 1
    assert all(log["action"] == "ERROR" for log in logs_a + logs_b)
    ids_a = {log["id"] for log in logs_a}
    ids_b = {log["id"] for log in logs_b}
    assert len(ids_a) == 2
    assert len(ids_b) == 1
    assert ids_a.isdisjoint(ids_b)

    export_a = client.get("/api/v1/audit/export?action=ERROR", headers=_headers(tenant_a))
    assert export_a.status_code == 200
    exported_a = list(csv.DictReader(io.StringIO(export_a.text)))
    assert len(exported_a) == 2
    assert {row["id"] for row in exported_a} == ids_a
    assert all(row["action"] == "ERROR" for row in exported_a)
    assert not (ids_b & {row["id"] for row in exported_a})
