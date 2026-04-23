# -*- coding: utf-8 -*-
"""
Comprehensive tests for chuk_artifacts.models module.

Tests cover:
- ArtifactEnvelope model validation
- Field defaults and types
- Pydantic configuration behavior
- Serialization and deserialization
- Edge cases and error conditions
- Extra fields handling
"""

import pytest
import json
from pydantic import ValidationError

from chuk_artifacts.models import (
    ArtifactEnvelope,
    ArtifactMetadata,
    GridKeyComponents,
    BatchStoreItem,
)


class TestArtifactEnvelopeBasics:
    """Test basic ArtifactEnvelope functionality."""

    def test_minimal_creation(self):
        """Test creating ArtifactEnvelope with minimal required fields."""
        envelope = ArtifactEnvelope(
            artifact_id="abc123",
            mime_type="text/plain",
            bytes=1024,
            summary="Test artifact",
        )

        assert envelope.success is True  # Default value
        assert envelope.artifact_id == "abc123"
        assert envelope.mime_type == "text/plain"
        assert envelope.bytes == 1024
        assert envelope.summary == "Test artifact"
        assert envelope.meta == {}  # Default empty dict

    def test_full_creation(self):
        """Test creating ArtifactEnvelope with all fields."""
        meta_data = {"category": "test", "version": 1, "tags": ["important"]}

        envelope = ArtifactEnvelope(
            success=False,
            artifact_id="xyz789",
            mime_type="application/json",
            bytes=2048,
            summary="Complex test artifact",
            meta=meta_data,
        )

        assert envelope.success is False
        assert envelope.artifact_id == "xyz789"
        assert envelope.mime_type == "application/json"
        assert envelope.bytes == 2048
        assert envelope.summary == "Complex test artifact"
        assert envelope.meta == meta_data

    def test_default_values(self):
        """Test that default values are applied correctly."""
        envelope = ArtifactEnvelope(
            artifact_id="test123", mime_type="text/plain", bytes=512, summary="Test"
        )

        # Test defaults
        assert envelope.success is True
        assert isinstance(envelope.meta, dict)
        assert len(envelope.meta) == 0

    def test_field_types(self):
        """Test that fields have correct types."""
        envelope = ArtifactEnvelope(
            artifact_id="test123", mime_type="text/plain", bytes=512, summary="Test"
        )

        assert isinstance(envelope.success, bool)
        assert isinstance(envelope.artifact_id, str)
        assert isinstance(envelope.mime_type, str)
        assert isinstance(envelope.bytes, int)
        assert isinstance(envelope.summary, str)
        assert isinstance(envelope.meta, dict)


