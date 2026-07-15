from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, cast

from .errors import GwtError


class Scope(Protocol):
    def resolve_name(self, name: str) -> Any:
        ...


@dataclass(frozen=True)
class Token:
    kind: str
    value: str


def parse_expression(text: str) -> Expr:
    parser = ExpressionParser(_scan(text))
    return parser.parse()


def evaluate_expression(text: str, scope: Scope) -> Any:
    return parse_expression(text).evaluate(scope)


class Expr:
    def evaluate(self, scope: Scope) -> Any:
        raise NotImplementedError


@dataclass(frozen=True)
class Literal(Expr):
    value: Any

    def evaluate(self, scope: Scope) -> Any:
        return self.value


@dataclass(frozen=True)
class Name(Expr):
    value: str

    def evaluate(self, scope: Scope) -> Any:
        return scope.resolve_name(self.value)


@dataclass(frozen=True)
class Presence(Expr):
    value: Expr
    present: bool

    def evaluate(self, scope: Scope) -> Any:
        is_present = self.value.evaluate(scope) is not None
        return is_present if self.present else not is_present


@dataclass(frozen=True)
class ListLiteral(Expr):
    values: list[Expr]

    def evaluate(self, scope: Scope) -> Any:
        return [value.evaluate(scope) for value in self.values]


@dataclass(frozen=True)
class Unary(Expr):
    operator: str
    right: Expr

    def evaluate(self, scope: Scope) -> Any:
        value = self.right.evaluate(scope)
        try:
            if self.operator == "-":
                return -value
            if self.operator == "not":
                return not _truthy(value)
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise _operation_error(self.operator, exc) from exc
        raise AssertionError(self.operator)


@dataclass(frozen=True)
class Binary(Expr):
    left: Expr
    operator: str
    right: Expr

    def evaluate(self, scope: Scope) -> Any:
        if self.operator == "and":
            return _truthy(self.left.evaluate(scope)) and _truthy(self.right.evaluate(scope))
        if self.operator == "or":
            return _truthy(self.left.evaluate(scope)) or _truthy(self.right.evaluate(scope))

        left = self.left.evaluate(scope)
        right = self.right.evaluate(scope)
        try:
            left, right = _coerce_mixed_float_decimal(left, right)

            if self.operator == "+":
                return left + right
            if self.operator == "-":
                return left - right
            if self.operator == "*":
                return left * right
            if self.operator == "/":
                return left / right
            if self.operator == "==":
                return _equal_values(left, right, scope)
            if self.operator == "!=":
                return not _equal_values(left, right, scope)
            if self.operator == ">":
                return left > right
            if self.operator == "<":
                return left < right
            if self.operator == ">=":
                return left >= right
            if self.operator == "<=":
                return left <= right
            if self.operator == "contains":
                return _contains(left, right, scope)
        except (ArithmeticError, TypeError, ValueError) as exc:
            if self.operator == "contains":
                raise GwtError(
                    "contains requires a text, list, or mapping value on the left"
                ) from exc
            raise _operation_error(self.operator, exc) from exc
        raise AssertionError(self.operator)


def _operation_error(operator: str, error: BaseException) -> GwtError:
    if isinstance(error, ZeroDivisionError):
        return GwtError("division by zero")
    return GwtError(f"invalid operands for operator '{operator}': {error}")


def _coerce_mixed_float_decimal(left: Any, right: Any) -> tuple[Any, Any]:
    if isinstance(left, float) and isinstance(right, Decimal):
        return left, float(right)
    if isinstance(left, Decimal) and isinstance(right, float):
        return float(left), right
    return left, right


