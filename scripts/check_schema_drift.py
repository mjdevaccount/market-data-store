"""Schema drift detection CLI for CI/CD integration.

Compares local schema snapshots against live Registry and emits telemetry
events when drift is detected.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from loguru import logger

from core_registry_client import RegistryClient
from market_data_store.pulse.config import PulseConfig
from market_data_store.telemetry.drift_reporter import DriftReporter, SchemaSnapshot


async def load_local_schemas(schema_dir: Path) -> list[SchemaSnapshot]:
    """Load local schema snapshots from fixtures directory.

    Args:
        schema_dir: Directory containing schema JSON files

    Returns:
        List of SchemaSnapshot objects
    """
    snapshots = []
    metadata_file = schema_dir / "_metadata.json"

    # Load metadata if available
    metadata = {}
    if metadata_file.exists():
        with open(metadata_file) as f:
            metadata = json.load(f)

    track = metadata.get("track", "v1")

    # Load each schema file
    for schema_file in schema_dir.glob("*.json"):
        if schema_file.name == "_metadata.json":
            continue

        with open(schema_file) as f:
            schema_content = json.load(f)

        # Compute hash
        reporter = DriftReporter()
        sha256 = reporter.compute_sha256(schema_content)

        # Extract schema name from filename
        schema_name = schema_file.stem

        snapshot = SchemaSnapshot(
            name=schema_name,
            track=track,
            sha256=sha256,
            version=metadata.get("version"),
            fetched_at=metadata.get("fetched_at"),
        )

        snapshots.append(snapshot)
        logger.info(f"Loaded local schema: {schema_name} ({sha256[:12]}...)")

    return snapshots


async def fetch_registry_schemas(
    registry_url: str, track: str, schema_names: list[str]
) -> dict[str, tuple[str, str]]:
    """Fetch schemas from Registry.

    Args:
        registry_url: Registry base URL
        track: Schema track (v1 or v2)
        schema_names: List of schema names to fetch

    Returns:
        Dict mapping schema name to (sha256, version) tuple
    """
    registry_schemas = {}

    async with RegistryClient(base_url=registry_url) as client:
        for name in schema_names:
            try:
                schema_obj = await client.get_schema(track, name)
                content = schema_obj.content

                # Compute hash
                reporter = DriftReporter()
                sha256 = reporter.compute_sha256(content)

                registry_schemas[name] = (sha256, schema_obj.version)
                logger.info(f"Fetched from Registry: {name} ({sha256[:12]}...)")

            except Exception as e:
                logger.warning(f"Failed to fetch {name} from Registry: {e}")

    return registry_schemas


async def check_drift(
    registry_url: str,
    track: str,
    schema_dir: Path,
    emit_telemetry: bool = False,
) -> dict:
    """Check for schema drift and optionally emit telemetry.

    Args:
        registry_url: Registry base URL
        track: Schema track to check
        schema_dir: Local schema directory
        emit_telemetry: Whether to emit Pulse events

    Returns:
        Drift report dict
    """
    logger.info(f"🔍 Checking schema drift for track: {track}")
    logger.info(f"📂 Local schemas: {schema_dir}")
    logger.info(f"📡 Registry: {registry_url}")

    # Load local schemas
    local_snapshots = await load_local_schemas(schema_dir)
    logger.info(f"✅ Loaded {len(local_snapshots)} local schemas")

    # Fetch Registry schemas
    schema_names = [s.name for s in local_snapshots]
    registry_schemas = await fetch_registry_schemas(registry_url, track, schema_names)
    logger.info(f"✅ Fetched {len(registry_schemas)} Registry schemas")

    # Initialize drift reporter
    pulse_config = PulseConfig() if emit_telemetry else PulseConfig(enabled=False)
    reporter = DriftReporter(pulse_config=pulse_config)

    if emit_telemetry:
        await reporter.start()

    # Check drift for each schema
    drift_results = []
    drift_count = 0

    for snapshot in local_snapshots:
        if snapshot.name not in registry_schemas:
            logger.warning(f"⚠️  Schema {snapshot.name} not found in Registry")
            drift_results.append(
                {
                    "schema": snapshot.name,
                    "status": "missing_in_registry",
                    "local_sha": snapshot.sha256,
                    "registry_sha": None,
                }
            )
            continue

        registry_sha, registry_version = registry_schemas[snapshot.name]

        drift_detected = await reporter.detect_and_emit_drift(
            snapshot, registry_sha, registry_version
        )

        status = "drift" if drift_detected else "synced"
        if drift_detected:
            drift_count += 1

        drift_results.append(
            {
                "schema": snapshot.name,
                "status": status,
                "local_sha": snapshot.sha256[:12],
                "local_version": snapshot.version,
                "registry_sha": registry_sha[:12],
                "registry_version": registry_version,
            }
        )

    if emit_telemetry:
        await reporter.stop()

    # Generate report
    report = {
        "track": track,
        "registry_url": registry_url,
        "total_schemas": len(local_snapshots),
        "synced": len(local_snapshots) - drift_count,
        "drifted": drift_count,
        "schemas": drift_results,
    }

    # Summary
    logger.info("=" * 60)
    logger.info("📊 Drift Check Summary:")
    logger.info(f"   Total schemas: {report['total_schemas']}")
    logger.info(f"   ✅ Synced: {report['synced']}")
    logger.info(f"   ⚠️  Drifted: {report['drifted']}")
    logger.info("=" * 60)

    if drift_count > 0:
        logger.warning(f"⚠️  {drift_count} schema(s) have drifted from Registry")
        for result in drift_results:
            if result["status"] == "drift":
                logger.warning(
                    f"   - {result['schema']}: "
                    f"local={result['local_sha']}... "
                    f"registry={result['registry_sha']}..."
                )

    return report


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Check schema drift against Registry")
    parser.add_argument(
        "--track",
        default="v1",
        help="Schema track to check (default: v1)",
    )
    parser.add_argument(
        "--registry-url",
        default="https://schema-registry-service.fly.dev",
        help="Registry base URL",
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=Path("tests/fixtures/schemas"),
        help="Local schema directory",
    )
    parser.add_argument(
        "--emit-telemetry",
        action="store_true",
        help="Emit Pulse telemetry events on drift",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("drift_report.json"),
        help="Output file for drift report JSON",
    )

    args = parser.parse_args()

    # Run drift check
    report = asyncio.run(
        check_drift(
            args.registry_url,
            args.track,
            args.schema_dir,
            args.emit_telemetry,
        )
    )

    # Save report
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"💾 Drift report saved to: {args.output}")

    # Exit with error code if drift detected (for CI)
    if report["drifted"] > 0:
        logger.warning("⚠️  Drift detected - exiting with status 1")
        sys.exit(1)

    logger.success("✅ All schemas synced - exiting with status 0")
    sys.exit(0)


if __name__ == "__main__":
    main()
