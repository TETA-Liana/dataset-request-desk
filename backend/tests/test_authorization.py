"""Authorization is enforced on the server, not just hidden in the UI."""
import pytest


@pytest.mark.parametrize("method,path", [
    ("get", "/auth/me"),
    ("get", "/requests"),
    ("post", "/requests"),
    ("get", "/requests/1"),
    ("get", "/episodes"),
    ("post", "/episodes/import"),
    ("get", "/analytics?start=2026-01-01&end=2026-01-02"),
    ("get", "/users"),
])
def test_every_endpoint_needs_login(api, method, path):
    assert getattr(api, method)(path).status_code == 401


def test_health_and_login_are_public(api):
    assert api.get("/health").status_code == 200
    assert api.post("/auth/login", json={"email": "x@test.com", "password": "x"}).status_code == 401


def test_garbage_token_is_rejected(api):
    assert api.get("/auth/me", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_wrong_password_and_inactive_user_get_the_same_error(api, make_user):
    active = make_user("client")
    inactive = make_user("client", is_active=False)
    wrong = api.post("/auth/login", json={"email": active.email, "password": "nope"})
    blocked = api.post("/auth/login", json={"email": inactive.email, "password": "password123"})
    assert wrong.status_code == blocked.status_code == 401
    assert wrong.json() == blocked.json()


def test_deactivating_a_user_kills_their_existing_token(api, make_user, login):
    admin, client = make_user("admin"), make_user("client")
    headers = login(client)
    assert api.get("/auth/me", headers=headers).status_code == 200

    api.patch(f"/users/{client.id}", headers=login(admin), json={"is_active": False})
    assert api.get("/auth/me", headers=headers).status_code == 401


def test_role_change_takes_effect_immediately(api, make_user, login):
    admin, operator = make_user("admin"), make_user("operator")
    headers = login(operator)
    assert api.get("/episodes", headers=headers).status_code == 200

    api.patch(f"/users/{operator.id}", headers=login(admin), json={"role": "client"})
    assert api.get("/episodes", headers=headers).status_code == 403


@pytest.mark.parametrize("method,path", [
    ("get", "/episodes"),
    ("post", "/episodes/import"),
    ("get", "/analytics?start=2026-01-01&end=2026-01-02"),
    ("get", "/users"),
    ("post", "/requests/1/assignments"),
])
def test_client_cannot_use_staff_endpoints(api, make_user, login, method, path):
    assert getattr(api, method)(path, headers=login(make_user("client"))).status_code == 403


def test_operator_cannot_manage_users(api, make_user, login):
    headers = login(make_user("operator"))
    assert api.get("/users", headers=headers).status_code == 403
    assert api.post("/users", headers=headers, json={
        "email": "new@test.com", "name": "N", "password": "longpassword", "role": "admin",
    }).status_code == 403


def test_only_clients_create_requests(api, make_user, login):
    body = {"task_name": "pick cup", "episodes_requested": 1, "deadline": "2030-01-01"}
    assert api.post("/requests", headers=login(make_user("operator")), json=body).status_code == 403


def test_client_only_sees_own_requests(api, make_user, login, new_request):
    alice, bob = make_user("client"), make_user("client")
    mine = new_request(alice)
    theirs = new_request(bob)

    listed = api.get("/requests", headers=login(alice)).json()
    assert [r["id"] for r in listed] == [mine["id"]]
    # 404 instead of 403: Alice should not even learn that Bob's request exists
    assert api.get(f"/requests/{theirs['id']}", headers=login(alice)).status_code == 404
    assert api.get(f"/requests/{theirs['id']}/assignments", headers=login(alice)).status_code == 404


def test_operator_sees_all_requests(api, make_user, login, new_request):
    new_request(make_user("client"))
    new_request(make_user("client"))
    assert len(api.get("/requests", headers=login(make_user("operator"))).json()) == 2


def test_admin_manages_users_but_cannot_lock_themselves_out(api, make_user, login):
    admin = make_user("admin")
    headers = login(admin)
    res = api.post("/users", headers=headers, json={
        "email": "New@Test.com", "name": "New", "password": "longpassword", "role": "operator"})
    assert res.status_code == 201
    assert res.json()["email"] == "new@test.com"
    assert "password" not in str(res.json())

    assert api.patch(f"/users/{admin.id}", headers=headers, json={"is_active": False}).status_code == 409
    assert api.patch(f"/users/{admin.id}", headers=headers, json={"role": "client"}).status_code == 409


def test_passwords_are_not_stored_in_plain_text(db, make_user):
    user = make_user("client")
    db.refresh(user)
    assert user.password_hash.startswith("$2")  # bcrypt
    assert "password123" not in user.password_hash
