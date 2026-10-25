from html.parser import HTMLParser

import pytest

from tests.test_app import app_module


FORM_FIELDS = {
    "item_category",
    "description",
    "organization_type",
    "organization_name",
    "campus_or_branch",
    "building_or_terminal",
    "floor_or_level",
    "specific_area",
    "date",
    "approx_time",
}


class FormsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self._current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self._current = {"action": attrs.get("action"), "names": set()}
            self.forms.append(self._current)
        elif tag in {"input", "select", "textarea"} and self._current:
            if attrs.get("name"):
                self._current["names"].add(attrs["name"])

    def handle_endtag(self, tag):
        if tag == "form":
            self._current = None


@pytest.fixture()
def client():
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def _form_for(response, action):
    parser = FormsParser()
    parser.feed(response.get_data(as_text=True))
    return next(form for form in parser.forms if form["action"] == action)


def test_homepage_renders_search_form_with_existing_route_contract(client):
    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Lost, then" in html
    assert "POSSIBLE FOUND REPORT" in html
    assert 'id="theme-toggle"' in html
    assert FORM_FIELDS <= _form_for(response, "/search")["names"]


def test_found_form_preserves_existing_route_and_fields(client):
    response = client.get("/found")

    assert response.status_code == 200
    assert FORM_FIELDS <= _form_for(response, "/found")["names"]


def test_found_form_submission_still_uses_existing_confirmation_route(
        client, monkeypatch, tmp_path):
    dataset_file = tmp_path / "findback_reports.csv"
    monkeypatch.setattr(app_module, "DATASET_FILE", str(dataset_file))
    monkeypatch.setattr(app_module, "DATASET_DIR", str(tmp_path))

    response = client.post("/found", data={
        "item_category": "Wallet",
        "description": "black leather wallet",
        "organization_type": "Mall",
        "organization_name": "City Center Mall",
        "campus_or_branch": "Main Branch",
        "building_or_terminal": "Main Building",
        "floor_or_level": "Ground Floor",
        "specific_area": "Food Court",
        "date": "2026-08-18",
        "approx_time": "13:35",
    })

    assert response.status_code == 200
    assert b"REPORT RECEIVED" in response.data
    assert b"FB001" in response.data


def test_search_post_still_renders_existing_results_route(client):
    response = client.post("/search", data={
        "item_category": "Backpack",
        "description": "navy bag with stitched patch",
        "organization_type": "University",
        "organization_name": "Greenfield University",
        "campus_or_branch": "Main Campus",
        "building_or_terminal": "Central Library",
        "floor_or_level": "2nd Floor",
        "specific_area": "Reading Room",
        "date": "2026-08-18",
        "approx_time": "16:20",
    })

    assert response.status_code == 200
    assert b"Potential found reports" in response.data
    assert b"FB002" in response.data


@pytest.mark.parametrize(
    ("path", "action"),
    [("/login", "/login"), ("/register", "/register")],
)
def test_account_routes_keep_existing_forms(client, path, action):
    response = client.get(path)

    assert response.status_code == 200
    fields = _form_for(response, action)["names"]
    assert {"email", "password"} <= fields


def test_protected_claim_route_remains_registered(client):
    response = client.get("/claims")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
