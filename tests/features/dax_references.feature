Feature: DAX reference parsing
  As a lineage tool
  I want to extract Table[Field] and [Field] references from DAX expressions
  So that calculated columns and measures can be linked to what they depend on

  Scenario: Parsing a qualified column reference
    Given the DAX expression: SELECTEDVALUE(DA_GLD[DA_WIP])
    When I parse DAX references in the expression
    Then a reference to table "DA_GLD" and field "DA_WIP" is found

  Scenario: Parsing a quoted table reference
    Given the DAX expression: RELATED('DIM_TGI'[Nom])
    When I parse DAX references in the expression
    Then a reference to table "DIM_TGI" and field "Nom" is found

  Scenario: Parsing an unqualified reference
    Given the DAX expression: IF([MAJ_RAPPORT_OK] = "OK", "OK", "KO")
    When I parse DAX references in the expression
    Then a reference with no table and field "MAJ_RAPPORT_OK" is found

  Scenario: Parsing a column name containing an apostrophe
    Given the DAX expression: DA_GLD[Date_demande_d'achat]
    When I parse DAX references in the expression
    Then a reference to table "DA_GLD" and field "Date_demande_d'achat" is found

  Scenario: Parsing an empty expression
    Given an empty DAX expression
    When I parse DAX references in the expression
    Then no reference is found
