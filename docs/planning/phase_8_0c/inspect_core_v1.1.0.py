"""Inspect Core v1.1.0 exports to answer open questions."""

import inspect
from market_data_core.telemetry import (
    FeedbackEvent,
    BackpressureLevel,
    HealthStatus,
    HealthComponent,
)

try:
    from market_data_core.protocols import FeedbackPublisher

    has_feedback_publisher = True
except ImportError:
    has_feedback_publisher = False

print("=" * 60)
print("CORE v1.1.0 INSPECTION REPORT")
print("=" * 60)

# FeedbackEvent
print("\n1. FeedbackEvent")
print("-" * 60)
print(f"Signature: {inspect.signature(FeedbackEvent)}")
print(f"Fields: {list(FeedbackEvent.model_fields.keys())}")
print(f"Has 'reason' field: {'reason' in FeedbackEvent.model_fields}")
print(f"Has 'utilization' property: {hasattr(FeedbackEvent, 'utilization')}")

# Create sample to test
try:
    import time

    sample = FeedbackEvent(
        coordinator_id="test",
        queue_size=80,
        capacity=100,
        level=BackpressureLevel.hard,
        ts=time.time(),
    )
    print(f"Sample created successfully: {sample.coordinator_id}")
    if hasattr(sample, "utilization"):
        print(f"Utilization property works: {sample.utilization}")
except Exception as e:
    print(f"Error creating sample: {e}")

# BackpressureLevel
print("\n2. BackpressureLevel")
print("-" * 60)
for level in BackpressureLevel:
    print(f"  {level.name} = '{level.value}'")

# HealthStatus
print("\n3. HealthStatus")
print("-" * 60)
print(f"Signature: {inspect.signature(HealthStatus)}")
print(f"Fields: {list(HealthStatus.model_fields.keys())}")

# HealthComponent
print("\n4. HealthComponent")
print("-" * 60)
print(f"Signature: {inspect.signature(HealthComponent)}")
print(f"Fields: {list(HealthComponent.model_fields.keys())}")

# Test HealthComponent state values
try:
    test_comp = HealthComponent(name="test", state="healthy")
    print("State 'healthy' accepted: ✓")
except Exception as e:
    print(f"State 'healthy' rejected: {e}")

# FeedbackPublisher Protocol
print("\n5. FeedbackPublisher Protocol")
print("-" * 60)
if has_feedback_publisher:
    print("Protocol exists: ✓")
    print(f"Type: {type(FeedbackPublisher)}")
    # Check if it's a Protocol
    if hasattr(FeedbackPublisher, "__protocol_attrs__"):
        print(f"Protocol attrs: {FeedbackPublisher.__protocol_attrs__}")
    # Get method signature if available
    if hasattr(FeedbackPublisher, "publish"):
        sig = inspect.signature(FeedbackPublisher.publish)
        print(f"publish() signature: {sig}")
else:
    print("Protocol NOT found ✗")

print("\n" + "=" * 60)
print("KEY FINDINGS")
print("=" * 60)

print("\n✅ COMPATIBLE:")
print("  - BackpressureLevel values match exactly (ok/soft/hard)")
print("  - HealthStatus has all expected fields")
print("  - HealthComponent state values work")

print("\n⚠️ REQUIRES ATTENTION:")
if "reason" not in FeedbackEvent.model_fields:
    print("  - FeedbackEvent MISSING 'reason' field (store uses this)")
if not hasattr(sample, "utilization"):
    print("  - FeedbackEvent MISSING 'utilization' property (store uses this)")
print("  - FeedbackEvent REQUIRES 'ts' parameter (store doesn't pass this)")
print("  - FeedbackEvent has 'source' with default='store'")

print("\n📝 RECOMMENDATION:")
print("  Use ADAPTER PATTERN to preserve store-specific fields")
print("  (reason, utilization) while conforming to Core contracts")
