#!/usr/bin/env python3
"""
Fetch schemas from Schema Registry for CI/CD validation.

Usage:
    python scripts/fetch_registry_schemas.py --track v1 --output schemas/

Environment Variables:
    REGISTRY_URL: Registry base URL (default: https://schema-registry-service.fly.dev)
    REGISTRY_TRACK: Schema track to fetch (v1 or v2)
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

try:
    from core_registry_client import RegistryClient
except ImportError:
    print("❌ core-registry-client not installed")
    print(
        "   Install with: pip install git+https://github.com/mjdevaccount/schema-registry-service.git#subdirectory=client_sdk"
    )
    sys.exit(1)


# Schemas critical to Store
CRITICAL_SCHEMAS = [
    "telemetry.FeedbackEvent.schema",
    "telemetry.HealthStatus.schema",
    "telemetry.HealthComponent.schema",
]


async def fetch_schemas(
    track: str,
    output_dir: Path,
    registry_url: str,
    schema_names: list[str] | None = None,
) -> None:
    """Fetch schemas from Registry and save to local directory."""

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📡 Connecting to Registry: {registry_url}")
    print(f"🎯 Track: {track}")
    print(f"📂 Output: {output_dir}")
    print()

    async with RegistryClient(base_url=registry_url) as client:
        # Get index to see what's available
        try:
            index = await client.get_index()
            print(f"✅ Registry healthy: {len(index.tracks)} tracks available")
        except Exception as e:
            print(f"❌ Failed to fetch index: {e}")
            sys.exit(1)

        # Get schemas for this track
        track_data = index.tracks.get(track)
        if not track_data:
            print(f"❌ Track '{track}' not found in Registry")
            print(f"   Available tracks: {list(index.tracks.keys())}")
            sys.exit(1)

        available_schemas = [s.name for s in track_data.schemas]
        print(f"📋 {len(available_schemas)} schemas available in {track} track")
        print()

        # Determine which schemas to fetch
        if schema_names:
            to_fetch = schema_names
        else:
            to_fetch = CRITICAL_SCHEMAS

        # Fetch each schema
        fetched = 0
        failed = []

        for schema_name in to_fetch:
            try:
                # Remove .schema suffix if present
                clean_name = schema_name.replace(".schema", "")

                # Fetch schema
                schema = await client.fetch_schema(track=track, name=f"{clean_name}.schema")

                # Save to file
                output_file = output_dir / f"{clean_name}.json"
                with open(output_file, "w") as f:
                    json.dump(schema.content, f, indent=2)

                print(f"  ✅ {clean_name} @ {schema.core_version}")
                fetched += 1

            except Exception as e:
                print(f"  ❌ {schema_name}: {e}")
                failed.append(schema_name)

        print()
        print(f"📊 Results: {fetched} fetched, {len(failed)} failed")

        if failed:
            print(f"⚠️  Failed schemas: {', '.join(failed)}")
            # Don't exit with error - allow CI to continue

        # Save metadata
        meta_file = output_dir / "_metadata.json"
        with open(meta_file, "w") as f:
            json.dump(
                {
                    "registry_url": registry_url,
                    "track": track,
                    "fetched_at": index.generated_at.isoformat() if index.generated_at else None,
                    "schemas_fetched": fetched,
                    "schemas_failed": len(failed),
                    "failed_schemas": failed,
                },
                f,
                indent=2,
            )

        print(f"✅ Saved metadata to {meta_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch schemas from Schema Registry",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--track",
        required=True,
        choices=["v1", "v2"],
        help="Schema track to fetch",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("schemas"),
        help="Output directory for schemas (default: schemas/)",
    )
    parser.add_argument(
        "--registry-url",
        default=os.getenv("REGISTRY_URL", "https://schema-registry-service.fly.dev"),
        help="Registry base URL (default: env REGISTRY_URL or https://schema-registry-service.fly.dev)",
    )
    parser.add_argument(
        "--schemas",
        nargs="+",
        help=f"Specific schemas to fetch (default: {', '.join(CRITICAL_SCHEMAS)})",
    )

    args = parser.parse_args()

    try:
        asyncio.run(
            fetch_schemas(
                track=args.track,
                output_dir=args.output,
                registry_url=args.registry_url,
                schema_names=args.schemas,
            )
        )
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