def _equal_values(left: object, right: object, scope: Scope) -> bool:
    """Compare JSON-shaped values without unmetered recursive collection walks."""

    tasks: list[tuple[str, object, object]] = [("compare", left, right)]
    while tasks:
        kind, first, second = tasks.pop()
        if kind == "list-items":
            iterator = cast(Any, first)
            try:
                left_item, right_item = next(iterator)
            except StopIteration:
                continue
            _consume_collection_work(scope)
            tasks.append((kind, iterator, second))
            tasks.append(("compare", left_item, right_item))
            continue
        if kind == "mapping-items":
            iterator = cast(Any, first)
            left_items, right_items = cast(
                tuple[dict[object, object], dict[object, object]],
                second,
            )
            try:
                key = next(iterator)
            except StopIteration:
                continue
            _consume_collection_work(scope)
            if key not in right_items:
                return False
            tasks.append((kind, iterator, second))
            tasks.append(("compare", left_items[key], right_items[key]))
            continue

        current_left, current_right = _coerce_mixed_float_decimal(first, second)
        if isinstance(current_left, list) and isinstance(current_right, list):
            left_items = cast(list[object], current_left)
            right_items = cast(list[object], current_right)
            if len(left_items) != len(right_items):
                return False
            tasks.append(("list-items", iter(zip(left_items, right_items)), ()))
            continue
        if isinstance(current_left, dict) and isinstance(current_right, dict):
            left_mapping = cast(dict[object, object], current_left)
            right_mapping = cast(dict[object, object], current_right)
            if len(left_mapping) != len(right_mapping):
                return False
            tasks.append(
                (
                    "mapping-items",
                    iter(left_mapping),
                    (left_mapping, right_mapping),
                )
            )
            continue
        if current_left != current_right:
            return False
    return True


def _contains(left: object, right: object, scope: Scope) -> bool:
    if isinstance(left, str):
        if not isinstance(right, str):
            raise TypeError("text membership requires text")
        for _ in left:
            _consume_collection_work(scope)
        return right in left
    if isinstance(left, list):
        for item in cast(list[object], left):
            _consume_collection_work(scope)
            if _equal_values(item, right, scope):
                return True
        return False
    if isinstance(left, dict):
        _consume_collection_work(scope)
        return right in left
    raise TypeError("left operand is not text, list, or mapping")


def _consume_collection_work(scope: Scope) -> None:
    consume = getattr(scope, "consume_expression_work", None)
    if callable(consume):
        consume()


class ExpressionParser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.current = 0

    def parse(self) -> Expr:
        expression = self._or()
        if not self._is_at_end():
            raise GwtError(f"unexpected token in expression: {self._peek().value}")
        return expression

    def _or(self) -> Expr:
        expression = self._and()
        while self._match("word", "or"):
            expression = Binary(expression, "or", self._and())
        return expression

    def _and(self) -> Expr:
        expression = self._not()
        while self._match("word", "and"):
            expression = Binary(expression, "and", self._not())
        return expression

    def _not(self) -> Expr:
        if self._match("word", "not"):
            return Unary("not", self._not())
        return self._equality()

    def _equality(self) -> Expr:
        expression = self._comparison()
        while self._match("operator", "==", "!="):
            operator = self._previous().value
            expression = Binary(expression, operator, self._comparison())
        return expression

    def _comparison(self) -> Expr:
        expression = self._term()
        if self._match("word", "is"):
            if self._match("word", "present"):
                expression = Presence(expression, True)
            elif self._match("word", "absent"):
                expression = Presence(expression, False)
            else:
                raise GwtError("expected 'present' or 'absent' after 'is'")
        while True:
            if self._match("operator", ">", "<", ">=", "<="):
                operator = self._previous().value
            elif self._match("identifier", "contains"):
                operator = "contains"
            else:
                break
            expression = Binary(expression, operator, self._term())
        return expression

    def _term(self) -> Expr:
        expression = self._factor()
        while self._match("operator", "+", "-"):
            operator = self._previous().value
            expression = Binary(expression, operator, self._factor())
        return expression

    def _factor(self) -> Expr:
        expression = self._unary()
        while self._match("operator", "*", "/"):
            operator = self._previous().value
            expression = Binary(expression, operator, self._unary())
        return expression

    def _unary(self) -> Expr:
        if self._match("operator", "-"):
            return Unary("-", self._unary())
        return self._primary()

    def _primary(self) -> Expr:
        if self._match("number"):
            text = self._previous().value
            return Literal(Decimal(text) if "." in text else int(text))
        if self._match("string"):
            return Literal(self._previous().value)
        if self._match("word", "true"):
            return Literal(True)
        if self._match("word", "false"):
            return Literal(False)
        if self._match("identifier"):
            return Name(self._previous().value)
        if self._match("left_paren"):
            expression = self._or()
            self._consume("right_paren", "expected ')' after expression")
            return expression
        if self._match("left_bracket"):
            values: list[Expr] = []
            if not self._check("right_bracket"):
                while True:
                    values.append(self._or())
                    if not self._match("comma"):
                        break
            self._consume("right_bracket", "expected ']' after list")
            return ListLiteral(values)
        raise GwtError(f"expected expression, got: {self._peek().value}")

    def _match(self, kind: str, *values: str) -> bool:
        if not self._check(kind, *values):
            return False
        self.current += 1
        return True

    def _consume(self, kind: str, message: str) -> Token:
        if self._check(kind):
            self.current += 1
            return self._previous()
        raise GwtError(message)

    def _check(self, kind: str, *values: str) -> bool:
        if self._is_at_end():
            return False
        token = self._peek()
        if token.kind != kind:
            return False
        return not values or token.value in values

    def _peek(self) -> Token:
        return self.tokens[self.current]

    def _previous(self) -> Token:
        return self.tokens[self.current - 1]

    def _is_at_end(self) -> bool:
        return self._peek().kind == "eof"


