"""Compatibility re-exports for parser reports."""

from __future__ import annotations

from .base import (  # noqa: F401
    ADAPTER_SCHEMA_VERSION,
    PARSER_VERSION,
    ParserReport,
    build_parser_report,
    create_parser_report,
    load_parser_reports,
    make_parser_report,
    parse_report,
    write_parser_reports,
)

__all__ = [
    "ADAPTER_SCHEMA_VERSION",
    "PARSER_VERSION",
    "ParserReport",
    "build_parser_report",
    "create_parser_report",
    "load_parser_reports",
    "make_parser_report",
    "parse_report",
    "write_parser_reports",
]
