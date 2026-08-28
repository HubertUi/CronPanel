"""Centralized validation, normalization and human description of cron
expressions (standard 5-field UNIX syntax).

    ┌───────── minute        (0 - 59)
    │ ┌─────── hour          (0 - 23)
    │ │ ┌───── day of month  (1 - 31)
    │ │ │ ┌─── month         (1 - 12)
    │ │ │ │ ┌─ day of week   (0 - 6, Sunday = 0; 7 is accepted as Sunday)
    │ │ │ │ │
    * * * * *

Supported per field: ``*``, ``*/N``, ``N``, ``N-M``, ``N-M/S`` and comma
separated lists of those. Field values are validated for range and for
sensible ranges/counts, and errors are categorized with a stable error code.

This module only interprets text. It NEVER executes anything; the parsed
fields are data used to validate, store and describe schedules.
"""

from dataclasses import dataclass
import re

_FIELD_NAMES = ("minute", "hour", "day_of_month", "month", "day_of_week")
_FIELD_TITLES = {
    "minute": "minuto",
    "hour": "hora",
    "day_of_month": "día del mes",
    "month": "mes",
    "day_of_week": "día de la semana",
}
# Inclusive bounds of every field (day_of_week accepts 7 as an alias of 0).
_FIELD_BOUNDS = {
    "minute": (0, 59),
    "hour": (0, 23),
    "day_of_month": (1, 31),
    "month": (1, 12),
    "day_of_week": (0, 7),
}
# Effective values used for expansion (day_of_week collapses 7 into 0).
_FIELD_ALLOWED = {
    "minute": range(0, 60),
    "hour": range(0, 24),
    "day_of_month": range(1, 32),
    "month": range(1, 13),
    "day_of_week": range(0, 7),
}

_TOKEN_PATTERN = re.compile(r"^[0-9,\-*/]+$")

# Error codes (stable, surfaced in API responses).
ERR_EMPTY = "EMPTY_EXPRESSION"
ERR_FIELD_COUNT = "WRONG_FIELD_COUNT"
ERR_CHARACTER = "INVALID_CHARACTER"
ERR_EMPTY_FIELD = "EMPTY_FIELD"
ERR_INVALID_VALUE = "INVALID_VALUE"
ERR_INVALID_RANGE = "INVALID_RANGE"
ERR_OUT_OF_RANGE = "VALUE_OUT_OF_RANGE"
ERR_INVALID_STEP = "INVALID_STEP"

_MONTHS = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

_WEEKDAYS = {
    0: "domingo",
    1: "lunes",
    2: "martes",
    3: "miércoles",
    4: "jueves",
    5: "viernes",
    6: "sábado",
}


class CronValidationError(ValueError):
    """Raised when a cron expression or field is invalid.

    Carries a stable error code and the offending field name so callers can
    report structured errors (API 422 details, UI messages, tests).
    """

    def __init__(self, code: str, message: str, field: str | None = None) -> None:
        self.code = code
        self.message = message
        self.field = field
        super().__init__(message)


@dataclass
class CronValidation:
    valid: bool
    normalized_expression: str | None = None
    fields: list[str] | None = None
    error_code: str | None = None
    error_message: str | None = None
    error_field: str | None = None

    @property
    def as_dict(self) -> dict:
        return {
            "valid": self.valid,
            "normalized_expression": self.normalized_expression,
            "fields": self.fields,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "error_field": self.error_field,
        }


def _field_bounds(field_name: str) -> tuple[int, int]:
    return _FIELD_BOUNDS[field_name]


def _is_day_of_week(field_name: str) -> bool:
    return field_name == "day_of_week"


def _normalize_bound(field_name: str, value: int) -> int:
    """Collapse Sunday aliases (7 -> 0) for single values in day_of_week."""
    if _is_day_of_week(field_name) and value == 7:
        return 0
    return value


