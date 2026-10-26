"""Safe deterministic tools for AI agent execution in flake-detector.

Includes an AST-based safe calculator (strictly prohibiting code injection)
and a local fact lookup dictionary, along with OpenAI function schemas.
Conforms to PRD Section 10 and Milestone 04.
"""

from __future__ import annotations

import ast
import json
from typing import Any

# Allowed binary and unary operators for safe arithmetic
ALLOWED_OPERATORS: dict[type, Any] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a ** b,
    ast.Mod: lambda a, b: a % b,
    ast.FloorDiv: lambda a, b: a // b,
}

ALLOWED_UNARY_OPERATORS: dict[type, Any] = {
    ast.UAdd: lambda a: +a,
    ast.USub: lambda a: -a,
}

FACTS_DATABASE: dict[str, str] = {
    "capital_of_france": "Paris",
    "speed_of_light_m_s": "299792458",
    "python_creator": "Guido van Rossum",
    "apollo_11_year": "1969",
    "largest_planet": "Jupiter",
    "boiling_point_water_celsius": "100",
    "freezing_point_water_celsius": "0",
    "sun_center_of_solar_system": "True",
}

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": (
                "Safely evaluate a mathematical expression with numbers and + - * / ** % //"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression string to evaluate, e.g. '17 * 23'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_fact",
            "description": "Look up a verified factual key from the database",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": (
                            "Factual key, e.g. 'capital_of_france', 'speed_of_light_m_s', "
                            "'python_creator', 'apollo_11_year'"
                        ),
                    }
                },
                "required": ["key"],
            },
        },
    },
]


def _evaluate_ast_node(node: ast.AST) -> float | int:
    """Recursively and safely evaluate an AST arithmetic node."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in ALLOWED_OPERATORS:
            raise ValueError(f"Unsupported binary operator: {op_type.__name__}")

        left = _evaluate_ast_node(node.left)
        right = _evaluate_ast_node(node.right)

        # Guard against astronomical exponentiation attacks
        if op_type is ast.Pow and abs(right) > 100:
            raise ValueError("Exponent too large (max 100)")

        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Division by zero")

        return ALLOWED_OPERATORS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in ALLOWED_UNARY_OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        operand = _evaluate_ast_node(node.operand)
        return ALLOWED_UNARY_OPERATORS[op_type](operand)

    raise ValueError(f"Security restriction: AST node {type(node).__name__} is prohibited")


def calculator(expression: str) -> str:
    """Safely evaluate an arithmetic expression without eval() or exec().

    Args:
        expression: Mathematical string containing only numbers, operators, and parentheses.

    Returns:
        The calculated result as a string, or an error description.
    """
    if not expression or not expression.strip():
        return "Error: Empty expression"

    try:
        parsed = ast.parse(expression.strip(), mode="eval")
        result = _evaluate_ast_node(parsed.body)
        if isinstance(result, float) and result.is_integer():
            return str(int(result))
        return str(result)
    except ZeroDivisionError:
        return "Error: Division by zero"
    except (ValueError, SyntaxError) as exc:
        return f"Error: Invalid or prohibited expression ({exc})"
    except Exception as exc:
        return f"Error: Evaluation failed ({type(exc).__name__})"


def lookup_fact(key: str) -> str:
    """Look up a fact in the local dictionary.

    Args:
        key: Fact key identifier.

    Returns:
        The fact value string or an error if not found.
    """
    clean_key = key.strip().lower()
    if clean_key in FACTS_DATABASE:
        return FACTS_DATABASE[clean_key]
    return f"Fact not found for key: '{key}'"


def execute_tool(name: str, arguments: dict[str, Any] | str) -> str:
    """Dispatch and execute a tool by name with arguments."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return "Error: Tool arguments must be valid JSON"

    if name == "calculator":
        expr = arguments.get("expression", "")
        return calculator(str(expr))
    if name == "lookup_fact":
        fact_key = arguments.get("key", "")
        return lookup_fact(str(fact_key))
    return f"Error: Unknown tool '{name}'"
