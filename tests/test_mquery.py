from pbix_atlas.mquery import MQueryDependencyResolver


def test_resolve_no_dependencies():
    queries = {
        "A": "let x = 1 in x",
        "B": "let y = 2 in y",
    }
    result = MQueryDependencyResolver().resolve(queries)
    assert result["A"] == set()
    assert result["B"] == set()


def test_resolve_simple_dependency():
    queries = {
        "Base": "let x = 1 in x",
        "Derived": "Base[Column]",
    }
    result = MQueryDependencyResolver().resolve(queries)
    assert "Base" in result["Derived"]
    assert result["Base"] == set()


def test_resolve_circular():
    queries = {
        "A": "B[Value]",
        "B": "A[Other]",
    }
    result = MQueryDependencyResolver().resolve(queries)
    assert "B" in result["A"]
    assert "A" in result["B"]


def test_resolve_self_not_included():
    queries = {
        "A": "A[Col] + 1",
    }
    result = MQueryDependencyResolver().resolve(queries)
    assert result["A"] == set()
