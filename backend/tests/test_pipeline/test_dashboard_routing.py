"""Smoke tests for /pipeline + /pipeline/configure routing.

When no on-disk pipeline state exists, GET /pipeline renders the
configure form inline (saves a click). When state exists, it renders
the dashboard. /pipeline/configure stays as a deep link to the form.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from mtgai.review.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_pipeline_renders_configure_when_no_state(client):
    with patch("mtgai.pipeline.server._get_current_state", return_value=None):
        resp = client.get("/pipeline")
    assert resp.status_code == 200
    body = resp.text
    # The dropdown picker replaces the per-form set-code input now;
    # the configure form keeps a read-only display element instead.
    assert 'id="active-set-display"' in body
    assert "Configure Pipeline" in body
    # The dashboard's pipeline-app shell shouldn't appear when we're
    # rendering the configure form instead.
    assert 'id="pipeline-app"' not in body


def test_pipeline_renders_dashboard_when_state_exists(client):
    """A non-None pipeline state takes the dashboard branch.

    The banner middleware also looks up the same state, so we use a
    real ``create_pipeline_state`` minimal value rather than a fake —
    the banner reads ``overall_status`` + ``current_stage()`` which a
    blank fake doesn't satisfy.
    """
    from mtgai.pipeline.models import PipelineConfig, create_pipeline_state

    state = create_pipeline_state(PipelineConfig(set_code="TST", set_name="Test", set_size=20))

    with patch("mtgai.pipeline.server._get_current_state", return_value=state):
        resp = client.get("/pipeline")
    assert resp.status_code == 200
    body = resp.text
    assert 'id="pipeline-app"' in body
    assert "/static/pipeline.js" in body


def test_pipeline_configure_renders_form_even_with_active_state(client):
    """`/pipeline/configure` ignores pipeline state — the form is the form."""
    from mtgai.pipeline.models import PipelineConfig, create_pipeline_state

    state = create_pipeline_state(PipelineConfig(set_code="TST", set_name="Test", set_size=20))

    with patch("mtgai.pipeline.server._get_current_state", return_value=state):
        resp = client.get("/pipeline/configure")
    assert resp.status_code == 200
    body = resp.text
    # The dropdown picker replaces the per-form set-code input now;
    # the configure form keeps a read-only display element instead.
    assert 'id="active-set-display"' in body
    assert "Configure Pipeline" in body
    assert 'id="pipeline-app"' not in body
