"""UI contract checks for the existing Flask form and results routes."""

from html.parser import HTMLParser

import pytest

# Reuse the test module's lightweight matcher stub so importing the Flask
# app never initializes the semantic model or reaches an external service.
from tests.test_app import app_module


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
        elif tag in {"input", "textarea", "select"} and self._current:
            if attrs.get("name"):
                self._current["names"].add(attrs["name"])

    def handle_endtag(self, tag):
        if tag == "form":
            self._current = None


@pytest.fixture()
def client():
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def _forms(response):
    parser = FormsParser()
    parser.feed(response.get_data(as_text=True))
    return parser.forms


def test_home_search_form_preserves_route_and_field_contract(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"A way back" in response.data
    form = next(form for form in _forms(response) if form["action"] == "/search")
    assert {
        "item_category", "description", "organization_type",
        "organization_name", "campus_or_branch", "building_or_terminal",
        "floor_or_level", "specific_area", "date", "approx_time",
    } <= form["names"]


def test_found_form_preserves_route_and_field_contract(client):
    response = client.get("/found")
    assert response.status_code == 200
    form = next(form for form in _forms(response) if form["action"] == "/found")
    assert {
        "item_category", "description", "organization_type",
        "organization_name", "campus_or_branch", "building_or_terminal",
        "floor_or_level", "specific_area", "date", "approx_time",
    } <= form["names"]


def test_results_present_candidates_as_unconfirmed_leads(client):
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
    assert b"Weighted similarity is a guide" in response.data
    assert b"FB002" in response.data
