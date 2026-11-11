import pytest

from core import vault_manager as vm
from security.recovery import (
    InvalidRecoveryKeyFormat, generate_recovery_key, parse_recovery_key,
)
from tests.conftest import PASSWORD, tree_snapshot
from utils.error_handler import WrongPasswordError, WrongRecoveryKeyError


def test_keys_are_unique_and_well_formed():
    keys = {generate_recovery_key() for _ in range(200)}
    assert len(keys) == 200
    k = next(iter(keys))
    assert len(k.split("-")) == 14 and all(len(g) == 4 for g in k.split("-"))


def test_parse_roundtrip_and_forgiving_input():
    k = generate_recovery_key()
    secret = parse_recovery_key(k)
    assert len(secret) == 32
    assert parse_recovery_key(k.lower().replace("-", " ")) == secret
    assert parse_recovery_key("  " + k + "\n") == secret


def test_typo_detected_by_checksum():
    k = generate_recovery_key()
    bad = ("B" if k[0] != "B" else "C") + k[1:]
    with pytest.raises(InvalidRecoveryKeyFormat):
        parse_recovery_key(bad)


def test_incomplete_key_rejected():
    with pytest.raises(InvalidRecoveryKeyFormat):
        parse_recovery_key(generate_recovery_key()[:30])


def make_vault(tmp_path, sample_folder, fast_kdf, recovery_key):
    vault = tmp_path / "v.flock"
    vm.create_vault(sample_folder, vault, PASSWORD, recovery_key, kdf=fast_kdf)
    return vault


def test_recovery_key_unlocks_independently_of_password(tmp_path, sample_folder, fast_kdf, recovery_key):
    vault = make_vault(tmp_path, sample_folder, fast_kdf, recovery_key)
    keys = vm.unlock_with_recovery_key(vault, recovery_key)
    out = tmp_path / "out"
    out.mkdir()
    restored = vm.extract_vault(vault, keys, out)
    assert tree_snapshot(restored) == tree_snapshot(sample_folder)


def test_wrong_recovery_key_rejected(tmp_path, sample_folder, fast_kdf, recovery_key):
    vault = make_vault(tmp_path, sample_folder, fast_kdf, recovery_key)
    with pytest.raises(WrongRecoveryKeyError):
        vm.unlock_with_recovery_key(vault, generate_recovery_key())


def test_recovery_key_is_not_stored_in_vault(tmp_path, sample_folder, fast_kdf, recovery_key):
    vault = make_vault(tmp_path, sample_folder, fast_kdf, recovery_key)
    blob = vault.read_bytes()
    secret = parse_recovery_key(recovery_key)
    assert secret not in blob
    assert recovery_key.replace("-", "").encode() not in blob
    assert PASSWORD.encode() not in blob


def test_reset_password_with_recovery_key(tmp_path, sample_folder, fast_kdf, recovery_key):
    vault = make_vault(tmp_path, sample_folder, fast_kdf, recovery_key)
    vm.reset_password_with_recovery_key(vault, recovery_key, "A brand new Password 42!", kdf=fast_kdf)
    with pytest.raises(WrongPasswordError):
        vm.unlock_with_password(vault, PASSWORD)
    vm.unlock_with_password(vault, "A brand new Password 42!")
    vm.unlock_with_recovery_key(vault, recovery_key)       # recovery key still valid


def test_replace_recovery_key_invalidates_old(tmp_path, sample_folder, fast_kdf, recovery_key):
    vault = make_vault(tmp_path, sample_folder, fast_kdf, recovery_key)
    new_key = generate_recovery_key()
    vm.replace_recovery_key(vault, PASSWORD, new_key)
    with pytest.raises(WrongRecoveryKeyError):
        vm.unlock_with_recovery_key(vault, recovery_key)
    vm.unlock_with_recovery_key(vault, new_key)
    vm.unlock_with_password(vault, PASSWORD)
