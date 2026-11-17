from backend.importers.testrail_xml import parse_testrail_xml


def test_testrail_import_parses_nested_sections_and_case_metadata():
    content = b"""
    <suite>
      <sections>
        <section>
          <name>Authentication</name>
          <sections>
            <section>
              <name>OAuth</name>
              <cases>
                <case>
                  <id>41</id><title>Google login</title>
                  <priority_id>4</priority_id><type_id>1</type_id>
                </case>
                <case><id>42</id><title>   </title></case>
              </cases>
            </section>
          </sections>
          <cases>
            <case><id>7</id><title>Password login</title></case>
          </cases>
        </section>
      </sections>
    </suite>
    """

    result = parse_testrail_xml(content)

    assert result.source_provider == "testrail"
    assert result.format_detected == "testrail_xml"
    assert [(test.title, test.folder_path) for test in result.tests] == [
        ("Google login", "Authentication/OAuth"),
        ("Password login", "Authentication"),
    ]
    assert result.tests[0].type == "automated"
    assert result.tests[0].priority == "critical"
    assert result.tests[1].type == "manual"
    assert result.tests[1].priority == "med"
    assert result.warnings == [
        "Skipped case with no title in section 'Authentication/OAuth'"
    ]


def test_testrail_import_supports_sections_root_and_missing_sections():
    sections = parse_testrail_xml(b"""
      <sections><section><name>API</name><cases>
        <case><id>1</id><title>Health</title><priority_id>1</priority_id></case>
      </cases></section></sections>
    """)
    assert sections.tests[0].folder_path == "API"
    assert sections.tests[0].priority == "low"

    missing = parse_testrail_xml(b"<suite><name>Empty</name></suite>")
    assert missing.tests == []
    assert missing.warnings == ["No <sections> element found in XML"]


def test_testrail_import_rejects_malformed_xml():
    result = parse_testrail_xml(b"<suite><sections>")
    assert result.tests == []
    assert result.format_detected == "testrail_xml"
    assert result.warnings and result.warnings[0].startswith("XML parse error:")