class TestArtifactEnvelopeValidation:
    """Test validation behavior of ArtifactEnvelope."""

    def test_required_fields_missing(self):
        """Test that missing required fields raise validation errors."""
        # Missing artifact_id
        with pytest.raises(ValidationError) as exc_info:
            ArtifactEnvelope(mime_type="text/plain", bytes=512, summary="Test")
        assert "artifact_id" in str(exc_info.value)

        # Missing mime_type
        with pytest.raises(ValidationError) as exc_info:
            ArtifactEnvelope(artifact_id="test123", bytes=512, summary="Test")
        assert "mime_type" in str(exc_info.value)

        # Missing bytes
        with pytest.raises(ValidationError) as exc_info:
            ArtifactEnvelope(
                artifact_id="test123", mime_type="text/plain", summary="Test"
            )
        assert "bytes" in str(exc_info.value)

        # Missing summary
        with pytest.raises(ValidationError) as exc_info:
            ArtifactEnvelope(artifact_id="test123", mime_type="text/plain", bytes=512)
        assert "summary" in str(exc_info.value)

    def test_invalid_field_types(self):
        """Test validation with invalid field types."""
        # Note: Pydantic V2 is more permissive with type coercion
        # String "true" gets coerced to True, "512" gets coerced to 512

        # Invalid meta type (should be dict-like) - this should still fail
        with pytest.raises(ValidationError) as exc_info:
            ArtifactEnvelope(
                artifact_id="test123",
                mime_type="text/plain",
                bytes=512,
                summary="Test",
                meta="not a dict",  # Should be dict
            )
        assert "meta" in str(exc_info.value)

        # Test with completely invalid types that can't be coerced
        with pytest.raises(ValidationError) as exc_info:
            ArtifactEnvelope(
                artifact_id="test123",
                mime_type="text/plain",
                bytes={"not": "an_int"},  # Dict can't be coerced to int
                summary="Test",
            )
        assert "bytes" in str(exc_info.value)

    def test_type_coercion(self):
        """Test Pydantic's type coercion behavior."""
        # Pydantic V2 is more aggressive with type coercion
        envelope = ArtifactEnvelope(
            success="true",  # Should coerce to True
            artifact_id="test123",
            mime_type="text/plain",
            bytes="512",  # Should coerce to int
            summary="Test",
        )

        assert envelope.success is True
        assert envelope.bytes == 512
        assert isinstance(envelope.bytes, int)

        # Test more coercion examples
        envelope2 = ArtifactEnvelope(
            success=1,  # Should coerce to True
            artifact_id="test456",
            mime_type="application/json",
            bytes=1024.0,  # Float should coerce to int
            summary="Another test",
        )

        assert envelope2.success is True
        assert envelope2.bytes == 1024
        assert isinstance(envelope2.bytes, int)

    def test_negative_bytes(self):
        """Test validation with negative bytes value."""
        # Pydantic allows negative numbers by default
        envelope = ArtifactEnvelope(
            artifact_id="test123",
            mime_type="text/plain",
            bytes=-512,  # Negative bytes - technically valid but unusual
            summary="Test",
        )

        assert envelope.bytes == -512

    def test_zero_bytes(self):
        """Test validation with zero bytes value."""
        envelope = ArtifactEnvelope(
            artifact_id="test123",
            mime_type="text/plain",
            bytes=0,  # Zero bytes - valid for empty files
            summary="Empty file",
        )

        assert envelope.bytes == 0

    def test_large_bytes_value(self):
        """Test validation with very large bytes value."""
        large_size = 10**15  # 1 petabyte

        envelope = ArtifactEnvelope(
            artifact_id="test123",
            mime_type="application/octet-stream",
            bytes=large_size,
            summary="Very large file",
        )

        assert envelope.bytes == large_size


class TestArtifactEnvelopeMetadata:
    """Test metadata field behavior."""

    def test_empty_meta_default(self):
        """Test that meta defaults to empty dict."""
        envelope = ArtifactEnvelope(
            artifact_id="test123", mime_type="text/plain", bytes=512, summary="Test"
        )

        assert envelope.meta == {}
        assert isinstance(envelope.meta, dict)

    def test_simple_meta(self):
        """Test simple metadata values."""
        meta = {"author": "John Doe", "version": "1.0", "category": "document"}

        envelope = ArtifactEnvelope(
            artifact_id="test123",
            mime_type="text/plain",
            bytes=512,
            summary="Test",
            meta=meta,
        )

        assert envelope.meta == meta
        assert envelope.meta["author"] == "John Doe"
        assert envelope.meta["version"] == "1.0"
        assert envelope.meta["category"] == "document"

    def test_complex_meta(self):
        """Test complex metadata with nested structures."""
        meta = {
            "author": {
                "name": "John Doe",
                "email": "john@example.com",
                "department": "Engineering",
            },
            "tags": ["important", "urgent", "review"],
            "metrics": {"lines": 1500, "functions": 25, "complexity": 7.5},
            "timestamps": {
                "created": "2025-01-01T00:00:00Z",
                "modified": "2025-01-02T12:00:00Z",
            },
        }

        envelope = ArtifactEnvelope(
            artifact_id="test123",
            mime_type="application/python",
            bytes=15000,
            summary="Python source code",
            meta=meta,
        )

        assert envelope.meta == meta
        assert envelope.meta["author"]["name"] == "John Doe"
        assert envelope.meta["tags"] == ["important", "urgent", "review"]
        assert envelope.meta["metrics"]["complexity"] == 7.5

    def test_meta_with_none_values(self):
        """Test metadata with None values."""
        meta = {
            "optional_field": None,
            "present_field": "value",
            "empty_list": [],
            "empty_dict": {},
        }

        envelope = ArtifactEnvelope(
            artifact_id="test123",
            mime_type="text/plain",
            bytes=512,
            summary="Test",
            meta=meta,
        )

        assert envelope.meta["optional_field"] is None
        assert envelope.meta["present_field"] == "value"
        assert envelope.meta["empty_list"] == []
        assert envelope.meta["empty_dict"] == {}


