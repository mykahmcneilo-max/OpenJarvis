import json

import pytest

from openjarvis.tools.shared_tool_catalog import SharedToolCatalog


def test_search_distinguishes_installed_from_inspiration_and_bounds_results(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "name": "Watch",
                        "status": "skill-installed",
                        "purpose": "video evidence",
                    },
                    {"name": "Rose", "status": "inspiration", "purpose": "video demo"},
                ]
            }
        ),
        encoding="utf-8",
    )
    tool = SharedToolCatalog(path)
    out = json.loads(tool.execute(query="video", limit=1).content)
    assert out["matched"] == 2 and len(out["tools"]) == 1
    rose = json.loads(tool.execute(query="rose").content)["tools"][0]
    assert rose["status"] == "inspiration"
    assert json.loads(tool.execute(query="missing").content)["matched"] == 0


@pytest.mark.parametrize("params", [{"query": []}, {"limit": "all"}, {"limit": True}])
def test_bad_arguments_fail_without_running_anything(tmp_path, params):
    assert not SharedToolCatalog(tmp_path / "missing").execute(**params).success


def test_missing_catalog_is_a_plain_failure(tmp_path):
    assert not SharedToolCatalog(tmp_path / "missing").execute().success
