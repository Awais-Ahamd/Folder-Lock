from security.password_manager import check_password, validate_new_password


def test_empty_password():
    assert validate_new_password("", "") is not None


def test_mismatch():
    assert "match" in validate_new_password("Correct-Horse-9!", "Correct-Horse-8!")


def test_too_short_rejected():
    assert not check_password("Ab1!xyz").acceptable


def test_common_passwords_rejected():
    for pw in ("password123", "Password1234", "qwertyuiop", "1234567890"):
        assert not check_password(pw).acceptable, pw


def test_repetition_and_sequences_are_weak():
    assert not check_password("aaaaaaaaaaaa").acceptable
    assert not check_password("abcdefghijkl").acceptable


def test_good_passphrase_accepted():
    r = check_password("correct horse battery staple")
    assert r.acceptable and r.score >= 3


def test_strong_password_scores_high():
    assert check_password("T7#qLz!92vR@pXw4mK").score == 4


def test_score_increases_with_quality():
    scores = [check_password(p).score for p in ("aB3$", "Summer2020", "T7#qLz!92vR@pXw4mK")]
    assert scores == sorted(scores)


def test_valid_pair_accepted():
    assert validate_new_password("T7#qLz!92vR@pXw4mK", "T7#qLz!92vR@pXw4mK") is None


def test_unicode_passwords_ok():
    assert check_password("пароль-Ünïcode-🔒-пример").acceptable