class TestArtifactEnvelopeExtraFields:
    """Test extra fields handling due to Config.extra = 'allow'."""

    def test_extra_fields_allowed(self):
        """Test that extra fields are allowed and preserved."""
        envelope = ArtifactEnvelope(
            artifact_id="test123",
            mime_type="text/plain",
            bytes=512,
            summary="Test",
            # Extra fields not in the model
            custom_field="custom_value",
            another_field=42,
            complex_extra={"nested": True, "data": ["a", "b", "c"]},
        )

        # Standard fields work
        assert envelope.artifact_id == "test123"
        assert envelope.mime_type == "text/plain"

        # Extra fields are preserved
        assert envelope.custom_field == "custom_value"
        assert envelope.another_field == 42
        assert envelope.complex_extra["nested"] is True
        assert envelope.complex_extra["data"] == ["a", "b", "c"]

    def test_extra_fields_in_dict(self):
        """Test that extra fields appear in dict representation."""
        envelope = ArtifactEnvelope(
            artifact_id="test123",
            mime_type="text/plain",
            bytes=512,
            summary="Test",
            extra_info="additional data",
        )

        # Use Pydantic V2 method
        envelope_dict = envelope.model_dump()
        assert "extra_info" in envelope_dict
        assert envelope_dict["extra_info"] == "additional data"

    def test_extra_fields_in_json(self):
        """Test that extra fields appear in JSON serialization."""
        envelope = ArtifactEnvelope(
            artifact_id="test123",
            mime_type="text/plain",
            bytes=512,
            summary="Test",
            tool_specific={"feature": "enabled", "version": 2},
        )

        # Use Pydantic V2 method
        json_str = envelope.model_dump_json()
        parsed = json.loads(json_str)

        assert "tool_specific" in parsed
        assert parsed["tool_specific"]["feature"] == "enabled"
        assert parsed["tool_specific"]["version"] == 2


class TestArtifactEnvelopeSerialization:
    """Test serialization and deserialization."""

    def test_dict_serialization(self):
        """Test conversion to dictionary."""
        envelope = ArtifactEnvelope(
            success=True,
            artifact_id="test123",
            mime_type="application/json",
            bytes=2048,
            summary="JSON data",
            meta={"format": "json", "version": 1},
        )

        # Use Pydantic V2 method
        envelope_dict = envelope.model_dump()

        expected = {
            "success": True,
            "artifact_id": "test123",
            "mime_type": "application/json",
            "bytes": 2048,
            "summary": "JSON data",
            "meta": {"format": "json", "version": 1},
        }

        assert envelope_dict == expected

    def test_json_serialization(self):
        """Test JSON serialization."""
        envelope = ArtifactEnvelope(
            artifact_id="test123",
            mime_type="text/plain",
            bytes=512,
            summary="Test file",
            meta={"encoding": "utf-8"},
        )

        # Use Pydantic V2 method
        json_str = envelope.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["artifact_id"] == "test123"
        assert parsed["mime_type"] == "text/plain"
        assert parsed["bytes"] == 512
        assert parsed["summary"] == "Test file"
        assert parsed["meta"]["encoding"] == "utf-8"
        assert parsed["success"] is True  # Default value

    def test_json_deserialization(self):
        """Test creating envelope from JSON."""
        json_data = {
            "success": False,
            "artifact_id": "json123",
            "mime_type": "application/xml",
            "bytes": 4096,
            "summary": "XML document",
            "meta": {"schema": "custom", "valid": True},
        }

        envelope = ArtifactEnvelope(**json_data)

        assert envelope.success is False
        assert envelope.artifact_id == "json123"
        assert envelope.mime_type == "application/xml"
        assert envelope.bytes == 4096
        assert envelope.summary == "XML document"
        assert envelope.meta["schema"] == "custom"
        assert envelope.meta["valid"] is True

    def test_round_trip_serialization(self):
        """Test that serialization and deserialization preserve data."""
        original = ArtifactEnvelope(
            success=True,
            artifact_id="roundtrip123",
            mime_type="image/png",
            bytes=51200,
            summary="PNG image",
            meta={
                "width": 800,
                "height": 600,
                "channels": 4,
                "metadata": {
                    "camera": "Canon EOS",
                    "timestamp": "2025-01-01T12:00:00Z",
                },
            },
        )

        # Serialize to JSON and back using Pydantic V2 methods
        json_str = original.model_dump_json()
        parsed_dict = json.loads(json_str)
        reconstructed = ArtifactEnvelope(**parsed_dict)

        assert reconstructed == original
        assert reconstructed.model_dump() == original.model_dump()


