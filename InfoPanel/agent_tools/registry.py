from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]

    def openai_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable[..., Any],
    ) -> Callable[..., Any]:
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered.")
        self._tools[name] = ToolSpec(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
        )
        return handler

    def tool(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
            self.register(
                name=name,
                description=description,
                parameters=parameters,
                handler=handler,
            )
            return handler

        return decorator

    def list_definitions(self) -> list[dict[str, Any]]:
        return [tool.openai_definition() for tool in self._tools.values()]

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def call(self, name: str, arguments: str | dict[str, Any] | None = None) -> Any:
        spec = self.get(name)
        if spec is None:
            raise KeyError(f"Unknown tool: {name}")

        parsed_args = self._parse_arguments(arguments)
        validated_args = self._validate_arguments(spec, parsed_args)
        return spec.handler(**validated_args)

    @staticmethod
    def _parse_arguments(arguments: str | dict[str, Any] | None) -> dict[str, Any]:
        if arguments in (None, ""):
            return {}
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            parsed = json.loads(arguments)
            if not isinstance(parsed, dict):
                raise ValueError("Tool arguments must decode to a JSON object.")
            return parsed
        raise TypeError("Tool arguments must be a dict, JSON string, or None.")

    def _validate_arguments(
        self,
        spec: ToolSpec,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        schema = spec.parameters or {}
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        missing = [name for name in required if name not in arguments]
        if missing:
            raise ValueError(f"Missing required arguments for {spec.name}: {', '.join(missing)}")

        unknown = [name for name in arguments if name not in properties]
        if unknown:
            raise ValueError(f"Unknown arguments for {spec.name}: {', '.join(unknown)}")

        validated: dict[str, Any] = {}
        for name, value in arguments.items():
            validated[name] = self._coerce_value(value, properties.get(name, {}))
        return validated

    @staticmethod
    def _coerce_value(value: Any, schema: dict[str, Any]) -> Any:
        schema_type = schema.get("type")
        if schema_type == "number":
            if isinstance(value, (int, float)):
                return value
            if isinstance(value, str):
                numeric = float(value)
                return int(numeric) if numeric.is_integer() else numeric
            raise ValueError(f"Expected a number, got {type(value).__name__}.")
        if schema_type == "integer":
            if isinstance(value, bool):
                raise ValueError("Booleans are not valid integers.")
            return int(value)
        if schema_type == "string":
            if isinstance(value, str):
                return value
            raise ValueError(f"Expected a string, got {type(value).__name__}.")
        if schema_type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "1", "yes", "on"}:
                    return True
                if lowered in {"false", "0", "no", "off"}:
                    return False
            raise ValueError(f"Expected a boolean, got {value!r}.")
        return value


registry = ToolRegistry()
tool = registry.tool
