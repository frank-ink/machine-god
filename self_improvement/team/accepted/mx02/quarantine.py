def test_used_requires_min_overlap_distinct_words_len_ge_5(self):
        selected = ["item1"]
        answer = "hello world test"
        item_texts = {"item1": "hello world test"}
        result = attribute(selected, answer, item_texts, min_overlap=1)
        assert result["item1"] == "ignored"
