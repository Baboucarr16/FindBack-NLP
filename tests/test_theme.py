"""Theme accessibility and asset contract for the shared page shell."""

from tests.test_ui_templates import client


def test_theme_toggle_is_available_from_the_shared_shell(client):
    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="theme-toggle"' in html
    assert 'aria-pressed="false"' in html
    assert 'aria-label="Switch to dark theme"' in html
    assert 'name="color-scheme"' in html
    assert "theme.js" in html


def test_theme_script_supports_system_default_and_persisted_choice(client):
    response = client.get("/static/theme.js")
    script = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "prefers-color-scheme: dark" in script
    assert "localStorage" in script
    assert 'setAttribute("data-theme"' in script


def test_stylesheet_defines_dark_palette_and_themed_controls(client):
    response = client.get("/static/style.css")
    css = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '[data-theme="dark"]' in css
    assert "--workspace-bg" in css
    assert "--input-bg" in css
    assert "color-scheme: dark" in css
    assert "--display:" in css
    assert "--signal: #a65335" in css
    assert "--signal: #e59b7c" in css
    assert "@media (max-width: 700px)" in css


def test_shared_shell_keeps_theme_control_on_public_pages(client):
    for path in ("/", "/found", "/login", "/register"):
        response = client.get(path)
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        assert 'id="theme-toggle"' in html
        assert 'aria-label="Switch to dark theme"' in html


def test_stylesheet_has_visible_keyboard_focus_reduced_motion_and_small_viewports(client):
    css = client.get("/static/style.css").get_data(as_text=True)

    assert ":focus-visible" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "@media (max-width: 700px)" in css
    assert "@media (max-width: 390px)" in css


def test_full_bleed_decorations_do_not_extend_past_the_layout_viewport(client):
    css = client.get("/static/style.css").get_data(as_text=True)

    # Viewport-width pseudo-elements can be wider than the layout viewport
    # when classic scrollbars are present. Keep decoration within its section
    # instead of hiding page overflow globally.
    assert "width: 100vw;" not in css
    assert ".home-hero::before" in css
    assert ".how-section::before" in css


def test_search_form_has_a_live_progressive_loading_status(client):
    response = client.get("/")
    html = response.get_data(as_text=True)

    assert 'id="search-status"' in html
    assert 'data-submit-label' in html
    assert "Comparing reports" in client.get("/static/theme.js").get_data(as_text=True)


def test_search_validation_error_is_announced(client):
    response = client.post("/search", data={
        "item_category": "",
        "description": "a blue backpack",
        "organization_name": "Greenfield University",
        "date": "2026-08-18",
        "approx_time": "16:20",
    })

    assert response.status_code == 200
    assert b'role="alert"' in response.data
    assert b"select an item category" in response.data.lower()


def test_results_describe_the_four_scores_as_weighted_components(client):
    response = client.post("/search", data={
        "item_category": "Backpack",
        "description": "navy bag with stitched patch",
        "organization_name": "Greenfield University",
        "date": "2026-08-18",
        "approx_time": "16:20",
    })

    assert response.status_code == 200
    assert b"4 WEIGHTED COMPONENTS" in response.data
