def test_attribute_duplicate_selected_preserves_order_and_processes_each():
    selected = ["i1", "i1"]
    answer = "i1"
    item_texts = {"i1": "text"}
    out = attribute(selected, answer, item_texts)
    assert list(out.keys()) == ["i1", "i1"]
    assert out["i1"] == "cited"
