"""Run allocation regressions in a subprocess with a strict memory limit."""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest


def _run_bounded(script: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent("""\
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
        """) + textwrap.dedent(script)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_wal_archiver_metric_preserves_exponent_like_wal_names() -> None:
    _run_bounded("""
        from pg_diag.content_loader import load_content
        from pg_diag.metric_engine import build_metric_item
        from pg_diag.planner import PlannedItem
        from pg_diag.versioning import select_query_variant
        from importlib.resources import files

        content = load_content(files('pg_diag').joinpath('content'))
        metric = content.metrics['wal.archiver_delta']
        query = content.queries[metric['source_query']]
        variant = select_query_variant(query['title'], query, 180000).variant
        names = ['000000010000E67000000000', '0000000100000E1600000000']
        columns = ['scope', 'stats_reset', 'archived_count', 'failed_count',
                   'last_archived_wal', 'last_failed_wal']
        snapshots = [
            {'timestamp': timestamp, 'items': {'source': {
                'collection_status': 'ok',
                'result': {'kind': 'table', 'rows': [
                    ['cluster', '2026-09-01', count, count, *names]
                ]},
            }}}
            for timestamp, count in [('2026-09-23T13:20:00Z', 10),
                                     ('2026-09-23T13:26:00Z', 16)]
        ]
        planned = PlannedItem(
            item_id='snapshot_delta_workload.wal_archiver_delta',
            section_id='snapshot_delta_workload', item_key='wal_archiver_delta',
            title=metric['title'], source_kind='metric', status='planned',
            source_id='wal.archiver_delta', source_metadata={},
        )
        item = build_metric_item(
            planned, metric, snapshots, {}, {metric['source_query']: 'source'},
            {'source': {**variant, '_result_columns': columns}},
        )
        assert item['collection_status'] == 'ok', item
        assert item['result']['rows'] == [['cluster', 6, 6 / 360, 6, *names]]
        assert item['severity_level'] == 'medium'
    """)


@pytest.mark.parametrize("transform", ["first", "last", None])
def test_endpoint_text_transforms_do_not_parse_numbers(transform: str | None) -> None:
    _run_bounded(f"""
        from pg_diag.metric_engine import build_table_result

        names = ['000000010000E67000000000', '0000000100000E1600000000']
        metric = {{'table': {{'key_refs': ['id'], 'drop_zero_rows': False,
            'columns': [{{'name': 'label', 'value_ref': 'label',
                         'transform': {transform!r}, 'pg_type': 'text'}}]}}}}
        samples = [{{'timestamp': timestamp, 'rows': [{{'id': 1, 'label': name}}]}}
                   for timestamp, name in zip(
                       ['2026-09-23T13:20:00Z', '2026-09-23T13:26:00Z'], names)]
        result = build_table_result(metric, samples, {{}})
        assert result['rows'] == [[names[0 if {transform!r} == 'first' else 1]]]
    """)


def test_sample_sum_text_and_count_do_not_parse_numbers() -> None:
    _run_bounded("""
        from pg_diag.metric_engine import build_table_result

        name = '000000010000E67000000000'
        metric = {'table': {'mode': 'sample_sum', 'key_refs': ['id'], 'columns': [
            {'name': 'label', 'ref': 'label', 'transform': 'last', 'pg_type': 'text'},
            {'name': 'count', 'ref': 'label', 'transform': 'sample_count'},
        ]}}
        samples = [{'timestamp': timestamp, 'rows': [{'id': 1, 'label': name}]}
                   for timestamp in ['2026-09-23T13:20:00Z', '2026-09-23T13:26:00Z']]
        assert build_table_result(metric, samples, {})['rows'] == [[name, 2]]
    """)


def test_numeric_coercion_rejects_huge_exponents_without_expanding_them() -> None:
    _run_bounded("""
        from decimal import Decimal
        from pg_diag.metric_engine import _number_or_none, build_chart_result

        for value in ['1e67000000000', '-1e67000000000', '1e309',
                      Decimal('1e67000000000'), 'NaN', 'Infinity']:
            assert _number_or_none(value) is None, repr(value)
        for value, expected in [('9007199254740993', 9007199254740993),
                                ('1e3', 1000), ('1e308', 10**308),
                                ('-12.5', Decimal('-12.5'))]:
            assert _number_or_none(value) == expected
        chart = build_chart_result(
            {'series': [{'name': 'counter', 'value_ref': 'v', 'transform': 'delta'}]},
            [{'timestamp': '2026-09-23T13:20:00Z', 'rows': [{'v': '1'}]},
             {'timestamp': '2026-09-23T13:26:00Z', 'rows': [{'v': '1e67000000000'}]}],
            {},
        )
        assert chart['interval_coverage']['counts']['invalid_value'] == 1
    """)
