"""Tests for the data contract (M5.5): models, committed schemas and the published data."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from orbyt.core import contracts as c
from orbyt.core import publish

FINDING = {
    "id": "ph-eu-x-2024",
    "module": "pollution-hunter",
    "subject": {
        "id": "ph-eu-x",
        "kind": "facility",
        "name": "X",
        "display_name": None,
        "operator": None,
        "sector": "Energy sector",
        "country": "GR",
        "city": None,
        "lat": 35.0,
        "lon": 26.1,
        "register": "EEA",
        "register_id": "r1",
    },
    "period": {"label": "2024", "start": "2024-01-01", "end": "2024-12-31"},
    "claimed": None,
    "observed": None,
    "ratio": None,
    "verdict": None,
    "grade": None,
}


def test_a_minimal_finding_validates_and_round_trips_by_alias():
    f = c.Finding.model_validate(FINDING)
    assert f.subject.register_ == "EEA"
    out = f.model_dump(mode="json", by_alias=True, exclude_none=False)
    assert out["subject"]["register"] == "EEA"


def test_unknown_keys_are_refused():
    bad = {**FINDING, "extra": 1}
    with pytest.raises(ValidationError):
        c.Finding.model_validate(bad)


def test_enums_are_closed():
    for key, value in (("verdict", "maybe"), ("grade", "D")):
        with pytest.raises(ValidationError):
            c.Finding.model_validate({**FINDING, key: value})


def test_a_finding_that_misses_a_required_key_is_refused():
    bad = {k: v for k, v in FINDING.items() if k != "claimed"}
    with pytest.raises(ValidationError):
        c.Finding.model_validate(bad)


def test_committed_schemas_match_the_models(tmp_path):
    publish.export_schemas(tmp_path)
    for path in tmp_path.glob("*.schema.json"):
        committed = publish.SCHEMAS_DIR / path.name
        assert committed.exists(), f"{path.name} is not committed, run orbyt.core.publish --schemas"
        assert json.loads(committed.read_text(encoding="utf-8")) == json.loads(
            path.read_text(encoding="utf-8")
        ), f"{path.name} is out of date, run orbyt.core.publish --schemas"


def test_schema_has_no_property_titles_and_no_prefix_items():
    text = json.dumps(publish.schema_of(c.Contract, "contract"))
    assert "prefixItems" not in text
    schema = publish.schema_of(c.Subject, "subject")
    assert all("title" not in p for p in schema["properties"].values())
    assert "register" in schema["properties"]


def test_published_data_validates():
    module = publish.DATA_ROOT / "pollution-hunter"
    counts = publish.validate_module(module)
    assert counts["findings"] > 0


def test_validation_catches_a_missing_detail_file(tmp_path):
    module = tmp_path / "m"
    (module / "finding").mkdir(parents=True)
    payload = {
        "module": "pollution-hunter",
        "period": "2024",
        "source": "s",
        "count": 1,
        "latest_year_countries": {},
        "findings": [FINDING],
    }
    (module / "findings.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="missing detail"):
        publish.validate_module(module)


def test_validation_catches_a_wrong_count(tmp_path):
    module = tmp_path / "m"
    (module / "finding").mkdir(parents=True)
    payload = {
        "module": "pollution-hunter",
        "period": "2024",
        "source": "s",
        "count": 2,
        "latest_year_countries": {},
        "findings": [FINDING],
    }
    (module / "findings.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="count"):
        publish.validate_module(module)


def test_manifest_lists_the_module():
    m = publish.build_manifest("ph-emg-1.1", "2026-11", "abc1234")
    assert m.modules[0].id == "pollution-hunter"
    assert m.modules[0].base == "/data/v1/pollution-hunter"


def test_cluster_info_validates_and_is_optional():
    f = c.Finding.model_validate(
        {
            **FINDING,
            "cluster": {
                "n_facilities": 1,
                "neighbour": {"name": "N", "reported_t": 3.0, "distance_km": 40.0},
            },
        }
    )
    assert f.cluster.neighbour.name == "N"
    assert c.Finding.model_validate(FINDING).cluster is None
    with pytest.raises(ValidationError):
        c.Finding.model_validate({**FINDING, "cluster": {"n_facilities": 1, "extra": 1}})
