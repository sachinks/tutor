from tutor_ai.security import token_matches


def test_exact_token_matches():
    assert token_matches("a" * 40, ["a" * 40])


def test_wrong_or_partial_tokens_do_not_match():
    assert not token_matches("a" * 39, ["a" * 40])
    assert not token_matches("", ["a" * 40])
    assert not token_matches("b" * 40, ["a" * 40])


def test_either_token_matches_during_rotation():
    assert token_matches("b" * 40, ["a" * 40, "b" * 40])
