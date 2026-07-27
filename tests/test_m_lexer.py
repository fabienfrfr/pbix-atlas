import pytest

from pbix_atlas.m_lexer import MLexError, TokType, tokenize


def _types(text):
    return [(t.type, t.value) for t in tokenize(text)]


def test_tokenizes_numbers():
    assert _types("42") == [(TokType.NUMBER, "42"), (TokType.EOF, "")]
    assert _types("3.14") == [(TokType.NUMBER, "3.14"), (TokType.EOF, "")]
    assert _types(".5") == [(TokType.NUMBER, ".5"), (TokType.EOF, "")]
    assert _types("1e10") == [(TokType.NUMBER, "1e10"), (TokType.EOF, "")]
    assert _types("2.5E-3") == [(TokType.NUMBER, "2.5E-3"), (TokType.EOF, "")]


def test_tokenizes_strings():
    assert _types('"hello"') == [(TokType.STRING, "hello"), (TokType.EOF, "")]
    assert _types('"say ""hi"""') == [(TokType.STRING, 'say "hi"'), (TokType.EOF, "")]


def test_tokenizes_identifiers():
    assert _types("foo") == [(TokType.IDENT, "foo"), (TokType.EOF, "")]
    assert _types("Foo.Bar") == [(TokType.IDENT, "Foo.Bar"), (TokType.EOF, "")]


def test_tokenizes_quoted_identifier():
    assert _types('#"My Column"') == [(TokType.IDENT, "My Column"), (TokType.EOF, "")]


def test_tokenizes_hash_constructors():
    assert _types("#table") == [(TokType.IDENT, "#table"), (TokType.EOF, "")]
    assert _types("#date") == [(TokType.IDENT, "#date"), (TokType.EOF, "")]


def test_tokenizes_keywords():
    keywords = [
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
    ]
    for kw in keywords:
        result = _types(kw)
        assert result[0] == (TokType.KEYWORD, kw)


def test_dotted_identifier_not_keyword():
    assert _types("let.x")[0][0] == TokType.IDENT


def test_tokenizes_operators():
    singles = "+-*/,(){}[]=<>&.?@!;:"
    for ch in singles:
        assert _types(ch)[0] == (TokType.OP, ch)
    assert _types("<=")[0] == (TokType.OP, "<=")
    assert _types(">=")[0] == (TokType.OP, ">=")
    assert _types("<>")[0] == (TokType.OP, "<>")
    assert _types("=>")[0] == (TokType.OP, "=>")
    assert _types("??")[0] == (TokType.OP, "??")
    assert _types("..")[0] == (TokType.OP, "..")


def test_skips_whitespace_and_comments():
    assert _types("  42  ") == [(TokType.NUMBER, "42"), (TokType.EOF, "")]
    assert _types("42 // comment") == [(TokType.NUMBER, "42"), (TokType.EOF, "")]


def test_skips_block_comment():
    assert _types("1 /* comment */ 2") == [
        (TokType.NUMBER, "1"),
        (TokType.NUMBER, "2"),
        (TokType.EOF, ""),
    ]


def test_raises_on_invalid_character():
    with pytest.raises(MLexError):
        tokenize("42 $ 1")


def test_eof_token():
    tokens = tokenize("")
    assert len(tokens) == 1
    assert tokens[0].type == TokType.EOF
    assert tokens[0].value == ""


def test_complex_expression():
    assert _types("let Source = 1 in Source") == [
        (TokType.KEYWORD, "let"),
        (TokType.IDENT, "Source"),
        (TokType.OP, "="),
        (TokType.NUMBER, "1"),
        (TokType.KEYWORD, "in"),
        (TokType.IDENT, "Source"),
        (TokType.EOF, ""),
    ]
