from pytest_bdd import given, parsers, scenarios, then, when

from pbix_atlas.models import SourceRef
from pbix_atlas.sources import SourceDetectorRegistry, normalize_source_identifier

scenarios("../features/source_detection.feature")


@given(parsers.parse("the M expression: {expression}"), target_fixture="expression")
def m_expression(expression):
    return expression


@when("I detect sources in the expression", target_fixture="detected_sources")
def detect_sources(expression):
    return SourceDetectorRegistry().detect(expression)


@then(parsers.parse('a source of system "{system}" is detected'))
def assert_system_detected(detected_sources, system):
    assert any(s.system == system for s in detected_sources)


@then(parsers.parse('its identifier is "{identifier}"'))
def assert_identifier(detected_sources, identifier):
    assert any(s.identifier == identifier for s in detected_sources)


@then(parsers.parse("exactly {count:d} source is detected"))
def assert_count(detected_sources, count):
    assert len(detected_sources) == count


@given(
    parsers.parse('a detected source with system "{system}" and identifier "{identifier}"'),
    target_fixture="source_ref",
)
def a_source_ref(system, identifier):
    return SourceRef(system=system, identifier=identifier, raw_match="")


@when("I normalize the source identifier", target_fixture="normalized_identifier")
def normalize(source_ref):
    return normalize_source_identifier(source_ref)


@then(parsers.parse('the normalized identifier is "{expected}"'))
def assert_normalized(normalized_identifier, expected):
    assert normalized_identifier == expected