class TestArtifactEnvelopeSpecialCases:
    """Test special cases and edge conditions."""

    def test_unicode_content(self):
        """Test handling of Unicode content."""
        envelope = ArtifactEnvelope(
            artifact_id="unicode_test_🎉",
            mime_type="text/plain; charset=utf-8",
            bytes=1024,
            summary="Unicode test file: 世界 🌍 café résumé",
            meta={
                "description": "Contains émojis 🚀 and spéciâl chàractérs",
                "tags": ["tëst", "üñïcodé", "🏷️"],
            },
        )

        assert envelope.artifact_id == "unicode_test_🎉"
        assert "世界" in envelope.summary
        assert "🚀" in envelope.meta["description"]
        assert "🏷️" in envelope.meta["tags"]

        # Should serialize/deserialize correctly using Pydantic V2 methods
        json_str = envelope.model_dump_json()
        parsed = json.loads(json_str)
        reconstructed = ArtifactEnvelope(**parsed)

        assert reconstructed.artifact_id == envelope.artifact_id
        assert reconstructed.summary == envelope.summary
        assert reconstructed.meta == envelope.meta

    def test_empty_strings(self):
        """Test handling of empty string values."""
        envelope = ArtifactEnvelope(
            artifact_id="",  # Empty artifact ID
            mime_type="",  # Empty MIME type
            bytes=0,
            summary="",  # Empty summary
            meta={},
        )

        assert envelope.artifact_id == ""
        assert envelope.mime_type == ""
        assert envelope.bytes == 0
        assert envelope.summary == ""
        assert envelope.meta == {}

    def test_very_long_strings(self):
        """Test handling of very long string values."""
        long_id = "a" * 10000
        long_summary = "Very long summary: " + "x" * 50000

        envelope = ArtifactEnvelope(
            artifact_id=long_id,
            mime_type="text/plain",
            bytes=len(long_summary),
            summary=long_summary,
            meta={"note": "This is a very long artifact description"},
        )

        assert len(envelope.artifact_id) == 10000
        assert len(envelope.summary) > 50000
        assert envelope.bytes == len(long_summary)

    def test_special_mime_types(self):
        """Test various MIME type formats."""
        mime_types = [
            "text/plain",
            "application/json",
            "image/jpeg",
            "video/mp4",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/plain; charset=utf-8",
            "multipart/form-data; boundary=something",
            "application/octet-stream",
            "",  # Empty MIME type
            "custom/x-proprietary-format",
        ]

        for mime_type in mime_types:
            envelope = ArtifactEnvelope(
                artifact_id=f"test_{mime_type.replace('/', '_').replace(';', '_')}",
                mime_type=mime_type,
                bytes=1024,
                summary=f"Test for MIME type: {mime_type}",
            )

            assert envelope.mime_type == mime_type


class TestArtifactEnvelopeComparison:
    """Test equality and comparison behavior."""

    def test_equality(self):
        """Test that identical envelopes are equal."""
        envelope1 = ArtifactEnvelope(
            artifact_id="test123",
            mime_type="text/plain",
            bytes=512,
            summary="Test",
            meta={"key": "value"},
        )

        envelope2 = ArtifactEnvelope(
            artifact_id="test123",
            mime_type="text/plain",
            bytes=512,
            summary="Test",
            meta={"key": "value"},
        )

        assert envelope1 == envelope2

    def test_inequality_different_fields(self):
        """Test that envelopes with different fields are not equal."""
        base_envelope = ArtifactEnvelope(
            artifact_id="test123", mime_type="text/plain", bytes=512, summary="Test"
        )

        # Different artifact_id
        different_id = ArtifactEnvelope(
            artifact_id="different123",
            mime_type="text/plain",
            bytes=512,
            summary="Test",
        )
        assert base_envelope != different_id

        # Different bytes
        different_bytes = ArtifactEnvelope(
            artifact_id="test123", mime_type="text/plain", bytes=1024, summary="Test"
        )
        assert base_envelope != different_bytes

        # Different meta
        different_meta = ArtifactEnvelope(
            artifact_id="test123",
            mime_type="text/plain",
            bytes=512,
            summary="Test",
            meta={"different": "value"},
        )
        assert base_envelope != different_meta

    def test_inequality_extra_fields(self):
        """Test that extra fields affect equality."""
        envelope1 = ArtifactEnvelope(
            artifact_id="test123", mime_type="text/plain", bytes=512, summary="Test"
        )

        envelope2 = ArtifactEnvelope(
            artifact_id="test123",
            mime_type="text/plain",
            bytes=512,
            summary="Test",
            extra_field="extra_value",
        )

        assert envelope1 != envelope2


