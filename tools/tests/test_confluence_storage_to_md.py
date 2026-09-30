from storage_to_md import convert

STORAGE = """
<ac:layout><ac:layout-section ac:type="single"><ac:layout-cell>
<ac:structured-macro ac:name="toc"><ac:parameter ac:name="maxLevel">2</ac:parameter></ac:structured-macro>
<h1>Payments&nbsp;v2</h1>
<p style="color: red;">Customers can <strong>pay</strong> by card. See <a href="https://jira.example.com/browse/PAY-7">ticket</a>.</p>
<ul><li><p>Cards</p><ul><li>Visa</li><li>Mastercard</li></ul></li><li>Wallets</li></ul>
<ol><li>First</li><li>Second</li></ol>
<table><colgroup><col /></colgroup><tbody>
<tr><th>Case</th><th>Expected</th></tr>
<tr><td>Expired card</td><td>Error <code>E42</code> | declined</td></tr>
</tbody></table>
<p><ac:structured-macro ac:name="jira"><ac:parameter ac:name="server">JIRA</ac:parameter><ac:parameter ac:name="key">PAY-1</ac:parameter></ac:structured-macro></p>
<p><ac:link><ri:page ri:content-title="Refunds" /><ac:plain-text-link-body><![CDATA[refund rules]]></ac:plain-text-link-body></ac:link>
and <ac:link><ri:page ri:content-title="Limits" /></ac:link></p>
<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">java</ac:parameter><ac:plain-text-body><![CDATA[if (a < b && c) { pay(); }]]></ac:plain-text-body></ac:structured-macro>
<ac:structured-macro ac:name="info"><ac:parameter ac:name="title">Note</ac:parameter><ac:rich-text-body><p>Only EUR.</p></ac:rich-text-body></ac:structured-macro>
<p>Status: <ac:structured-macro ac:name="status"><ac:parameter ac:name="title">IN REVIEW</ac:parameter></ac:structured-macro></p>
<ac:task-list><ac:task><ac:task-status>complete</ac:task-status><ac:task-body>Write plan</ac:task-body></ac:task>
<ac:task><ac:task-status>incomplete</ac:task-status><ac:task-body>Review plan</ac:task-body></ac:task></ac:task-list>
<p><ac:image><ri:attachment ri:filename="diagram.png" /></ac:image></p>
<p></p>
<h2>Out of scope</h2>
</ac:layout-cell></ac:layout-section></ac:layout>
"""


def test_converts_storage_to_compact_markdown():
    c = convert(STORAGE)
    md = c.markdown

    assert md.startswith("# Payments v2")
    assert "Customers can pay by card. See [ticket](https://jira.example.com/browse/PAY-7)." in md
    assert "- Cards\n  - Visa\n  - Mastercard\n- Wallets" in md
    assert "1. First\n2. Second" in md
    assert "| Case | Expected |\n|---|---|\n| Expired card | Error `E42` \\| declined |" in md
    assert "PAY-1" in md
    assert "refund rules [[Refunds]] and [[Limits]]" in md
    assert "```java\nif (a < b && c) { pay(); }\n```" in md
    assert "**Note**\n\nOnly EUR." in md
    assert "Status: [IN REVIEW]" in md
    assert "- [x] Write plan\n- [ ] Review plan" in md

    # noise is gone
    for junk in ("maxLevel", "style", "diagram.png", "JIRA", "\n\n\n", "\xa0"):
        assert junk not in md

    assert c.headings == ["Payments v2", "Out of scope"]
    assert c.jira_macro_keys == ["PAY-1"]
    assert c.link_titles == ["Refunds", "Limits"]


def test_markdown_is_much_smaller_than_storage():
    assert len(convert(STORAGE).markdown) < len(STORAGE) / 2


def test_no_space_before_punctuation_after_macros():
    md = convert('<p>Epic <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">SHOP-1</ac:parameter>'
                 '</ac:structured-macro>. Done</p>').markdown
    assert md == "Epic SHOP-1. Done"


def test_unclosed_tags_and_plain_text():
    assert convert("<p>one<p>two").markdown == "one\n\ntwo"
    assert convert("just text").markdown == "just text"


def test_include_macro_becomes_link():
    c = convert('<ac:structured-macro ac:name="include"><ac:parameter ac:name="">'
                '<ac:link><ri:page ri:content-title="Shared rules" /></ac:link></ac:parameter></ac:structured-macro>')
    assert c.markdown == "[[Shared rules]]"
    assert c.link_titles == ["Shared rules"]