def _expand_token(token: str, field_name: str) -> set[int]:
    """Expand a single comma token into the concrete set of values it matches."""
    bounds = _field_bounds(field_name)
    allowed = _FIELD_ALLOWED[field_name]
    values = set()

    if token == "*":
        values.update(allowed)
        return values

    base = token
    step: int | None = None
    if "/" in token:
        base, _, raw_step = token.partition("/")
        if not raw_step.isdigit() or int(raw_step) <= 0:
            raise CronValidationError(
                ERR_INVALID_STEP,
                "El paso debe ser un número entero positivo.",
                field_name,
            )
        step = int(raw_step)

    if base == "*":
        start, stop = 0, 0
        if step is None:
            values.update(allowed)
            return values
        for index in range(start, max(allowed) + 1, step):
            if index in allowed:
                values.add(index)
        return values

    def _single(text: str) -> int:
        if not text.isdigit():
            raise CronValidationError(
                ERR_INVALID_VALUE, f"Valor inválido '{text}'.", field_name
            )
        value = int(text)
        if value < bounds[0] or value > bounds[1]:
            raise CronValidationError(
                ERR_OUT_OF_RANGE,
                f"El valor {value} está fuera del rango {bounds[0]}-{bounds[1]} "
                f"para {_FIELD_TITLES[field_name]}.",
                field_name,
            )
        return _normalize_bound(field_name, value)

    if "-" in base:
        raw_start, _, raw_end = base.partition("-")
        if not raw_start or not raw_end:
            raise CronValidationError(
                ERR_INVALID_RANGE, "Rango incompleto (se espera N-M).", field_name
            )
        start = _single(raw_start)
        end = _single(raw_end)
        if start > end:
            raise CronValidationError(
                ERR_INVALID_RANGE,
                f"El rango {start}-{end} está invertido en "
                f"{_FIELD_TITLES[field_name]}.",
                field_name,
            )
        for index in range(start, end + 1):
            values.add(index)
        if step is not None:
            values = {index for index in values if (index - start) % step == 0}
        return values

    single = _single(base)
    return {single}


def _validate_token(token: str, field_name: str) -> str:
    """Validate one comma element and return its normalized form."""
    if not _TOKEN_PATTERN.match(token):
        raise CronValidationError(
            ERR_CHARACTER,
            f"Caracteres no permitidos en {_FIELD_TITLES[field_name]}: '{token}'.",
            field_name,
        )

    if token == "*":
        return "*"

    base = token
    step: str | None = None
    if "/" in token:
        base, _, raw_step = token.partition("/")
        if not raw_step.isdigit() or int(raw_step) <= 0:
            raise CronValidationError(
                ERR_INVALID_STEP,
                "El paso debe ser un número entero positivo.",
                field_name,
            )
        step = raw_step

    if base == "*":
        return f"*/{step}" if step else "*"

    def _normalize_single(text: str) -> str:
        if not text.isdigit():
            raise CronValidationError(
                ERR_INVALID_VALUE, f"Valor inválido '{text}'.", field_name
            )
        value = int(text)
        bounds = _field_bounds(field_name)
        if value < bounds[0] or value > bounds[1]:
            raise CronValidationError(
                ERR_OUT_OF_RANGE,
                f"El valor {value} está fuera del rango {bounds[0]}-{bounds[1]} "
                f"para {_FIELD_TITLES[field_name]}.",
                field_name,
            )
        normalized = _normalize_bound(field_name, value)
        return str(normalized)

    if "-" in base:
        raw_start, _, raw_end = base.partition("-")
        if not raw_start or not raw_end:
            raise CronValidationError(
                ERR_INVALID_RANGE, "Rango incompleto (se espera N-M).", field_name
            )
        start_text = _normalize_single(raw_start)
        end_text = _normalize_single(raw_end)
        start, end = int(start_text), int(end_text)
        if start > end:
            raise CronValidationError(
                ERR_INVALID_RANGE,
                f"El rango {raw_start}-{raw_end} está invertido en "
                f"{_FIELD_TITLES[field_name]}.",
                field_name,
            )
        if step is not None and int(step) <= 0:
            raise CronValidationError(
                ERR_INVALID_STEP,
                "El paso debe ser un número entero positivo.",
                field_name,
            )
        return f"{start_text}-{end_text}/" + (step or "") if step else f"{start_text}-{end_text}"

    normalized = _normalize_single(base)
    return f"{normalized}/{step}" if step else normalized