class TestArtifactEnvelopeUseCases:
    """Test realistic usage scenarios."""

    def test_image_artifact(self):
        """Test envelope for image artifact."""
        envelope = ArtifactEnvelope(
            success=True,
            artifact_id="img_20250101_photo001",
            mime_type="image/jpeg",
            bytes=2048000,  # ~2MB
            summary="Family vacation photo from beach",
            meta={
                "width": 4032,
                "height": 3024,
                "camera": {
                    "make": "Apple",
                    "model": "iPhone 14 Pro",
                    "iso": 64,
                    "aperture": "f/1.78",
                    "shutter_speed": "1/2000",
                },
                "location": {
                    "latitude": 25.7617,
                    "longitude": -80.1918,
                    "city": "Miami Beach",
                },
                "timestamp": "2025-01-01T15:30:00Z",
                "tags": ["family", "vacation", "beach", "sunset"],
            },
        )

        assert envelope.mime_type == "image/jpeg"
        assert envelope.bytes == 2048000
        assert envelope.meta["width"] == 4032
        assert envelope.meta["camera"]["make"] == "Apple"
        assert "beach" in envelope.meta["tags"]

    def test_document_artifact(self):
        """Test envelope for document artifact."""
        envelope = ArtifactEnvelope(
            artifact_id="doc_research_paper_v3",
            mime_type="application/pdf",
            bytes=1536000,  # ~1.5MB
            summary="Research Paper: Machine Learning in Healthcare",
            meta={
                "title": "Applications of Machine Learning in Healthcare Diagnostics",
                "authors": ["Dr. Jane Smith", "Prof. John Doe", "Dr. Alice Johnson"],
                "journal": "Journal of Medical AI",
                "publication_date": "2025-01-15",
                "doi": "10.1000/journal.2025.001",
                "keywords": ["machine learning", "healthcare", "diagnostics", "AI"],
                "page_count": 24,
                "version": "3.0",
                "review_status": "peer_reviewed",
            },
        )

        assert envelope.mime_type == "application/pdf"
        assert len(envelope.meta["authors"]) == 3
        assert envelope.meta["page_count"] == 24
        assert "machine learning" in envelope.meta["keywords"]

    def test_data_artifact(self):
        """Test envelope for data file artifact."""
        envelope = ArtifactEnvelope(
            artifact_id="data_sales_q4_2024",
            mime_type="text/csv",
            bytes=5242880,  # 5MB
            summary="Q4 2024 Sales Data - All Regions",
            meta={
                "schema": {
                    "columns": [
                        {"name": "date", "type": "datetime"},
                        {"name": "region", "type": "string"},
                        {"name": "product", "type": "string"},
                        {"name": "sales_amount", "type": "decimal"},
                        {"name": "customer_id", "type": "integer"},
                    ]
                },
                "row_count": 125000,
                "date_range": {"start": "2024-10-01", "end": "2024-12-31"},
                "regions": ["North", "South", "East", "West"],
                "currency": "USD",
                "last_updated": "2025-01-02T09:00:00Z",
                "quality_score": 0.97,
            },
        )

        assert envelope.mime_type == "text/csv"
        assert envelope.meta["row_count"] == 125000
        assert len(envelope.meta["regions"]) == 4
        assert envelope.meta["quality_score"] == 0.97

    def test_error_artifact(self):
        """Test envelope for failed operation."""
        envelope = ArtifactEnvelope(
            success=False,
            artifact_id="",  # No artifact created
            mime_type="",
            bytes=0,
            summary="Failed to process uploaded file",
            meta={
                "error": {
                    "code": "INVALID_FORMAT",
                    "message": "Unsupported file format: .xyz",
                    "timestamp": "2025-01-01T10:30:00Z",
                },
                "original_filename": "document.xyz",
                "attempted_mime_type": "application/octet-stream",
                "file_size": 1024000,
                "retry_count": 3,
            },
        )

        assert envelope.success is False
        assert envelope.artifact_id == ""
        assert envelope.meta["error"]["code"] == "INVALID_FORMAT"
        assert envelope.meta["retry_count"] == 3


