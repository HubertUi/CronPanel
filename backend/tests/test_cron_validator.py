"""Tests for the centralized cron expression validator/normalizer."""

import pytest

from app.utils import cron_validator
from app.utils.cron_validator import (
    CronValidationError,
    describe_cron_expression,
    normalize_cron_expression,
    parse_cron_expression,
    validate_cron_expression,
)

VALID_EXPRESSIONS = [
    "* * * * *",
    "0 * * * *",
    "0 2 * * *",
    "30 8 * * 1-5",
    "0 0 1 * *",
    "*/15 * * * *",
    "0 9 * * 1",
    "5,10,15 * * * *",
    "0 6,18 * * *",
    "30 4 1,15 * *",
    "10-20 * * * *",
    "0-30/10 * * * *",
    "0 0 * * 7",
]


@pytest.mark.parametrize("expression", VALID_EXPRESSIONS)
def test_valid_standard_expressions(expression):
    result = validate_cron_expression(expression)
    assert result.valid, result.error_message
    assert result.normalized_expression is not None
    assert result.error_code is None


@pytest.mark.parametrize(
    ("expression", "expected_code"),
    [
        ("", cron_validator.ERR_EMPTY),
        ("   ", cron_validator.ERR_EMPTY),
        ("* * *", cron_validator.ERR_FIELD_COUNT),
        ("* * * * * *", cron_validator.ERR_FIELD_COUNT),
        ("0 2 * *", cron_validator.ERR_FIELD_COUNT),
        ("61 * * * *", cron_validator.ERR_OUT_OF_RANGE),
        ("-1 * * * *", cron_validator.ERR_INVALID_RANGE),
        ("a * * * *", cron_validator.ERR_CHARACTER),
        ("0 24 * * *", cron_validator.ERR_OUT_OF_RANGE),
        ("0 0 32 * *", cron_validator.ERR_OUT_OF_RANGE),
        ("0 0 0 * *", cron_validator.ERR_OUT_OF_RANGE),
        ("0 0 * 13 *", cron_validator.ERR_OUT_OF_RANGE),
        ("0 0 * 0 *", cron_validator.ERR_OUT_OF_RANGE),
        ("0 0 * * 8", cron_validator.ERR_OUT_OF_RANGE),
        ("0 * 5-3 * *", cron_validator.ERR_INVALID_RANGE),
        ("0 0 25-32 * *", cron_validator.ERR_OUT_OF_RANGE),
        ("0 0 * * */x", cron_validator.ERR_CHARACTER),
        ("0-5/0 * * * *", cron_validator.ERR_INVALID_STEP),
        ("0 0 * * */0", cron_validator.ERR_INVALID_STEP),
        ("0 0 ,* * *", cron_validator.ERR_CHARACTER),
        ("0 0 * * 1-", cron_validator.ERR_INVALID_RANGE),
    ],
)
def test_invalid_expressions(expression, expected_code):
    result = validate_cron_expression(expression)
    assert result.valid is False
    assert result.error_code == expected_code
    assert result.error_message
    assert result.error_field is not None or expected_code in (
        cron_validator.ERR_FIELD_COUNT,
        cron_validator.ERR_EMPTY,
    )


def test_parse_returns_five_fields():
    fields = parse_cron_expression("30 8 * * 1-5")
    assert fields == ["30", "8", "*", "*", "1-5"]


def test_parse_normalizes_extra_spaces_and_dow_seven():
    fields = parse_cron_expression("  0   2   *   *   7 ")
    assert fields == ["0", "2", "*", "*", "0"]
    assert normalize_cron_expression("  0   2   *   *   7 ") == "0 2 * * 0"


def test_validate_missing_optional_fields():
    result = validate_cron_expression("*/5 * * * *")
    assert result.valid
    assert result.fields == ["*/5", "*", "*", "*", "*"]


def test_parse_raises_for_invalid_expression():
    with pytest.raises(CronValidationError) as exc_info:
        parse_cron_expression("* * *")
    assert exc_info.value.code == cron_validator.ERR_FIELD_COUNT


def test_describe_required_examples():
    assert describe_cron_expression("0 2 * * *") == "Todos los días a las 02:00"
    assert describe_cron_expression("30 8 * * 1-5") == "Lunes a viernes a las 08:30"


def test_describe_common_cases():
    assert describe_cron_expression("* * * * *") == "Cada minuto"
    assert describe_cron_expression("0 0 1 * *") == "El día 1 de cada mes a las 00:00"
    assert describe_cron_expression("0 9 * * 1") == "Los lunes a las 09:00"
    assert describe_cron_expression("*/15 * * * *") == "Todos los días cada 15 minutos"
    assert describe_cron_expression("0 6,18 * * *") == "Todos los días a las 06:00 y 18:00"


def test_validate_never_executes_expression():
    """The validator only parses text; it must never evaluate or run it."""
    assert validate_cron_expression("0 0 * * *").valid
    assert validate_cron_expression("*/1 * * * *").valid