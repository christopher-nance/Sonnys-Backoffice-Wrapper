import re
import string

from sonnys_backoffice.passwords import generate_bo_password, generate_pos_pin


def test_pos_pin_is_int_in_five_digit_range():
    for _ in range(100):
        pin = generate_pos_pin()
        assert isinstance(pin, int)
        assert 10000 <= pin <= 99999


def test_bo_password_length_is_twelve():
    for _ in range(100):
        pw = generate_bo_password()
        assert len(pw) == 12


def test_bo_password_has_alphanumeric_and_symbol():
    pw = generate_bo_password()
    has_alpha = any(c.isalpha() for c in pw)
    has_digit = any(c.isdigit() for c in pw)
    has_symbol = any(c in string.punctuation for c in pw)
    assert has_alpha and has_digit and has_symbol


def test_bo_password_matches_expected_character_set():
    pw = generate_bo_password()
    assert re.fullmatch(r"[A-Za-z0-9!@#$%^&*()_+=\-\[\]{};:,.<>?]+", pw)


def test_pos_pin_is_randomized():
    pins = {generate_pos_pin() for _ in range(50)}
    assert len(pins) > 1


def test_bo_password_is_randomized():
    pws = {generate_bo_password() for _ in range(50)}
    assert len(pws) > 1
