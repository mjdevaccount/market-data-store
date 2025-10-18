"""Telemetry module for schema drift detection and reporting."""

from .drift_reporter import DriftReporter, SchemaSnapshot

__all__ = ["DriftReporter", "SchemaSnapshot"]
