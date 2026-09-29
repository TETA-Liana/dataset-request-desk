"""Assignment rules: one request per episode, only good/usable, all-or-nothing."""
import pytest


@pytest.fixture
def setup(make_user, new_request, move):
    client, operator = make_user("client"), make_user("operator")
    first, second = new_request(client), new_request(client)
    move(operator, first["id"], "in_progress")
    move(operator, second["id"], "in_progress")
    return operator, first["id"], second["id"]


@pytest.mark.parametrize("quality", ["good", "usable"])
def test_good_and_usable_can_be_assigned(setup, assign, make_episode, quality):
    operator, req, _ = setup
    assert assign(operator, req, make_episode(quality=quality)).status_code == 201


def test_bad_episodes_cannot_be_assigned(setup, assign, make_episode):
    operator, req, _ = setup
    res = assign(operator, req, make_episode(quality="bad"))
    assert res.status_code == 409
    assert "quality is bad" in str(res.json())


def test_episode_can_only_be_on_one_request(setup, assign, make_episode):
    operator, first, second = setup
    episode = make_episode()
    assert assign(operator, first, episode).status_code == 201
    res = assign(operator, second, episode)
    assert res.status_code == 409
    assert f"already assigned to request {first}" in str(res.json())
    # assigning it to the same request twice is also refused
    assert assign(operator, first, episode).status_code == 409


def test_batch_is_all_or_nothing(api, login, setup, assign, make_episode):
    operator, req, _ = setup
    good, bad = make_episode(), make_episode(quality="bad")
    assert assign(operator, req, good, bad).status_code == 409

    assigned = api.get(f"/requests/{req}/assignments", headers=login(operator)).json()
    assert assigned == []


def test_unknown_episode_is_refused(setup, assign):
    operator, req, _ = setup
    assert assign(operator, req, "EP-99999").status_code == 409


def test_can_only_assign_while_in_progress(make_user, new_request, assign, make_episode):
    operator = make_user("operator")
    request = new_request(make_user("client"))  # still "submitted"
    assert assign(operator, request["id"], make_episode()).status_code == 409


def test_cannot_change_assignments_after_delivery(api, login, setup, assign, move, make_episode):
    operator, req, _ = setup
    a, b = make_episode(), make_episode()
    assign(operator, req, a, b)
    move(operator, req, "delivered")
    assert assign(operator, req, make_episode()).status_code == 409
    res = api.delete(f"/requests/{req}/assignments/{a.episode_id}", headers=login(operator))
    assert res.status_code == 409


def test_unassigned_episode_becomes_free_again(api, login, setup, assign, make_episode):
    operator, first, second = setup
    episode = make_episode()
    assign(operator, first, episode)
    res = api.delete(f"/requests/{first}/assignments/{episode.episode_id}", headers=login(operator))
    assert res.status_code == 204
    assert assign(operator, second, episode).status_code == 201


def test_unassigned_only_filter(api, login, setup, assign, make_episode):
    operator, req, _ = setup
    taken, free = make_episode(), make_episode()
    assign(operator, req, taken)
    res = api.get("/episodes?unassigned_only=true", headers=login(operator)).json()
    assert [e["episode_id"] for e in res["items"]] == [free.episode_id]


def test_database_itself_blocks_double_assignment(db, setup, make_episode, make_user):
    """Even if the API check is skipped (e.g. a race), the UNIQUE constraint holds."""
    from sqlalchemy.exc import IntegrityError
    from app.models import Assignment

    operator, first, second = setup
    episode = make_episode()
    db.add(Assignment(episode_id=episode.episode_id, request_id=first, assigned_by_id=operator.id))
    db.commit()
    db.add(Assignment(episode_id=episode.episode_id, request_id=second, assigned_by_id=operator.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_assignable_only_filter_hides_bad_episodes(api, login, setup, make_episode):
    operator, _, _ = setup
    make_episode(quality="good")
    make_episode(quality="usable")
    make_episode(quality="bad")
    res = api.get("/episodes?assignable_only=true", headers=login(operator)).json()
    assert res["total"] == 2
    assert {e["quality"] for e in res["items"]} == {"good", "usable"}