def parse_cron_expression(expression: str | None) -> list[str]:
    """Validate and normalize an expression into its five fields.

    Raises:
        CronValidationError: with a stable code when the expression is invalid.

    Returns:
        List of the five normalized field strings (minute..day_of_week).
    """
    if expression is None or expression.strip() == "":
        raise CronValidationError(ERR_EMPTY, "La expresión cron está vacía.")

    tokens = expression.strip().split()
    if len(tokens) != 5:
        raise CronValidationError(
            ERR_FIELD_COUNT,
            f"Una expresión cron debe tener 5 campos; se recibieron {len(tokens)}.",
        )

    normalized_fields: list[str] = []
    for field_name, token in zip(_FIELD_NAMES, tokens):
        if token == "":
            raise CronValidationError(ERR_EMPTY_FIELD, "Campo vacío.", field_name)
        parts = token.split(",")
        normalized_parts = [_validate_token(part.strip(), field_name) for part in parts]
        # Validate the whole field expands within bounds (e.g., a-b/c).
        combined = set()
        for part in normalized_parts:
            combined.update(_expand_token(part, field_name))
        if not combined:
            raise CronValidationError(
                ERR_INVALID_VALUE, "La expresión no produce ningún valor.", field_name
            )
        normalized_fields.append(",".join(normalized_parts))

    return normalized_fields


def normalize_cron_expression(expression: str | None) -> str:
    """Return the canonical expression for a valid input (raises otherwise)."""
    return " ".join(parse_cron_expression(expression))


def validate_cron_expression(expression: str | None) -> CronValidation:
    """Structured validation result; never raises for invalid input."""
    try:
        fields = parse_cron_expression(expression)
    except CronValidationError as exc:
        return CronValidation(
            valid=False,
            error_code=exc.code,
            error_message=exc.message,
            error_field=exc.field,
        )
    return CronValidation(
        valid=True,
        normalized_expression=" ".join(fields),
        fields=fields,
    )


def expand_cron_field(field_name: str, token: str) -> list[int]:
    """Expand a validated field token into sorted concrete values."""
    values: set[int] = set()
    for part in token.split(","):
        values.update(_expand_token(part.strip(), field_name))
    return sorted(values)


# ---------------------------------------------------------------------------
# Human-readable description (Spanish)
# ---------------------------------------------------------------------------

def _plural_weekday(name: str) -> str:
    """Spanish weekday plural; -es/-etes days are invariant."""
    if name in ("lunes", "martes", "miércoles", "jueves", "viernes"):
        return name
    return f"{name}s"


def _weekday_phrase(final: list[int]) -> str | None:
    """Describe a set of weekday numbers (0=Sunday..6=Saturday)."""
    names = {index: _WEEKDAYS[index] for index in final}
    if final == [0, 1, 2, 3, 4, 5, 6]:
        return "todos los días"
    if final == [1, 2, 3, 4, 5]:
        return "lunes a viernes"
    if final in ([6, 0], [0, 6]):
        return "los fines de semana"
    if len(final) == 1:
        return f"los {_plural_weekday(names[final[0]])}"
    if len(final) == 2 and final[1] == final[0] + 1:
        return f"{names[final[0]]} a {names[final[1]]}"
    ordered = [names[index] for index in final]
    if len(ordered) == 2:
        return f"los {ordered[0]} y {ordered[1]}"
    return "los " + ", ".join(ordered[:-1]) + " y " + ordered[-1]