# ============================================================================
# ArtifactMetadata Tests
# ============================================================================


class TestArtifactMetadataBasics:
    """Test basic ArtifactMetadata functionality."""

    def test_minimal_creation(self):
        """Test creating ArtifactMetadata with required fields."""
        metadata = ArtifactMetadata(
            artifact_id="test123",
            session_id="session456",
            sandbox_id="sandbox789",
            key="grid/sandbox789/session456/test123",
            mime="text/plain",
            summary="Test artifact",
            bytes=1024,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )

        assert metadata.artifact_id == "test123"
        assert metadata.session_id == "session456"
        assert metadata.bytes == 1024
        assert metadata.ttl == 900
        assert metadata.meta == {}

    def test_with_optional_fields(self):
        """Test creating ArtifactMetadata with optional fields."""
        metadata = ArtifactMetadata(
            artifact_id="test123",
            session_id="session456",
            sandbox_id="sandbox789",
            key="grid/sandbox789/session456/test123",
            mime="image/jpeg",
            summary="Image",
            bytes=2048,
            stored_at="2025-01-01T00:00:00Z",
            ttl=3600,
            storage_provider="s3",
            session_provider="redis",
            filename="photo.jpg",
            sha256="abc123",
            batch_operation=True,
            batch_index=5,
            uploaded_via_presigned=True,
            updated_at="2025-01-02T00:00:00Z",
            meta={"custom": "data"},
        )

        assert metadata.filename == "photo.jpg"
        assert metadata.sha256 == "abc123"
        assert metadata.batch_operation is True
        assert metadata.batch_index == 5
        assert metadata.uploaded_via_presigned is True
        assert metadata.updated_at == "2025-01-02T00:00:00Z"
        assert metadata.meta["custom"] == "data"


