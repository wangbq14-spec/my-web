"""Payment-info endpoint contract. DSH runs these tests."""

import pytest

from app.core.security import create_access_token
from app.models.user import User


@pytest.fixture()
def actors(db):
    users = [User(username=name, email=f"{name}@example.com", hashed_password="unused",
                  role=role) for name, role in [("admin", "admin"), ("alice", "user")]]
    db.add_all(users)
    db.commit()
    return [(u.id, {"Authorization": f"Bearer {create_access_token(subject=str(u.id))}"}) for u in users]


def test_payment_info_requires_auth(client):
    assert client.get("/api/me/payment-info").status_code == 401


def test_payment_info_returns_qr_and_sorted_packages(client, actors):
    response = client.get("/api/me/payment-info", headers=actors[1][1])
    assert response.status_code == 200
    payload = response.json()
    assert payload["qr_image_url"] is None

    packages = payload["packages"]
    assert isinstance(packages, list)
    assert all(set(pkg) == {"code", "credits", "amount_display"} for pkg in packages)
    assert all(isinstance(pkg["credits"], int) and isinstance(pkg["amount_display"], str)
               for pkg in packages)

    experience = next(pkg for pkg in packages if pkg["code"] == "experience")
    assert experience["credits"] == 1000
    assert experience["amount_display"] == "10 CNY"

    credits = [pkg["credits"] for pkg in packages]
    assert credits == sorted(credits)
