import json

import pytest
import responses

from app.redirects import RedirectError, Redirects

BASE = "https://api.cloudflare.com/client/v4/accounts/acc"
ITEMS = f"{BASE}/rules/lists/lst/items"
OPS = f"{BASE}/rules/lists/bulk_operations"


def _client():
    return Redirects("acc", "lst", "tok", "audio.paulinemahon.com", poll_interval=0)


def _item(item_id, source, target):
    return {
        "id": item_id,
        "redirect": {
            "source_url": f"audio.paulinemahon.com/{source}",
            "target_url": f"https://audio.paulinemahon.com/{target}",
            "status_code": 302,
        },
    }


def _list(*items):
    responses.get(
        ITEMS, json={"success": True, "result": list(items), "result_info": {"cursors": {}}}
    )


def _op(op_id, status="completed"):
    responses.get(
        f"{OPS}/{op_id}", json={"success": True, "result": {"id": op_id, "status": status}}
    )


@responses.activate
def test_point_adds_a_302_when_missing():
    _list()
    responses.post(ITEMS, json={"success": True, "result": {"operation_id": "op1"}})
    _op("op1")
    _client().point("k7mq3xpw", "the-kesh")
    sent = json.loads(responses.calls[1].request.body)
    assert sent == [
        {
            "redirect": {
                "source_url": "audio.paulinemahon.com/k7mq3xpw",
                "target_url": "https://audio.paulinemahon.com/the-kesh",
                "status_code": 302,
                "preserve_query_string": False,
                "subpath_matching": False,
                "include_subdomains": False,
                "preserve_path_suffix": False,
            }
        }
    ]
    assert responses.calls[0].request.headers["Authorization"] == "Bearer tok"


@responses.activate
def test_point_is_a_no_op_when_already_correct():
    _list(_item("i1", "k7mq3xpw", "the-kesh"))
    _client().point("k7mq3xpw", "the-kesh")
    assert len(responses.calls) == 1


@responses.activate
def test_point_repoints_by_delete_then_add_never_put():
    _list(_item("i1", "k7mq3xpw", "the-kesh"))
    responses.delete(ITEMS, json={"success": True, "result": {"operation_id": "op1"}})
    _op("op1")
    responses.post(ITEMS, json={"success": True, "result": {"operation_id": "op2"}})
    _op("op2")
    _client().point("k7mq3xpw", "the-kesh-jig")
    methods = [c.request.method for c in responses.calls]
    assert methods == ["GET", "DELETE", "GET", "POST", "GET"]
    assert json.loads(responses.calls[1].request.body) == {"items": [{"id": "i1"}]}
    assert "PUT" not in methods


@responses.activate
def test_items_follows_pagination():
    responses.get(
        ITEMS,
        json={
            "success": True,
            "result": [_item("i1", "a", "x")],
            "result_info": {"cursors": {"after": "c2"}},
        },
        match=[responses.matchers.query_param_matcher({})],
    )
    responses.get(
        ITEMS,
        json={"success": True, "result": [_item("i2", "b", "y")], "result_info": {"cursors": {}}},
        match=[responses.matchers.query_param_matcher({"cursor": "c2"})],
    )
    assert _client().items() == {"a": ("i1", "x"), "b": ("i2", "y")}


@responses.activate
def test_failed_operation_raises():
    _list()
    responses.post(ITEMS, json={"success": True, "result": {"operation_id": "op1"}})
    responses.get(
        f"{OPS}/op1",
        json={"success": True, "result": {"id": "op1", "status": "failed", "error": "bad url"}},
    )
    with pytest.raises(RedirectError, match="bad url"):
        _client().point("k7mq3xpw", "the-kesh")


@responses.activate
def test_target_reads_where_a_source_points():
    _list(_item("i1", "k7mq3xpw", "the-kesh"))
    assert _client().target("k7mq3xpw") == "the-kesh"
    assert _client().target("nope") is None


@responses.activate
def test_remove_deletes_only_that_item():
    _list(_item("i1", "the-kesh", "the-kesh-jig"), _item("i2", "k7mq3xpw", "the-kesh-jig"))
    responses.delete(ITEMS, json={"success": True, "result": {"operation_id": "op1"}})
    _op("op1")
    _client().remove("the-kesh")
    assert json.loads(responses.calls[1].request.body) == {"items": [{"id": "i1"}]}
    assert "PUT" not in [c.request.method for c in responses.calls]


@responses.activate
def test_remove_is_a_no_op_when_missing():
    _list()
    _client().remove("the-kesh")
    assert len(responses.calls) == 1