class TestArtifactMetadataValidation:
    """Test ArtifactMetadata validation."""

    def test_negative_bytes_rejected(self):
        """Test that negative bytes values are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ArtifactMetadata(
                artifact_id="test123",
                session_id="session456",
                sandbox_id="sandbox789",
                key="grid/test",
                mime="text/plain",
                summary="Test",
                bytes=-1,  # Invalid
                stored_at="2025-01-01T00:00:00Z",
                ttl=900,
                storage_provider="memory",
                session_provider="memory",
            )

        # Pydantic Field constraint catches this first
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_zero_ttl_rejected(self):
        """Test that zero TTL is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ArtifactMetadata(
                artifact_id="test123",
                session_id="session456",
                sandbox_id="sandbox789",
                key="grid/test",
                mime="text/plain",
                summary="Test",
                bytes=100,
                stored_at="2025-01-01T00:00:00Z",
                ttl=0,  # Invalid
                storage_provider="memory",
                session_provider="memory",
            )

        # Pydantic Field constraint catches this
        assert "greater than 0" in str(exc_info.value)

    def test_negative_ttl_rejected(self):
        """Test that negative TTL is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ArtifactMetadata(
                artifact_id="test123",
                session_id="session456",
                sandbox_id="sandbox789",
                key="grid/test",
                mime="text/plain",
                summary="Test",
                bytes=100,
                stored_at="2025-01-01T00:00:00Z",
                ttl=-100,  # Invalid
                storage_provider="memory",
                session_provider="memory",
            )

        # Pydantic Field constraint catches this
        assert "greater than 0" in str(exc_info.value)


class TestArtifactMetadataDictAccess:
    """Test backwards-compatible dict-like access for ArtifactMetadata."""

    def test_getitem_attribute_access(self):
        """Test __getitem__ for regular attributes (deprecated API)."""
        metadata = ArtifactMetadata(
            artifact_id="test123",
            session_id="session456",
            sandbox_id="sandbox789",
            key="grid/test",
            mime="text/plain",
            summary="Test",
            bytes=100,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )

        with pytest.warns(DeprecationWarning):
            assert metadata["artifact_id"] == "test123"
            assert metadata["session_id"] == "session456"
            assert metadata["bytes"] == 100
            assert metadata["mime"] == "text/plain"

    def test_getitem_extra_fields(self):
        """Test __getitem__ for extra fields."""
        # Create with extra field via model_validate
        data = {
            "artifact_id": "test123",
            "session_id": "session456",
            "sandbox_id": "sandbox789",
            "key": "grid/test",
            "mime": "text/plain",
            "summary": "Test",
            "bytes": 100,
            "stored_at": "2025-01-01T00:00:00Z",
            "ttl": 900,
            "storage_provider": "memory",
            "session_provider": "memory",
            "custom_field": "custom_value",  # Extra field
        }
        metadata = ArtifactMetadata.model_validate(data)

        with pytest.warns(DeprecationWarning):
            assert metadata["custom_field"] == "custom_value"

    def test_getitem_missing_key(self):
        """Test __getitem__ raises KeyError for missing keys."""
        metadata = ArtifactMetadata(
            artifact_id="test123",
            session_id="session456",
            sandbox_id="sandbox789",
            key="grid/test",
            mime="text/plain",
            summary="Test",
            bytes=100,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )

        with pytest.warns(DeprecationWarning):
            with pytest.raises(KeyError):
                _ = metadata["nonexistent_field"]

    def test_get_method(self):
        """Test get() method returns value or default."""
        metadata = ArtifactMetadata(
            artifact_id="test123",
            session_id="session456",
            sandbox_id="sandbox789",
            key="grid/test",
            mime="text/plain",
            summary="Test",
            bytes=100,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )

        with pytest.warns(DeprecationWarning):
            assert metadata.get("artifact_id") == "test123"
            assert metadata.get("nonexistent") is None
            assert metadata.get("nonexistent", "default") == "default"

    def test_keys_method(self):
        """Test keys() method returns all field names."""
        metadata = ArtifactMetadata(
            artifact_id="test123",
            session_id="session456",
            sandbox_id="sandbox789",
            key="grid/test",
            mime="text/plain",
            summary="Test",
            bytes=100,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )

        with pytest.warns(DeprecationWarning):
            keys = metadata.keys()
            assert "artifact_id" in keys
            assert "session_id" in keys
            assert "bytes" in keys

    def test_values_method(self):
        """Test values() method returns all field values."""
        metadata = ArtifactMetadata(
            artifact_id="test123",
            session_id="session456",
            sandbox_id="sandbox789",
            key="grid/test",
            mime="text/plain",
            summary="Test",
            bytes=100,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )

        with pytest.warns(DeprecationWarning):
            values = list(metadata.values())
            assert "test123" in values
            assert "session456" in values
            assert 100 in values

    def test_items_method(self):
        """Test items() method returns key-value pairs."""
        metadata = ArtifactMetadata(
            artifact_id="test123",
            session_id="session456",
            sandbox_id="sandbox789",
            key="grid/test",
            mime="text/plain",
            summary="Test",
            bytes=100,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )

        with pytest.warns(DeprecationWarning):
            items = dict(metadata.items())
        assert items["artifact_id"] == "test123"
        assert items["session_id"] == "session456"
        assert items["bytes"] == 100


# ============================================================================
# GridKeyComponents Tests
# ============================================================================


class TestGridKeyComponentsBasics:
    """Test basic GridKeyComponents functionality."""

    def test_minimal_creation(self):
        """Test creating GridKeyComponents with required fields."""
        components = GridKeyComponents(
            sandbox_id="sandbox123",
            session_id="session456",
            artifact_id="artifact789",
        )

        assert components.sandbox_id == "sandbox123"
        assert components.session_id == "session456"
        assert components.artifact_id == "artifact789"
        assert components.subpath is None

    def test_with_subpath(self):
        """Test creating GridKeyComponents with subpath."""
        components = GridKeyComponents(
            sandbox_id="sandbox123",
            session_id="session456",
            artifact_id="artifact789",
            subpath="path/to/file.txt",
        )

        assert components.subpath == "path/to/file.txt"

    def test_immutable(self):
        """Test that GridKeyComponents is immutable."""
        components = GridKeyComponents(
            sandbox_id="sandbox123",
            session_id="session456",
            artifact_id="artifact789",
        )

        with pytest.raises(ValidationError):
            components.sandbox_id = "modified"


class TestGridKeyComponentsValidation:
    """Test GridKeyComponents validation."""

    def test_sandbox_id_with_slash_rejected(self):
        """Test that sandbox_id with slash is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GridKeyComponents(
                sandbox_id="sandbox/123",  # Invalid
                session_id="session456",
                artifact_id="artifact789",
            )

        assert "cannot contain '/'" in str(exc_info.value)

    def test_session_id_with_slash_rejected(self):
        """Test that session_id with slash is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GridKeyComponents(
                sandbox_id="sandbox123",
                session_id="session/456",  # Invalid
                artifact_id="artifact789",
            )

        assert "cannot contain '/'" in str(exc_info.value)

    def test_artifact_id_with_slash_rejected(self):
        """Test that artifact_id with slash is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GridKeyComponents(
                sandbox_id="sandbox123",
                session_id="session456",
                artifact_id="artifact/789",  # Invalid
            )

        assert "cannot contain '/'" in str(exc_info.value)