def _describe_days(dom: str, month: str, dow: str) -> str:
    if dom == "*" and month == "*" and dow == "*":
        return "Todos los días"

    parts: list[str] = []

    if dow == "*" and dom == "*" and month != "*":
        months = expand_cron_field("month", month)
        single = months[0] if len(months) == 1 else None
        if single is not None:
            parts.append(f"todos los días de {_MONTHS[single]}")
        else:
            parts.append(f"todos los días de los meses {', '.join(_MONTHS[i] for i in months)}")
    elif dom == "*" and month == "*":
        phrase = _weekday_phrase(expand_cron_field("day_of_week", dow))
        parts.append(phrase or "días seleccionados de la semana")
    elif dom != "*" and dow == "*" and month == "*":
        doms = expand_cron_field("day_of_month", dom)
        if len(doms) == 1:
            parts.append(f"el día {doms[0]} de cada mes")
        else:
            parts.append(f"los días {', '.join(str(i) for i in doms)} de cada mes")
    else:
        if dom != "*":
            doms = expand_cron_field("day_of_month", dom)
            parts.append(f"el día {doms[0]}" if len(doms) == 1 else f"los días {', '.join(str(i) for i in doms)}")
        if month != "*":
            months = expand_cron_field("month", month)
            parts.append(_MONTHS[months[0]] if len(months) == 1 else ", ".join(_MONTHS[i] for i in months))
        if dow != "*":
            phrase = _weekday_phrase(expand_cron_field("day_of_week", dow))
            if phrase:
                parts.append(phrase)

    return " ".join(part for part in parts if part).capitalize()


def _minutes_phrase(token: str, minutes: list[int]) -> str:
    if token == "*":
        return "cada minuto"
    if token.startswith("*/"):
        step = int(token[2:])
        return f"cada {step} minutos"
    if len(minutes) == 1:
        return f"el minuto {minutes[0]}"
    return "los minutos " + ", ".join(str(m) for m in minutes)


def describe_cron_expression(expression: str | None) -> str:
    """Return a human-readable Spanish description of a valid expression.

    Raises CronValidationError for invalid expressions (callers should
    validate first).
    """
    fields = parse_cron_expression(expression)
    minute, hour, dom, month, dow = fields

    if month == "*" and dom == "*" and dow == "*" and minute == "*" and hour == "*":
        return "Cada minuto"

    hour_values = expand_cron_field("hour", hour)
    minute_values = expand_cron_field("minute", minute)

    time_part: str
    if hour == "*" and minute == "*":
        time_part = "cada minuto"
    elif minute == "*":
        hours = hour_values
        if len(hours) == 1:
            time_part = f"cada minuto entre las {hours[0]:02d}:00 y las {hours[0]:02d}:59"
        else:
            time_part = "cada minuto"
    elif len(hour_values) <= 4 and len(minute_values) <= 4 and hour != "*" and minute != "*":
        times = sorted(h * 100 + m for h in hour_values for m in minute_values)
        rendered = [f"{value // 100:02d}:{value % 100:02d}" for value in times]
        if len(rendered) == 1:
            time_part = f"a las {rendered[0]}"
        elif len(rendered) == 2:
            time_part = f"a las {rendered[0]} y {rendered[1]}"
        else:
            time_part = "a las " + ", ".join(rendered[:-1]) + f" y {rendered[-1]}"
    elif hour == "*":
        time_part = _minutes_phrase(minute, minute_values)
    else:
        hours = hour_values
        hour_text = (
            f"la {hours[0]:02d}:00" if len(hours) == 1
            else f"las horas {', '.join(f'{h:02d}' for h in hours)}"
        )
        time_part = f"{_minutes_phrase(minute, minute_values)} de {hour_text}"

    day_part = _describe_days(dom, month, dow)
    return f"{day_part} {time_part}".strip()


def validate_and_normalize(expression: str | None) -> str:
    """Thin convenience wrapper: validate and normalize (raises on error)."""
    return normalize_cron_expression(expression)