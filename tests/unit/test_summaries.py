from __future__ import annotations

import json

import pytest

from pg_diag.cli import main
from pg_diag.errors import ValidationError
from pg_diag.render.html import render_html
from pg_diag.summaries import artifact_from_html, merge_markdown_to_html, validate_summaries
from test_core_engine import _artifact


@pytest.fixture()
def report_files(tmp_path):
    artifact = _artifact()
    artifact['runtime']['snapshot_count'] = 61
    artifact['query_texts'] = {'-4023659083661925077': 'select 1'}
    artifact['object_ddl'] = {
        '123': {'kind': 'relation', 'identifier': 'public.t', 'ddl': 'CREATE TABLE t(id int);'}
    }
    html = tmp_path / 'report.html'
    html.write_text(render_html(artifact), encoding='utf-8')
    brief = tmp_path / 'brief summary.md'
    detailed = tmp_path / 'detailed audit.md'
    brief.write_text('# Краткая сводка\n[Источник](#item-s.i)', encoding='utf-8')
    detailed.write_text(
        '# Развёрнутый отчёт\n\n'
        '[Запрос](#item-s.i?queryid=-4023659083661925077)\n\n'
        '[Таблица](#item-s.i?oid=123)\n\n'
        'Подробное объяснение наблюдений и предлагаемых изменений.', encoding='utf-8',
    )
    return html, brief, detailed


@pytest.mark.parametrize('syntax', ['paths', 'json', 'csv'])
@pytest.mark.parametrize('reverse', [False, True])
def test_merge_cli_only_updates_html_and_preserves_artifact(report_files, syntax, reverse):
    html, brief, detailed = report_files
    original = artifact_from_html(html.read_text())
    json_path = html.with_suffix('.json')
    json_path.write_text(json.dumps(original))
    json_before = json_path.read_bytes()
    paths = [str(brief), str(detailed)]
    if reverse:
        paths.reverse()
    arguments = paths if syntax == 'paths' else [
        json.dumps(paths) if syntax == 'json' else '[' + ', '.join(paths) + ']'
    ]
    assert main(['--merge-md-to-html', '--md-files', *arguments, '--html-file', str(html)]) == 0
    merged = artifact_from_html(html.read_text())
    assert merged.pop('summaries') == {
        'brief': {'markdown': brief.read_text()}, 'detailed': {'markdown': detailed.read_text()},
    }
    assert merged == original
    assert merged['runtime']['snapshot_count'] == 61
    assert json_path.read_bytes() == json_before
    assert html.stat().st_mode & 0o777 == 0o600
    # Replacement is idempotent and does not add another artifact or summary section.
    first = html.read_bytes()
    assert main(['--merge-md-to-html', '--md-files', *paths, '--html-file', str(html)]) == 0
    assert html.read_bytes() == first


@pytest.mark.parametrize('text', [
    '', '[missing](#item-missing.item)', '[missing SQL](#item-s.i?queryid=9)',
    '[missing DDL](#item-s.i?oid=9)', '[invalid](#item-s.i?oid=123&queryid=1)',
    '[bad](javascript:alert)', '[wrong report](another.html#item-s.i)',
    '[`missing SQL`](#item-s.i?queryid=9)',
])
def test_invalid_markdown_does_not_modify_html(report_files, text):
    html, brief, detailed = report_files
    original = html.read_bytes()
    brief.write_text(text)
    with pytest.raises(ValidationError):
        merge_markdown_to_html(html, [str(brief), str(detailed)])
    assert html.read_bytes() == original


@pytest.mark.parametrize('case', ['equal', 'duplicate', 'missing', 'encoding', 'one', 'target'])
def test_invalid_input_files_leave_report_untouched(report_files, case):
    html, brief, detailed = report_files
    original = html.read_bytes()
    paths = [str(brief), str(detailed)]
    if case == 'equal':
        detailed.write_bytes(brief.read_bytes())
    elif case == 'duplicate':
        paths[1] = paths[0]
    elif case == 'missing':
        paths[1] += '.missing'
    elif case == 'encoding':
        brief.write_bytes(b'\xff')
    elif case == 'one':
        paths.pop()
    else:
        paths[0] = str(html)
    with pytest.raises(ValidationError):
        merge_markdown_to_html(html, paths)
    assert html.read_bytes() == original


@pytest.mark.parametrize('text', [
    '<html></html>',
    '<script id="pg-diag-artifact" type="application/json">{}</script>' * 2,
    '<script id="pg-diag-artifact" type="application/json">{broken}</script>',
    '<script id="pg-diag-artifact" type="application/json">[]</script>',
    '<script id="pg-diag-artifact" type="application/json">{}',
    '<script id="pg-diag-artifact">{}</script>',
])
def test_reject_invalid_html(text):
    with pytest.raises(ValidationError):
        artifact_from_html(text)


def test_literal_code_examples_are_not_treated_as_links(report_files):
    html, brief, detailed = report_files
    brief.write_text(
        '`[literal](#item-missing.item)`\n\n'
        '```md\n[example](#item-missing.item)\n```\n\n'
        '[`actual item`](#item-s.i)\n'
        '[PostgreSQL](https://www.postgresql.org/docs/)',
    )
    # Do not rely on the document's role after changing its size.
    merge_markdown_to_html(html, [str(brief), str(detailed)])


@pytest.mark.parametrize('hidden', ['section', 'item', 'internal'])
def test_summary_links_cannot_target_invisible_items(hidden):
    artifact = _artifact()
    artifact['summaries'] = {
        key: {'markdown': '[item](#item-s.i)'} for key in ['brief', 'detailed']
    }
    if hidden == 'section':
        artifact['sections'][0]['state'] = 'hidden'
    elif hidden == 'item':
        artifact['items']['s.i']['state'] = 'hidden'
    else:
        artifact['items']['s.i']['source_metadata']['internal'] = True
    with pytest.raises(ValidationError, match='invalid report link'):
        validate_summaries(artifact)


def test_merge_cli_machine_envelope(report_files, capsys):
    html, brief, detailed = report_files
    assert main(['--machine', '--merge-md-to-html', '--md-files', str(brief), str(detailed),
                 '--html-file', str(html)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'succeeded'
    assert result['artifacts'][0]['kind'] == 'DiagnosticReportHtml'


@pytest.mark.parametrize('args', [
    ['--merge-md-to-html'], ['--html-file', 'report.html'],
    ['--merge-md-to-html', '--component-capabilities'],
    ['--merge-md-to-html', 'validate'],
])
def test_merge_cli_rejects_incomplete_or_conflicting_options(args):
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
