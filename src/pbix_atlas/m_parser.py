"""Recursive-descent parser for M expressions -> a small AST.

Scoped to what Power Query Desktop actually emits for applied steps
(let-blocks, function calls, each/lambda, if/then/else, list/record
literals, field/item access, try/otherwise) rather than the full M grammar.
Built in-house after a published third-party M parser (pbi-parsers 0.9.5)
turned out to be missing the `<`/`<=` operators entirely and unable to parse
multi-parameter or typed lambdas - real gaps that would have meant
hardcoding workarounds around someone else's incomplete grammar instead of
owning correctness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from .m_lexer import Token, TokType, tokenize


class MParseError(Exception):
    pass


# --------------------------------------------------------------------------- AST
@dataclass
class Lit:
    value: object


@dataclass
class Ident:
    name: str


@dataclass
class FieldAccess:
    target: "MNode"
    field: str


@dataclass
class ItemAccess:
    target: "MNode"
    index: "MNode"


@dataclass
class Invoke:
    func: "MNode"
    args: list["MNode"]


@dataclass
class Lambda:
    params: list[str]     # "_" for `each expr` sugar
    body: "MNode"


@dataclass
class If:
    cond: "MNode"
    then_: "MNode"
    else_: "MNode"


@dataclass
class BinOp:
    op: str
    left: "MNode"
    right: "MNode"


@dataclass
class UnaryOp:
    op: str
    expr: "MNode"


@dataclass
class ListExpr:
    items: list["MNode"]


@dataclass
class RecordExpr:
    fields: list[tuple[str, "MNode"]]


@dataclass
class LetExpr:
    steps: list[tuple[str, "MNode"]]
    body: "MNode"


@dataclass
class TryExpr:
    expr: "MNode"
    otherwise: Optional["MNode"]


@dataclass
class TypeLit:
    raw: str


MNode = Union[
    Lit, Ident, FieldAccess, ItemAccess, Invoke, Lambda,
    If, BinOp, UnaryOp, ListExpr, RecordExpr, LetExpr, TryExpr, TypeLit,
]


# ------------------------------------------------------------------------ parser
_BIN_PRECEDENCE = {
    "or": 1,
    "and": 2,
    "=": 3, "<>": 3, "<": 3, ">": 3, "<=": 3, ">=": 3,
    "??": 4,
    "&": 5,
    "+": 6, "-": 6,
    "*": 7, "/": 7,
}


class MParser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = tokenize(text)
        self.i = 0

    def _read_bracket_field(self) -> str:
        """Reads a `[Field Name]` field reference straight off the source
        text (not tokens): M column names can contain spaces/accents/etc.
        without quoting, so they don't tokenize as a single identifier."""
        start_pos = self._peek().pos
        text = self.text
        i = start_pos + 1
        depth = 0
        while i < len(text):
            ch = text[i]
            if ch == "[":
                depth += 1
            elif ch == "]":
                if depth == 0:
                    break
                depth -= 1
            i += 1
        field_name = text[start_pos + 1:i].strip()
        close_pos = i
        while self.tokens[self.i].pos < close_pos and self.tokens[self.i].type != TokType.EOF:
            self.i += 1
        if self.tokens[self.i].value == "]":
            self.i += 1
        return field_name

    def _looks_like_record(self) -> bool:
        """Disambiguates `[a = 1, b = 2]` (record literal) from `[Field Name]`
        (bare field access): scan raw text for a top-level `=` before the
        matching `]` - M record field names are always plain identifiers
        immediately followed by `=`, whereas field access never contains one."""
        start_pos = self._peek().pos
        text = self.text
        i = start_pos + 1
        depth = 0
        while i < len(text):
            ch = text[i]
            if ch == "[":
                depth += 1
            elif ch == "]":
                if depth == 0:
                    return False
                depth -= 1
            elif ch == "=" and depth == 0:
                prev_ch = text[i - 1] if i > 0 else ""
                next_ch = text[i + 1] if i + 1 < len(text) else ""
                if prev_ch not in "<>=" and next_ch not in "=>":
                    return True
            i += 1
        return False

    def _peek(self, offset: int = 0) -> Token:
        idx = min(self.i + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def _advance(self) -> Token:
        tok = self.tokens[self.i]
        self.i = min(self.i + 1, len(self.tokens) - 1)
        return tok

    def _check(self, value: str) -> bool:
        tok = self._peek()
        return tok.value == value and tok.type in (TokType.OP, TokType.KEYWORD)

    def _expect(self, value: str) -> Token:
        if not self._check(value):
            tok = self._peek()
            raise MParseError(f"expected {value!r} but got {tok.value!r} at {tok.pos}")
        return self._advance()

    def parse_program(self) -> MNode:
        node = self.parse_expr()
        if self._peek().type != TokType.EOF:
            raise MParseError(f"unexpected trailing tokens near {self._peek().value!r} (pos {self._peek().pos})")
        return node

    def parse_expr(self) -> MNode:
        node = self._parse_binary(0)
        while self._check("meta"):
            self._advance()
            self.parse_unary()  # metadata is evaluated-and-discarded
        while self._check("as"):
            self._advance()
            self._parse_type()  # type ascription is discarded (no runtime effect of interest)
        return node

    def _parse_binary(self, min_prec: int) -> MNode:
        left = self.parse_unary()
        while True:
            tok = self._peek()
            op = tok.value
            if op not in _BIN_PRECEDENCE or tok.type not in (TokType.OP, TokType.KEYWORD):
                break
            prec = _BIN_PRECEDENCE[op]
            if prec < min_prec:
                break
            self._advance()
            right = self._parse_binary(prec + 1)
            left = BinOp(op=op, left=left, right=right)
        return left

    def parse_unary(self) -> MNode:
        tok = self._peek()
        if tok.value in ("-", "+", "not") and tok.type in (TokType.OP, TokType.KEYWORD):
            self._advance()
            return UnaryOp(op=tok.value, expr=self.parse_unary())
        return self.parse_postfix()

    def parse_postfix(self) -> MNode:
        node = self.parse_primary()
        while True:
            if self._check("("):
                self._advance()
                args = self._parse_arg_list(")")
                node = Invoke(func=node, args=args)
            elif self._check("["):
                field_name = self._read_bracket_field()
                if self._check("?"):
                    self._advance()
                node = FieldAccess(target=node, field=field_name)
            elif self._check("{"):
                self._advance()
                idx = self.parse_expr()
                self._expect("}")
                node = ItemAccess(target=node, index=idx)
            else:
                break
        return node

    def _parse_arg_list(self, closing: str) -> list[MNode]:
        args: list[MNode] = []
        if self._check(closing):
            self._advance()
            return args
        while True:
            args.append(self.parse_expr())
            if self._check(","):
                self._advance()
                continue
            self._expect(closing)
            break
        return args

    def parse_primary(self) -> MNode:  # noqa: PLR0911
        tok = self._peek()

        if tok.type == TokType.NUMBER:
            self._advance()
            val = float(tok.value) if ("." in tok.value or "e" in tok.value.lower()) else int(tok.value)
            return Lit(val)

        if tok.type == TokType.STRING:
            self._advance()
            return Lit(tok.value)

        if tok.value == "true" and tok.type == TokType.KEYWORD:
            self._advance()
            return Lit(True)
        if tok.value == "false" and tok.type == TokType.KEYWORD:
            self._advance()
            return Lit(False)
        if tok.value == "null" and tok.type == TokType.KEYWORD:
            self._advance()
            return Lit(None)

        if tok.value == "each" and tok.type == TokType.KEYWORD:
            self._advance()
            return Lambda(params=["_"], body=self.parse_expr())

        if tok.value == "if" and tok.type == TokType.KEYWORD:
            self._advance()
            cond = self.parse_expr()
            self._expect("then")
            then_ = self.parse_expr()
            self._expect("else")
            else_ = self.parse_expr()
            return If(cond=cond, then_=then_, else_=else_)

        if tok.value == "try" and tok.type == TokType.KEYWORD:
            self._advance()
            expr = self.parse_expr()
            otherwise = None
            if self._check("otherwise"):
                self._advance()
                otherwise = self.parse_expr()
            return TryExpr(expr=expr, otherwise=otherwise)

        if tok.value == "let" and tok.type == TokType.KEYWORD:
            return self._parse_let()

        if tok.value == "type" and tok.type == TokType.KEYWORD:
            self._advance()
            return self._parse_type()

        if tok.value == "error" and tok.type == TokType.KEYWORD:
            self._advance()
            return Invoke(func=Ident("__m_error__"), args=[self.parse_expr()])

        if self._check("("):
            lambda_node = self._try_parse_lambda()
            if lambda_node is not None:
                return lambda_node
            self._advance()
            expr = self.parse_expr()
            self._expect(")")
            return expr

        if self._check("{"):
            self._advance()
            items = self._parse_arg_list("}")
            return ListExpr(items=items)

        if self._check("["):
            if not self._looks_like_record():
                field_name = self._read_bracket_field()
                if self._check("?"):
                    self._advance()
                return FieldAccess(target=Ident("_"), field=field_name)
            self._advance()
            fields: list[tuple[str, MNode]] = []
            if not self._check("]"):
                while True:
                    name_tok = self._advance()
                    self._expect("=")
                    val = self.parse_expr()
                    fields.append((name_tok.value, val))
                    if self._check(","):
                        self._advance()
                        continue
                    break
            self._expect("]")
            return RecordExpr(fields=fields)

        if tok.type == TokType.IDENT:
            self._advance()
            return Ident(tok.value)

        raise MParseError(f"unexpected token {tok.value!r} at {tok.pos}")

    def _try_parse_lambda(self) -> Optional[Lambda]:
        """Try to parse `(p1, p2 [as Type], ...) => body`; on failure, rewind
        and let the caller fall back to plain parenthesized-expression parsing."""
        save = self.i
        try:
            self._expect("(")
            params: list[str] = []
            if not self._check(")"):
                while True:
                    if self._peek().type != TokType.IDENT:
                        raise MParseError("not a parameter list")
                    pname = self._advance().value
                    if self._check("as"):
                        self._advance()
                        self._parse_type()
                    params.append(pname)
                    if self._check(","):
                        self._advance()
                        continue
                    break
            self._expect(")")
            if self._check("as"):  # return type ascription: `(x as number) as number => ...`
                self._advance()
                self._parse_type()
            self._expect("=>")
            body = self.parse_expr()
            return Lambda(params=params, body=body)
        except MParseError:
            self.i = save
            return None

    def _parse_let(self) -> MNode:
        self._expect("let")
        steps: list[tuple[str, MNode]] = []
        if not self._check("in"):
            while True:
                name_tok = self._advance()
                self._expect("=")
                expr = self.parse_expr()
                steps.append((name_tok.value, expr))
                if self._check(","):
                    self._advance()
                    continue
                break
        self._expect("in")
        body = self.parse_expr()
        return LetExpr(steps=steps, body=body)

    def _parse_type(self) -> MNode:
        if self._check("nullable"):
            self._advance()
        tok = self._peek()
        if tok.value in ("table", "record") and tok.type == TokType.IDENT:
            self._advance()
            raw = tok.value
            if self._check("["):
                depth = 0
                while True:
                    t = self._advance()
                    if t.value == "[":
                        depth += 1
                    elif t.value == "]":
                        depth -= 1
                        if depth == 0:
                            break
                raw += " [...]"
            return TypeLit(raw=raw)
        if self._check("function") and self.tokens[self.i + 1].value == "(":
            # `type function (x as number) as number` - skip the parameter list
            self._advance()
            self._advance()
            depth = 1
            while depth:
                t = self._advance()
                if t.value == "(":
                    depth += 1
                elif t.value == ")":
                    depth -= 1
            if self._check("as"):
                self._advance()
                self._parse_type()
            return TypeLit(raw="function")
        if tok.type in (TokType.IDENT, TokType.KEYWORD) and tok.value != "meta":
            self._advance()
            return TypeLit(raw=tok.value)
        raise MParseError(f"unrecognized type token {tok.value!r} at {tok.pos}")


def parse_m_expression(text: str) -> MNode:
    return MParser(text).parse_program()
