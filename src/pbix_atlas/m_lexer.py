"""M lexer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokType(Enum):
    """TokType (see attributes/methods below)."""

    NUMBER = auto()
    STRING = auto()
    IDENT = auto()  # bare identifier, dotted identifier, or #"quoted identifier"
    KEYWORD = auto()
    OP = auto()
    EOF = auto()


KEYWORDS = {
    "let",
    "in",
    "each",
    "if",
    "then",
    "else",
    "and",
    "or",
    "not",
    "true",
    "false",
    "null",
    "type",
    "meta",
    "as",
    "try",
    "otherwise",
    "error",
    "nullable",
    "is",
}

# Longest-match-first: order matters.
_MULTI_CHAR_OPS = ["<=", ">=", "<>", "=>", "??", ".."]
_SINGLE_CHAR_OPS = set("+-*/,(){}[]=<>&.?@!;:")


@dataclass
class Token:
    """Token (see attributes/methods below)."""

    type: TokType
    value: str
    pos: int


class MLexError(Exception):
    """MLexError (see attributes/methods below)."""

    pass


def tokenize(text: str) -> list[Token]:
    """Tokenize. Takes `text`."""
    tokens: list[Token] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]

        if ch.isspace():
            i += 1
            continue

        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue

        # Quoted step/identifier: #"..."
        if ch == "#" and i + 1 < n and text[i + 1] == '"':
            j = i + 2
            buf: list[str] = []
            while j < n:
                if text[j] == '"':
                    if j + 1 < n and text[j + 1] == '"':
                        buf.append('"')
                        j += 2
                        continue
                    j += 1
                    break
                buf.append(text[j])
                j += 1
            tokens.append(Token(TokType.IDENT, "".join(buf), i))
            i = j
            continue

        # #table / #date / #datetime / ... literal constructors
        if ch == "#" and i + 1 < n and text[i + 1].isalpha():
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tokens.append(Token(TokType.IDENT, "#" + text[i + 1 : j], i))
            i = j
            continue

        if ch == '"':
            j = i + 1
            buf = []
            while j < n:
                if text[j] == '"':
                    if j + 1 < n and text[j + 1] == '"':
                        buf.append('"')
                        j += 2
                        continue
                    j += 1
                    break
                buf.append(text[j])
                j += 1
            tokens.append(Token(TokType.STRING, "".join(buf), i))
            i = j
            continue

        if ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit()):
            j = i
            while j < n and (text[j].isdigit() or text[j] == "."):
                j += 1
            if j < n and text[j] in "eE":
                j += 1
                if j < n and text[j] in "+-":
                    j += 1
                while j < n and text[j].isdigit():
                    j += 1
            tokens.append(Token(TokType.NUMBER, text[i:j], i))
            i = j
            continue

        if ch.isalpha() or ch == "_":
            j = i
            while j < n:
                if text[j].isalnum() or text[j] == "_":
                    j += 1
                    continue
                # allow dotted identifiers (Table.AddColumn) as a single token,
                # but don't swallow a trailing "." with nothing alnum after it
                if text[j] == "." and j + 1 < n and (text[j + 1].isalnum() or text[j + 1] == "_"):
                    j += 1
                    continue
                break
            word = text[i:j]
            base = word.split(".")[0]
            ttype = TokType.KEYWORD if (base in KEYWORDS and "." not in word) else TokType.IDENT
            tokens.append(Token(ttype, word, i))
            i = j
            continue

        matched = False
        for op in _MULTI_CHAR_OPS:
            if text.startswith(op, i):
                tokens.append(Token(TokType.OP, op, i))
                i += len(op)
                matched = True
                break
        if matched:
            continue

        if ch in _SINGLE_CHAR_OPS:
            tokens.append(Token(TokType.OP, ch, i))
            i += 1
            continue

        raise MLexError(f"Unexpected character {ch!r} at position {i}")

    tokens.append(Token(TokType.EOF, "", n))
    return tokens
