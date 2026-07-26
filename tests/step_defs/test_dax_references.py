from pytest_bdd import given, parsers, scenarios, then, when

from pbix_atlas.dax import DaxReferenceParser

scenarios("../features/dax_references.feature")


@given(parsers.parse("the DAX expression: {expression}"), target_fixture="expression")
def dax_expression(expression):
    return expression


@given("an empty DAX expression", target_fixture="expression")
def empty_dax_expression():
    return ""


@when("I parse DAX references in the expression", target_fixture="parsed_references")
def parse_references(expression):
    return DaxReferenceParser().parse(expression)


@then(parsers.parse('a reference to table "{table}" and field "{field}" is found'))
def assert_qualified_reference(parsed_references, table, field):
    assert any(r.table == table and r.name == field for r in parsed_references)


@then(parsers.parse('a reference with no table and field "{field}" is found'))
def assert_unqualified_reference(parsed_references, field):
    assert any(r.table is None and r.name == field for r in parsed_references)


@then("no reference is found")
def assert_no_reference(parsed_references):
    assert parsed_references == []
