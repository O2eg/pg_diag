"""Generic execution of declaratively registered snapshot sampler providers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import importlib
import inspect
from pathlib import Path
from typing import Any

from .content_loader import ContentPack, resolve_under
from .errors import PgDiagError
from .host_access import HostAccess


SampleMap = dict[str, list[dict[str, Any]]]


@dataclass(frozen=True)
class SamplerProviderContext:
    content_path: Path
    host: HostAccess
    duration_seconds: float
    interval_seconds: float
    required_outputs: frozenset[str]
    manifest: dict[str, Any]


@dataclass(frozen=True)
class SamplerCollection:
    samples: SampleMap
    errors: list[dict[str, str]]


def sampler_output_registry(content: ContentPack) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    for provider_id, provider in content.sampler_providers.items():
        for output_id, output in provider["outputs"].items():
            normalized_id = str(output_id)
            if normalized_id in registry:
                raise PgDiagError(f"sampler output {normalized_id!r} is declared more than once")
            registry[normalized_id] = {
                **dict(output),
                "provider_id": provider_id,
            }
    return registry


def sampler_source_metadata(
    content: ContentPack,
    output_registry: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    scripts_root = content.path / "scripts"
    for output_id, output in output_registry.items():
        source_file = output["source_file"]
        source_path = resolve_under(scripts_root, source_file, "Sampler source file")
        try:
            source_text = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise PgDiagError(f"cannot read sampler source {source_file}: {exc}") from exc
        metadata[output_id] = {
            **output,
            "source_text": source_text,
        }
    return metadata


async def collect_sampler_providers(
    content: ContentPack,
    host: HostAccess,
    duration_seconds: float,
    interval_seconds: float,
    required_outputs: set[str],
) -> SamplerCollection:
    declared_outputs = set(sampler_output_registry(content))
    unknown_outputs = required_outputs.difference(declared_outputs)
    if unknown_outputs:
        raise PgDiagError(
            "required sampler outputs are not declared: "
            + ", ".join(sorted(unknown_outputs))
        )
    tasks: list[tuple[str, frozenset[str], asyncio.Task[SamplerCollection]]] = []
    for provider_id, manifest in content.sampler_providers.items():
        declared_outputs = frozenset(str(value) for value in manifest["outputs"])
        selected_outputs = declared_outputs.intersection(required_outputs)
        if not selected_outputs:
            continue
        context = SamplerProviderContext(
            content_path=content.path,
            host=host,
            duration_seconds=float(duration_seconds),
            interval_seconds=float(interval_seconds),
            required_outputs=selected_outputs,
            manifest=manifest,
        )
        task = asyncio.create_task(
            _run_provider(provider_id, context),
            name=f"sampler-provider:{provider_id}",
        )
        tasks.append((provider_id, selected_outputs, task))

    samples: SampleMap = {}
    errors: list[dict[str, str]] = []
    try:
        results = await asyncio.gather(
            *(task for _provider_id, _outputs, task in tasks),
            return_exceptions=True,
        )
    except BaseException:
        for _provider_id, _outputs, task in tasks:
            task.cancel()
        await asyncio.gather(
            *(task for _provider_id, _outputs, task in tasks),
            return_exceptions=True,
        )
        raise

    for (provider_id, selected_outputs, _task), result in zip(tasks, results):
        if isinstance(result, BaseException):
            errors.extend(
                {"sampler": output_id, "message": f"provider {provider_id}: {result}"}
                for output_id in sorted(selected_outputs)
            )
            continue
        for output_id, output_samples in result.samples.items():
            if output_id in selected_outputs:
                samples[output_id] = output_samples
        errors.extend(
            error for error in result.errors if error["sampler"] in selected_outputs
        )
        failed_outputs = {error["sampler"] for error in result.errors}
        for output_id in sorted(selected_outputs):
            if output_id not in result.samples and output_id not in failed_outputs:
                errors.append(
                    {
                        "sampler": output_id,
                        "message": f"provider {provider_id} returned no result for {output_id}",
                    }
                )
    return SamplerCollection(samples=samples, errors=errors)


async def _run_provider(
    provider_id: str,
    context: SamplerProviderContext,
) -> SamplerCollection:
    manifest = context.manifest
    module_name = str(manifest["module"])
    function_name = str(manifest["function"])
    try:
        module = importlib.import_module(module_name)
        function = getattr(module, function_name)
    except (ImportError, AttributeError) as exc:
        raise PgDiagError(
            f"cannot load sampler provider {provider_id} from {module_name}.{function_name}: {exc}"
        ) from exc
    if not inspect.iscoroutinefunction(function):
        raise PgDiagError(f"sampler provider {provider_id} must be async")

    grace_seconds = float(manifest["grace_timeout_ms"]) / 1000.0
    try:
        raw_result = await asyncio.wait_for(
            function(context),
            timeout=context.duration_seconds + grace_seconds,
        )
    except TimeoutError as exc:
        raise PgDiagError(
            f"sampler provider {provider_id} exceeded its collection window"
        ) from exc
    return _normalize_provider_result(provider_id, context, raw_result)


def _normalize_provider_result(
    provider_id: str,
    context: SamplerProviderContext,
    raw_result: Any,
) -> SamplerCollection:
    if isinstance(raw_result, SamplerCollection):
        result = raw_result
    elif isinstance(raw_result, dict):
        result = SamplerCollection(
            samples=dict(raw_result["samples"]),
            errors=list(raw_result["errors"]),
        )
    else:
        raise PgDiagError(f"sampler provider {provider_id} returned an invalid result")

    declared_outputs = set(context.manifest["outputs"])
    unknown_outputs = set(result.samples).difference(declared_outputs)
    normalized_errors: list[dict[str, str]] = []
    for error in result.errors:
        if not isinstance(error, dict):
            raise PgDiagError(f"sampler provider {provider_id} returned an invalid error")
        output_id = str(error.get("sampler") or "")
        if output_id not in declared_outputs:
            unknown_outputs.add(output_id or "<empty>")
        normalized_errors.append(
            {"sampler": output_id, "message": str(error.get("message") or "sampler failed")}
        )
    if unknown_outputs:
        raise PgDiagError(
            f"sampler provider {provider_id} returned undeclared outputs: "
            + ", ".join(sorted(unknown_outputs))
        )

    normalized_samples = {
        output_id: _normalize_samples(provider_id, output_id, samples)
        for output_id, samples in result.samples.items()
    }
    return SamplerCollection(samples=normalized_samples, errors=normalized_errors)


def _normalize_samples(
    provider_id: str,
    output_id: str,
    samples: Any,
) -> list[dict[str, Any]]:
    if not isinstance(samples, list):
        raise PgDiagError(
            f"sampler provider {provider_id} output {output_id} must be a sample list"
        )
    normalized: list[dict[str, Any]] = []
    for sample in samples:
        if not isinstance(sample, dict) or not isinstance(sample.get("timestamp"), str):
            raise PgDiagError(
                f"sampler provider {provider_id} output {output_id} has an invalid timestamp"
            )
        if not isinstance(sample.get("rows"), list):
            raise PgDiagError(
                f"sampler provider {provider_id} output {output_id} has invalid rows"
            )
        normalized.append({"timestamp": sample["timestamp"], "rows": sample["rows"]})
    return normalized
