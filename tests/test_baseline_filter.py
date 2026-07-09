#!/usr/bin/env python3
"""Tests for test-contract filtering in the baseline runner (issue #12)."""

import sys
from pathlib import Path

import pytest

# Add the baseline-runner directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "baseline-runner"))

from baseline_runner import is_test_file


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        # Real audit targets are kept
        ("src/Vault.sol", False),
        ("src/Token.sol", False),
        ("contracts/Governance.sol", False),
        # Foundry test contracts: no "test" substring in the name (issue #12)
        ("test/Counter.t.sol", True),
        ("src/Counter.t.sol", True),
        # Contracts under a test directory
        ("test/Helper.sol", True),
        ("tests/Fixtures.sol", True),
        # Existing name-substring behaviour still holds
        ("src/MyTest.sol", True),
        ("src/TestUtils.sol", True),
        # Nested repo-relative paths behave the same at any depth
        ("packages/core/test/Fixtures.sol", True),
        ("packages/core/src/Vault.sol", False),
        # Foundry deploy scripts are out of scope (only test contracts are filtered)
        ("script/Deploy.s.sol", False),
    ],
)
def test_is_test_file(path, expected):
    assert is_test_file(Path(path)) is expected