def _scan(text: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0

    while index < len(text):
        char = text[index]

        if char.isspace():
            index += 1
        elif char == '"':
            value, index = _scan_string(text, index)
            tokens.append(Token("string", value))
        elif char.isdigit():
            value, index = _scan_number(text, index)
            tokens.append(Token("number", value))
        elif char.isalpha() or char == "_":
            value, index = _scan_identifier(text, index)
            kind = (
                "word"
                if value
                in {"and", "or", "not", "true", "false", "is", "present", "absent"}
                else "identifier"
            )
            tokens.append(Token(kind, value))
        elif char in "()[]":
            kind = {
                "(": "left_paren",
                ")": "right_paren",
                "[": "left_bracket",
                "]": "right_bracket",
            }[char]
            tokens.append(Token(kind, char))
            index += 1
        elif char == ",":
            tokens.append(Token("comma", char))
            index += 1
        else:
            two = text[index : index + 2]
            if two in {"==", "!=", ">=", "<="}:
                tokens.append(Token("operator", two))
                index += 2
            elif char in "+-*/><":
                tokens.append(Token("operator", char))
                index += 1
            else:
                raise GwtError(f"unexpected character in expression: {char}")

    tokens.append(Token("eof", "end of expression"))
    return tokens


def _scan_string(text: str, start: int) -> tuple[str, int]:
    index = start + 1
    value = ""
    while index < len(text):
        char = text[index]
        if char == '"':
            return value, index + 1
        if char == "\\":
            index += 1
            if index >= len(text):
                raise GwtError("unterminated string literal")
            escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
            value += escapes.get(text[index], text[index])
        else:
            value += char
        index += 1
    raise GwtError("unterminated string literal")


def _scan_number(text: str, start: int) -> tuple[str, int]:
    index = start
    while index < len(text) and text[index].isdigit():
        index += 1
    if index < len(text) and text[index] == ".":
        index += 1
        if index >= len(text) or not text[index].isdigit():
            raise GwtError("decimal number requires digits after '.'")
        while index < len(text) and text[index].isdigit():
            index += 1
    return text[start:index], index


def _scan_identifier(text: str, start: int) -> tuple[str, int]:
    index = start
    while index < len(text) and (text[index].isalnum() or text[index] in "_."):
        index += 1
    return text[start:index], index


def _truthy(value: Any) -> bool:
    return bool(value)
