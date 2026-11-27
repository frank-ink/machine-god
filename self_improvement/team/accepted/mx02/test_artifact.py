import pytest
from artifact import SIGNALS, Feedback, parse_feedback, attribute, credit

class TestParseFeedback:

    def test_valid_feedback(self):
        d = {'compile_id': 'c1', 'item_id': 'i1', 'signal': 'cited', 'weight': 0.5, 'ts': 123.0}
        fb = parse_feedback(d)
        assert fb.compile_id == 'c1'
        assert fb.item_id == 'i1'
        assert fb.signal == 'cited'
        assert fb.weight == 0.5
        assert fb.ts == 123.0

    def test_missing_field_raises(self):
        d = {'compile_id': 'c1', 'item_id': 'i1', 'signal': 'cited', 'weight': 0.5}
        with pytest.raises(ValueError, match='missing field: ts'):
            parse_feedback(d)

    def test_empty_compile_id_raises(self):
        d = {'compile_id': '', 'item_id': 'i1', 'signal': 'cited', 'weight': 0.5, 'ts': 1.0}
        with pytest.raises(ValueError, match='empty compile_id'):
            parse_feedback(d)

    def test_empty_item_id_raises(self):
        d = {'compile_id': 'c1', 'item_id': '', 'signal': 'cited', 'weight': 0.5, 'ts': 1.0}
        with pytest.raises(ValueError, match='empty item_id'):
            parse_feedback(d)

    def test_invalid_signal_raises(self):
        d = {'compile_id': 'c1', 'item_id': 'i1', 'signal': 'invalid', 'weight': 0.5, 'ts': 1.0}
        with pytest.raises(ValueError, match='invalid signal'):
            parse_feedback(d)

    def test_weight_below_zero_raises(self):
        d = {'compile_id': 'c1', 'item_id': 'i1', 'signal': 'cited', 'weight': -0.1, 'ts': 1.0}
        with pytest.raises(ValueError, match='weight out of range'):
            parse_feedback(d)

    def test_weight_above_one_raises(self):
        d = {'compile_id': 'c1', 'item_id': 'i1', 'signal': 'cited', 'weight': 1.1, 'ts': 1.0}
        with pytest.raises(ValueError, match='weight out of range'):
            parse_feedback(d)

    def test_weight_boundary_zero_ok(self):
        d = {'compile_id': 'c1', 'item_id': 'i1', 'signal': 'cited', 'weight': 0.0, 'ts': 1.0}
        fb = parse_feedback(d)
        assert fb.weight == 0.0

    def test_weight_boundary_one_ok(self):
        d = {'compile_id': 'c1', 'item_id': 'i1', 'signal': 'cited', 'weight': 1.0, 'ts': 1.0}
        fb = parse_feedback(d)
        assert fb.weight == 1.0

class TestAttribute:

    def test_cited_when_item_id_in_answer(self):
        selected = ['item1', 'item2']
        answer = 'This references item1 explicitly'
        item_texts = {'item1': 'some text', 'item2': 'other text'}
        result = attribute(selected, answer, item_texts)
        assert result['item1'] == 'cited'
        assert result['item2'] == 'ignored'

    def test_cited_takes_precedence_over_used(self):
        selected = ['item1']
        answer = 'item1 appears here and also shares many words'
        item_texts = {'item1': 'appears here shares many words'}
        result = attribute(selected, answer, item_texts, min_overlap=2)
        assert result['item1'] == 'cited'

    def test_used_when_min_overlap_met(self):
        selected = ['item1']
        answer = 'The quick brown fox jumps over the lazy dog'
        item_texts = {'item1': 'quick brown fox jumps over'}
        result = attribute(selected, answer, item_texts, min_overlap=3)
        assert result['item1'] == 'used'

    def test_used_counts_distinct_words(self):
        selected = ['item1']
        answer = 'apple banana cherry apple banana'
        item_texts = {'item1': 'apple banana cherry'}
        result = attribute(selected, answer, item_texts, min_overlap=3)
        assert result['item1'] == 'used'

    def test_ignored_when_neither_cited_nor_used(self):
        selected = ['item1']
        answer = 'completely different text'
        item_texts = {'item1': 'unrelated content here'}
        result = attribute(selected, answer, item_texts, min_overlap=2)
        assert result['item1'] == 'ignored'

    def test_output_keys_match_selected_order(self):
        selected = ['third', 'first', 'second']
        answer = 'first and second mentioned'
        item_texts = {'first': 'first text', 'second': 'second text', 'third': 'third text'}
        result = attribute(selected, answer, item_texts)
        assert list(result.keys()) == ['third', 'first', 'second']

    def test_missing_item_text_only_cited_or_ignored(self):
        selected = ['missing1', 'missing2']
        answer = 'missing1 is cited here'
        item_texts = {}
        result = attribute(selected, answer, item_texts)
        assert result['missing1'] == 'cited'
        assert result['missing2'] == 'ignored'

    def test_missing_item_text_cannot_be_used(self):
        selected = ['missing']
        answer = 'many shared words appear here'
        item_texts = {}
        result = attribute(selected, answer, item_texts, min_overlap=1)
        assert result['missing'] == 'ignored'

    def test_case_insensitive_word_matching(self):
        selected = ['item1']
        answer = 'APPLE BANANA CHERRY'
        item_texts = {'item1': 'apple banana cherry'}
        result = attribute(selected, answer, item_texts, min_overlap=3)
        assert result['item1'] == 'used'

    def test_word_boundaries_respected(self):
        selected = ['item1']
        answer = 'apples are fruit'
        item_texts = {'item1': 'apple'}
        result = attribute(selected, answer, item_texts, min_overlap=1)
        assert result['item1'] == 'ignored'

    def test_min_overlap_default_is_three(self):
        selected = ['item1']
        answer = 'word1 word2 word3 word4'
        item_texts = {'item1': 'word1 word2 word3 word4'}
        result = attribute(selected, answer, item_texts)
        assert result['item1'] == 'used'

    def test_min_overlap_custom_value(self):
        selected = ['item1']
        answer = 'word1 word2'
        item_texts = {'item1': 'word1 word2'}
        result = attribute(selected, answer, item_texts, min_overlap=2)
        assert result['item1'] == 'used'

class TestCredit:

    def test_cited_is_1_0(self):
        signals = {'item1': 'cited'}
        result = credit(signals)
        assert result['item1'] == 1.0

    def test_used_is_0_5(self):
        signals = {'item1': 'used'}
        result = credit(signals)
        assert result['item1'] == 0.5

    def test_ignored_is_0_0(self):
        signals = {'item1': 'ignored'}
        result = credit(signals)
        assert result['item1'] == 0.0

    def test_corrected_is_neg_0_5(self):
        signals = {'item1': 'corrected'}
        result = credit(signals)
        assert result['item1'] == -0.5

    def test_harmful_is_neg_1_0(self):
        signals = {'item1': 'harmful'}
        result = credit(signals)
        assert result['item1'] == -1.0

    def test_unknown_signal_raises_value_error(self):
        signals = {'item1': 'unknown'}
        with pytest.raises(ValueError, match='unknown signal'):
            credit(signals)

    def test_multiple_items(self):
        signals = {'a': 'cited', 'b': 'used', 'c': 'ignored', 'd': 'corrected', 'e': 'harmful'}
        result = credit(signals)
        assert result['a'] == 1.0
        assert result['b'] == 0.5
        assert result['c'] == 0.0
        assert result['d'] == -0.5
        assert result['e'] == -1.0
