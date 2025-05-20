"""
jirassicpack.utils.fields

Custom Marshmallow fields and validators for Jira CLI schemas. Provides reusable field types, normalization, and validation utilities for robust schema-driven CLI input.
"""
import re
from marshmallow import fields, ValidationError, Schema, pre_load
import datetime

class IssueKeyField(fields.Str):
    """
    Marshmallow field for validating Jira issue keys (e.g., DEMO-123).
    """
    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if not re.match(r'^[A-Z][A-Z0-9]+-\d+$', value):
            raise ValidationError("Invalid Jira issue key format (e.g., DEMO-123).")
        return value 

class ProjectKeyField(fields.Str):
    """
    Marshmallow field for validating Jira project keys (e.g., DEMO).
    """
    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if not re.match(r'^[A-Z][A-Z0-9]+$', value):
            raise ValidationError("Invalid Jira project key format (e.g., DEMO).")
        return value 

def normalize_string(value: str) -> str:
    """Trim whitespace and normalize string values."""
    if isinstance(value, str):
        return value.strip()
    return value

class BaseOptionsSchema(Schema):
    """
    Base schema for common CLI options. Normalizes all string fields, lowercases emails, and coerces empty strings to None for required fields.
    """
    output_dir = fields.Str(load_default='output')
    unique_suffix = fields.Str(load_default='')

    @pre_load
    def normalize(self, data, **kwargs):
        for k, v in list(data.items()):
            if isinstance(v, str):
                v = v.strip()
                # Lowercase emails
                if 'email' in k:
                    v = v.lower()
                # Coerce empty strings to None for required fields
                field_obj = self.fields.get(k)
                if field_obj and getattr(field_obj, 'required', False) and v == '':
                    data[k] = None
                else:
                    data[k] = v
        return data 

def validate_date(value: str) -> None:
    """Validate date string is in YYYY-MM-DD format. Raises ValidationError if invalid."""
    if not isinstance(value, str):
        raise ValidationError("Date must be a string in YYYY-MM-DD format.", "Example: 2024-01-01")
    try:
        datetime.datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        raise ValidationError("Date must be in YYYY-MM-DD format.", "Example: 2024-01-01")

def validate_nonempty(value: str) -> None:
    """Validate that a string is not empty. Raises ValidationError if empty."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("This field cannot be empty.", "Please enter a value.")

# For enums/choices, use marshmallow.validate.OneOf directly in schemas 