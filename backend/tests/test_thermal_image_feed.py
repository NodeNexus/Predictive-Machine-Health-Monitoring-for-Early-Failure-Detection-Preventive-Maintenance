"""Tests for GET /api/demo/thermal-image-feed and
GET /api/demo/thermal-image-feed/{image_id} - the curated, cached Thermal
V1 dataset image feed used by the minimal dashboard presentation. Does not
require a running demo session (unlike /api/demo/thermal-video).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services import thermal_image_feed


def test_feed_returns_curated_real_images_with_all_six_classes():
    with TestClient(app) as client:
        resp = client.get("/api/demo/thermal-image-feed")
        assert resp.status_code == 200
        feed = resp.json()
        assert 10 <= len(feed) <= 20
        classes_seen = {entry["image_id"].split("_")[0] for entry in feed}
        assert classes_seen == {"HFL", "HML", "HNL", "CFL", "CML", "CNL"}


def test_feed_entries_have_gated_prediction_shape():
    with TestClient(app) as client:
        resp = client.get("/api/demo/thermal-image-feed")
        feed = resp.json()
        for entry in feed:
            assert "image_id" in entry
            assert "ml_prediction" in entry
            assert "ml_confidence" in entry
            assert "ml_condition" in entry
            assert "ml_load_context" in entry
            assert "ml_reliability" in entry
            assert entry["ml_reliability"] in ("high", "low", "unavailable")
            # never a definitive class when not accepted
            if entry["ml_reliability"] != "high":
                assert entry["ml_prediction"] is None


def test_feed_is_cached_across_requests():
    with TestClient(app) as client:
        first = client.get("/api/demo/thermal-image-feed").json()
        second = client.get("/api/demo/thermal-image-feed").json()
        assert first == second


def test_feed_image_endpoint_streams_real_jpeg():
    with TestClient(app) as client:
        feed = client.get("/api/demo/thermal-image-feed").json()
        image_id = feed[0]["image_id"]
        resp = client.get(f"/api/demo/thermal-image-feed/{image_id}")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"
        assert len(resp.content) > 1000  # a real JPEG, not an empty/stub file


def test_feed_image_endpoint_rejects_unknown_id():
    with TestClient(app) as client:
        client.get("/api/demo/thermal-image-feed")  # ensure the feed/id map is built
        resp = client.get("/api/demo/thermal-image-feed/not-a-real-id")
        assert resp.status_code == 404


def test_get_image_path_returns_none_for_unknown_id():
    thermal_image_feed.build_feed()
    assert thermal_image_feed.get_image_path("nonexistent") is None
