Feature: Physical source detection
  As a lineage tool
  I want to detect physical data sources referenced in Power Query (M) expressions
  So that a PBIX report can be traced back to its origin, regardless of the source system

  Scenario: Detecting an HTTP source wrapped in Web.Contents
    Given the M expression: Csv.Document(Web.Contents("https://example.com/export.php?id=42"))
    When I detect sources in the expression
    Then a source of system "http" is detected
    And its identifier is "https://example.com/export.php?id=42"

  Scenario: Detecting an OData source
    Given the M expression: OData.Feed("https://example.com/odata/svc", null, [Implementation="2.0"])
    When I detect sources in the expression
    Then a source of system "odata" is detected

  Scenario: Detecting a SQL Server source with server and database
    Given the M expression: Sql.Database("myserver.database.windows.net", "mydb")
    When I detect sources in the expression
    Then a source of system "sql" is detected
    And its identifier is "myserver.database.windows.net/mydb"

  Scenario: Falling back to a bare literal URL parameter
    Given the M expression: "https://example.com/odata/root/" meta [IsParameterQuery=true]
    When I detect sources in the expression
    Then a source of system "http" is detected

  Scenario: Deduplicating a source detected by more than one detector
    Given the M expression: Web.Contents("https://example.com/a")
    When I detect sources in the expression
    Then exactly 1 source is detected

  Scenario: Normalizing an identifier keeps the query string (it may be the actual resource identity)
    Given a detected source with system "http" and identifier "https://example.com/req/export.php?id=42"
    When I normalize the source identifier
    Then the normalized identifier is "https://example.com/req/export.php?id=42"

  Scenario: Two calls to the same endpoint with different query params are distinct sources
    Given a first detected source with system "http" and identifier "https://example.com/req/export.php?id=42"
    And a second detected source with system "http" and identifier "https://example.com/req/export.php?id=43"
    When I normalize both source identifiers
    Then the two normalized identifiers are different
