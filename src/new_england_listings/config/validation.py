from typing import Dict, Any, List
from enum import Enum


class ValidationRule:
    def __init__(self, **kwargs):
        self.min_value = kwargs.get('min_value')
        self.max_value = kwargs.get('max_value')
        self.allowed_formats = kwargs.get('allowed_formats', [])
        self.required_suffix = kwargs.get('required_suffix')
        self.allowed_values = kwargs.get('allowed_values', [])


VALIDATION_RULES = {
    "price": ValidationRule(
        min_value=0,
        max_value=10000000,  # $10M
        allowed_formats=["$X.XM", "$X,XXX,XXX"],
        allowed_values=["Contact for Price"]
    ),
    "acreage": ValidationRule(
        min_value=0,
        max_value=10000,  # 10,000 acres
        required_suffix="acres",
        allowed_values=["Not specified"]
    ),
    "location": ValidationRule(
        allowed_values=["Location Unknown"],
        required_suffix=None
    )
}
