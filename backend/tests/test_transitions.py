"""Status workflow: only valid moves, only by the right role, always recorded."""
import pytest


@pytest.fixture
def people(make_user):
    return {"client": make_user("client"), "other_client": make_user("client"),
            "operator": make_user("operator"), "admin": make_user("admin")}


def deliver(people, move, assign, make_episode, request):
    """Take a request from submitted to delivered."""
    assert move(people["operator"], request["id"], "in_progress").status_code == 200
    episodes = [make_episode() for _ in range(request["episodes_requested"])]
    assert assign(people["operator"], request["id"], *episodes).status_code == 201
    assert move(people["operator"], request["id"], "delivered").status_code == 200


def test_happy_path_and_history_records_who_and_when(api, login, people, new_request,
                                                      move, assign, make_episode):
    request = new_request(people["client"])
    assert request["status"] == "submitted"

    deliver(people, move, assign, make_episode, request)
    res = move(people["client"], request["id"], "accepted", comment="looks great")
    assert res.status_code == 200

    body = res.json()
    assert body["status"] == "accepted"
    steps = [(h["from_status"], h["to_status"], h["changed_by_name"]) for h in body["history"]]
    assert steps == [
        (None, "submitted", people["client"].name),
        ("submitted", "in_progress", people["operator"].name),
        ("in_progress", "delivered", people["operator"].name),
        ("delivered", "accepted", people["client"].name),
    ]
    assert all(h["changed_at"] for h in body["history"])
    assert body["history"][-1]["comment"] == "looks great"


def test_rejected_request_goes_back_to_rework(people, new_request, move, assign, make_episode):
    request = new_request(people["client"])
    deliver(people, move, assign, make_episode, request)

    assert move(people["client"], request["id"], "rejected").status_code == 200
    assert move(people["operator"], request["id"], "in_progress").status_code == 200
    assert move(people["operator"], request["id"], "delivered").status_code == 200
    assert move(people["client"], request["id"], "accepted").json()["status"] == "accepted"


@pytest.mark.parametrize("target", ["delivered", "accepted", "rejected", "submitted", "nonsense"])
def test_invalid_moves_from_submitted_are_refused(people, new_request, move, target):
    request = new_request(people["client"])
    assert move(people["admin"], request["id"], target).status_code == 409


def test_accepted_is_final(people, new_request, move, assign, make_episode):
    request = new_request(people["client"])
    deliver(people, move, assign, make_episode, request)
    move(people["client"], request["id"], "accepted")
    for target in ["in_progress", "rejected", "delivered", "submitted"]:
        assert move(people["operator"], request["id"], target).status_code in (403, 409)
        assert move(people["client"], request["id"], target).status_code in (403, 409)


def test_client_cannot_do_any_operator_step(people, new_request, move, assign, make_episode):
    request = new_request(people["client"], count=1)
    # submitted -> in_progress
    assert move(people["client"], request["id"], "in_progress").status_code == 403

    # in_progress -> delivered, even with enough episodes assigned
    move(people["operator"], request["id"], "in_progress")
    assign(people["operator"], request["id"], make_episode())
    assert move(people["client"], request["id"], "delivered").status_code == 403

    # rejected -> in_progress
    move(people["operator"], request["id"], "delivered")
    move(people["client"], request["id"], "rejected")
    assert move(people["client"], request["id"], "in_progress").status_code == 403


@pytest.mark.parametrize("role", ["operator", "admin"])
def test_staff_cannot_accept_or_reject_for_the_client(people, new_request, move, assign,
                                                     make_episode, role):
    request = new_request(people["client"])
    deliver(people, move, assign, make_episode, request)
    assert move(people[role], request["id"], "accepted").status_code == 403
    assert move(people[role], request["id"], "rejected").status_code == 403


def test_another_client_cannot_accept(people, new_request, move, assign, make_episode):
    request = new_request(people["client"])
    deliver(people, move, assign, make_episode, request)
    assert move(people["other_client"], request["id"], "accepted").status_code == 404


def test_admin_can_do_operator_steps(people, new_request, move):
    request = new_request(people["client"])
    assert move(people["admin"], request["id"], "in_progress").status_code == 200


def test_cannot_deliver_before_enough_episodes_are_assigned(people, new_request, move,
                                                           assign, make_episode):
    request = new_request(people["client"], count=3)
    move(people["operator"], request["id"], "in_progress")
    assign(people["operator"], request["id"], make_episode(), make_episode())

    res = move(people["operator"], request["id"], "delivered")
    assert res.status_code == 409
    assert "2 of 3" in res.json()["detail"]

    assign(people["operator"], request["id"], make_episode())
    assert move(people["operator"], request["id"], "delivered").status_code == 200


def test_refused_moves_leave_no_history(api, login, people, new_request, move):
    request = new_request(people["client"])
    move(people["client"], request["id"], "in_progress")
    move(people["operator"], request["id"], "accepted")
    detail = api.get(f"/requests/{request['id']}", headers=login(people["operator"])).json()
    assert detail["status"] == "submitted"
    assert len(detail["history"]) == 1


def test_request_validation(api, login, people):
    headers = login(people["client"])
    bad_bodies = [
        {"task_name": "", "episodes_requested": 1, "deadline": "2030-01-01"},
        {"task_name": "x", "episodes_requested": 0, "deadline": "2030-01-01"},
        {"task_name": "x", "episodes_requested": 1, "deadline": "2020-01-01"},
        {"task_name": "x", "episodes_requested": 1, "deadline": "not a date"},
    ]
    for body in bad_bodies:
        assert api.post("/requests", headers=headers, json=body).status_code == 422, body
