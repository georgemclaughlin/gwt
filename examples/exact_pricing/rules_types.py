# Generated from examples/exact_pricing/rules.gwt. Do not edit by hand.
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal, TypeAlias, TypedDict, cast

from gwtlang import CompiledProgram, ExecutionResult, compile_file

class Cart(TypedDict):
    mode: Literal['reserve', 'quote']
    quantity: int
    unit_price: str
    total: str
    status: str

class PriceCartRequest(TypedDict):
    cart: Cart

class PriceCartOutput(TypedDict):
    cart: Cart

GwtRequestName: TypeAlias = Literal['price cart']
GwtRequest: TypeAlias = PriceCartRequest
GwtOutput: TypeAlias = PriceCartOutput

PRICE_CART_REQUEST: GwtRequestName = 'price cart'

GwtRequests = TypedDict(
    'GwtRequests',
    {
        'price cart': PriceCartRequest,
    },
)

GwtOutputs = TypedDict(
    'GwtOutputs',
    {
        'price cart': PriceCartOutput,
    },
)

class ExactPricingClient:
    def __init__(self, program: CompiledProgram) -> None:
        self._program = program

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        import_roots: Iterable[str | Path] | None = None,
        allow_absolute_imports: bool = True,
    ) -> ExactPricingClient:
        return cls(
            compile_file(
                path,
                import_roots=import_roots,
                allow_absolute_imports=allow_absolute_imports,
            )
        )

    def run_price_cart(self, request: PriceCartRequest) -> ExecutionResult:
        return self._program.run_json(
            cast(dict[str, Any], request),
            request=PRICE_CART_REQUEST,
        )

    def price_cart(self, request: PriceCartRequest) -> PriceCartOutput:
        return cast(
            PriceCartOutput,
            self.run_price_cart(request).as_payload()["result"],
        )
