from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .errors import GwtError


class Scope(Protocol):
    def resolve_name(self, name: str) -> Any:
        ...


@dataclass(frozen=True)
class Token:
    kind: str
    value: str


def evaluate_expression(text: str, scope: Scope) -> Any:
    parser = ExpressionParser(_scan(text))
    expression = parser.parse()
    return expression.evaluate(scope)


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
        if self.operator == "-":
            return -value
        if self.operator == "not":
            return not _truthy(value)
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

        if self.operator == "+":
            return left + right
        if self.operator == "-":
            return left - right
        if self.operator == "*":
            return left * right
        if self.operator == "/":
            return left / right
        if self.operator == "==":
            return left == right
        if self.operator == "!=":
            return left != right
        if self.operator == ">":
            return left > right
        if self.operator == "<":
            return left < right
        if self.operator == ">=":
            return left >= right
        if self.operator == "<=":
            return left <= right
        raise AssertionError(self.operator)


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
        expression = self._equality()
        while self._match("word", "and"):
            expression = Binary(expression, "and", self._equality())
        return expression

    def _equality(self) -> Expr:
        expression = self._comparison()
        while self._match("operator", "==", "!="):
            operator = self._previous().value
            expression = Binary(expression, operator, self._comparison())
        return expression

    def _comparison(self) -> Expr:
        expression = self._term()
        while self._match("operator", ">", "<", ">=", "<="):
            operator = self._previous().value
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
        if self._match("word", "not"):
            return Unary("not", self._unary())
        return self._primary()

    def _primary(self) -> Expr:
        if self._match("number"):
            text = self._previous().value
            return Literal(float(text) if "." in text else int(text))
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
            kind = "word" if value in {"and", "or", "not", "true", "false"} else "identifier"
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