class TestGridKeyComponentsDictAccess:
    """Test backwards-compatible dict-like access for GridKeyComponents."""

    def test_getitem_access(self):
        """Test __getitem__ for accessing components."""
        components = GridKeyComponents(
            sandbox_id="sandbox123",
            session_id="session456",
            artifact_id="artifact789",
        )

        with pytest.warns(DeprecationWarning):
            assert components["sandbox_id"] == "sandbox123"
            assert components["session_id"] == "session456"
            assert components["artifact_id"] == "artifact789"

    def test_getitem_missing_key(self):
        """Test __getitem__ raises KeyError for missing keys."""
        components = GridKeyComponents(
            sandbox_id="sandbox123",
            session_id="session456",
            artifact_id="artifact789",
        )

        with pytest.warns(DeprecationWarning):
            with pytest.raises(KeyError):
                _ = components["nonexistent"]

    def test_get_method(self):
        """Test get() method returns value or default."""
        components = GridKeyComponents(
            sandbox_id="sandbox123",
            session_id="session456",
            artifact_id="artifact789",
        )

        with pytest.warns(DeprecationWarning):
            assert components.get("sandbox_id") == "sandbox123"
            assert components.get("nonexistent") is None
            assert components.get("nonexistent", "default") == "default"


# ============================================================================
# BatchStoreItem Tests
# ============================================================================


class TestBatchStoreItemBasics:
    """Test basic BatchStoreItem functionality."""

    def test_minimal_creation(self):
        """Test creating BatchStoreItem with required fields."""
        item = BatchStoreItem(
            data=b"test data",
            mime="text/plain",
            summary="Test item",
        )

        assert item.data == b"test data"
        assert item.mime == "text/plain"
        assert item.summary == "Test item"
        assert item.meta is None
        assert item.filename is None

    def test_full_creation(self):
        """Test creating BatchStoreItem with all fields."""
        item = BatchStoreItem(
            data=b"test data",
            mime="image/jpeg",
            summary="Image item",
            meta={"custom": "metadata"},
            filename="photo.jpg",
        )

        assert item.data == b"test data"
        assert item.mime == "image/jpeg"
        assert item.summary == "Image item"
        assert item.meta == {"custom": "metadata"}
        assert item.filename == "photo.jpg"


class TestBatchStoreItemValidation:
    """Test BatchStoreItem validation."""

    def test_empty_data_rejected(self):
        """Test that empty data is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            BatchStoreItem(
                data=b"",  # Invalid
                mime="text/plain",
                summary="Test",
            )

        assert "data cannot be empty" in str(exc_info.value)

    def test_empty_mime_rejected(self):
        """Test that empty mime is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            BatchStoreItem(
                data=b"test",
                mime="",  # Invalid
                summary="Test",
            )

        assert "at least 1 character" in str(exc_info.value)

    def test_missing_required_fields(self):
        """Test that missing required fields are rejected."""
        with pytest.raises(ValidationError):
            BatchStoreItem(
                data=b"test",
                mime="text/plain",
                # missing summary
            )


if __name__ == "__main__":
    # Run the tests
    pytest.main(
        [
            __file__,
            "-v",
            "--tb=short",
            "--durations=10",
        ]
    )
