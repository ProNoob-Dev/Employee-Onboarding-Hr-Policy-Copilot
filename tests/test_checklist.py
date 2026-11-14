VALID_OWNERS = {"HR", "IT", "Manager", "Buddy", "Employee"}


def _checklist(client, employee_id="EMP-001", role="Software Engineer", location="Pune"):
    resp = client.post(f"/onboarding/{employee_id}/checklist",
                       json={"role": role, "location": location})
    assert resp.status_code == 200
    return resp.json()


def test_checklist_shape(client):
    body = _checklist(client)
    assert body["employee_id"] == "EMP-001"
    assert 5 <= len(body["checklist"]) <= 8
    for item in body["checklist"]:
        assert 1 <= item["day"] <= 5
        assert item["owner"] in VALID_OWNERS
        assert item["source"]["doc_id"].startswith("ONB")


def test_engineer_role_gets_dev_setup(client):
    body = _checklist(client, role="Software Engineer")
    assert any("development environment" in i["title"].lower() for i in body["checklist"])


def test_remote_location_gets_remote_setup(client):
    body = _checklist(client, location="Remote - India")
    assert any("remote workspace" in i["title"].lower() for i in body["checklist"])
    assert not any("office badge" in i["title"].lower() for i in body["checklist"])


def test_office_location_gets_badge(client):
    body = _checklist(client, location="Bengaluru")
    assert any("office badge" in i["title"].lower() for i in body["checklist"])


def test_manager_role_checked_before_engineer(client):
    # "Engineering Manager" contains "engineer" but must get the manager item.
    body = _checklist(client, role="Engineering Manager")
    assert any("meet your team" in i["title"].lower() for i in body["checklist"])
    assert not any("development environment" in i["title"].lower()
                   for i in body["checklist"])


def test_remote_joiner_is_not_told_to_collect_a_laptop(client):
    body = _checklist(client, role="Software Engineer", location="Remote - India")
    assert not any("collect laptop" in i["title"].lower() for i in body["checklist"])
    assert any("receive your laptop" in i["title"].lower() for i in body["checklist"])


def test_unknown_role_location_never_errors(client):
    body = _checklist(client, role="Quantum Gardener", location="Nowhere")
    assert 5 <= len(body["checklist"]) <= 8
