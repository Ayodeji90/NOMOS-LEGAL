"""Unit tests for the RRF fusion helper (pure logic, no DB)."""

import pytest

from app.services.retrieval.rrf import DEFAULT_RRF_K, fuse_ranked_lists, rrf_score


class TestRrfScore:
    def test_single_rank_default_k(self):
        # 1 / (60 + 1)
        assert rrf_score([1]) == pytest.approx(1 / 61)

    def test_multi_rank_sums(self):
        # ranks in three lists: 1, 3, 7
        expected = 1 / 61 + 1 / 63 + 1 / 67
        assert rrf_score([1, 3, 7]) == pytest.approx(expected)

    def test_custom_k(self):
        assert rrf_score([1], k=1) == pytest.approx(1 / 2)

    def test_weights_align_with_ranks(self):
        # weight 2 on rank 1, weight 0.5 on rank 3
        expected = 2 / 61 + 0.5 / 63
        assert rrf_score([1, 3], weights=[2.0, 0.5]) == pytest.approx(expected)

    def test_empty_ranks_is_zero(self):
        assert rrf_score([]) == 0.0

    def test_rejects_k_below_one(self):
        with pytest.raises(ValueError, match="k must be >= 1"):
            rrf_score([1], k=0)

    def test_rejects_zero_based_rank(self):
        with pytest.raises(ValueError, match="1-based"):
            rrf_score([0])

    def test_rejects_misaligned_weights(self):
        with pytest.raises(ValueError, match="must match ranks"):
            rrf_score([1, 2], weights=[1.0])

    def test_accepts_generator_input(self):
        # regression: generators must be materialised exactly once
        assert rrf_score(r for r in [1, 2]) == pytest.approx(1 / 61 + 1 / 62)


class TestFuseRankedLists:
    def test_single_list_preserves_order(self):
        fused = fuse_ranked_lists([["a", "b", "c"]])
        assert [f.id for f in fused] == ["a", "b", "c"]
        assert fused[0].ranks == {0: 1}

    def test_intersection_floats_to_top(self):
        # "a" appears in both lists; "b"/"c" only in one each.
        fused = fuse_ranked_lists([["a", "b"], ["c", "a"]])
        assert fused[0].id == "a"
        assert fused[0].ranks == {0: 1, 1: 2}
        assert fused[0].score == pytest.approx(1 / 61 + 1 / 62)

    def test_disjoint_lists_interleave_by_rank(self):
        fused = fuse_ranked_lists([["a", "b"], ["c", "d"]])
        # All score 1/61 for rank-1 items ("a","c") then 1/62 ("b","d").
        assert [f.id for f in fused] == ["a", "c", "b", "d"]

    def test_ties_broken_deterministically(self):
        # y,w hit rank 1 (score 1/61); x,z hit rank 2 (score 1/62).
        # Ties -> best-rank asc first, then id asc: w,y then x,z.
        fused = fuse_ranked_lists([["y", "x"], ["w", "z"]])
        assert [f.id for f in fused] == ["w", "y", "x", "z"]

    def test_duplicate_id_in_one_list_counts_best_rank(self):
        fused = fuse_ranked_lists([["a", "b", "a"]])
        a = next(f for f in fused if f.id == "a")
        assert a.ranks == {0: 1}
        assert a.score == pytest.approx(1 / 61)

    def test_empty_list_is_ignored(self):
        fused = fuse_ranked_lists([[], ["a", "b"]])
        assert [f.id for f in fused] == ["a", "b"]

    def test_all_empty(self):
        assert fuse_ranked_lists([[], []]) == []

    def test_no_lists(self):
        assert fuse_ranked_lists([]) == []

    def test_limit(self):
        fused = fuse_ranked_lists([["a", "b", "c"], ["d", "e", "f"]], limit=3)
        assert len(fused) == 3

    def test_weight_zero_list_contributes_nothing(self):
        with_w = fuse_ranked_lists([["a"], ["b"]], weights=[1.0, 0.0])
        assert [f.id for f in with_w] == ["a"]
        assert with_w[0].ranks == {0: 1}

    def test_weight_boost_changes_order(self):
        # Equal ranks in disjoint lists -> exact tie, broken by id asc.
        neutral = fuse_ranked_lists([["a"], ["b"]])
        assert [f.id for f in neutral] == ["a", "b"]

        # Doubling list 1's weight lifts b's identical rank past a.
        boosted = fuse_ranked_lists([["a"], ["b"]], weights=[1.0, 2.0])
        assert [f.id for f in boosted] == ["b", "a"]

    def test_absent_list_never_receives_its_weight(self):
        # "a" in list 0 only; weight of list 1 must not apply to it.
        fused = fuse_ranked_lists([["a"], ["b"]], weights=[2.0, 5.0])
        a = next(f for f in fused if f.id == "a")
        assert a.score == pytest.approx(2 / 61)

    def test_weights_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="match"):
            fuse_ranked_lists([["a"]], weights=[1.0, 1.0])

    def test_negative_weight_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            fuse_ranked_lists([["a"]], weights=[-1.0])

    def test_k_propagates(self):
        fused = fuse_ranked_lists([["a"]], k=1)
        assert fused[0].score == pytest.approx(1 / 2)

    def test_default_k_is_settings_value(self):
        assert DEFAULT_RRF_K == 60

    def test_determinism_across_calls(self):
        lists = [["a", "b", "c"], ["c", "a"], ["b", "x", "a"]]
        first = [f.id for f in fuse_ranked_lists(lists)]
        for _ in range(5):
            assert [f.id for f in fuse_ranked_lists(lists)] == first

    def test_ranks_provenance(self):
        fused = fuse_ranked_lists([["a", "b"], ["c", "a"]])
        a = next(f for f in fused if f.id == "a")
        assert a.ranks == {0: 1, 1: 2}
