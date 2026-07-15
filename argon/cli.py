import inspect
import sys
from collections.abc import Callable
from typing import Any


class Flag:
    """Represents a command-line flag parameter.

    A flag is declared as a default value in a command function. This class
    carries aliases, whether the flag accepts a value, and the expected type of
    that value.
    """

    def __init__(
        self,
        aliases: list[str],
        takes_value: bool = False,
        type: type | None = None,
        default: Any = None,
    ) -> None:
        """Create a new command-line flag descriptor.

        Args:
            aliases: List of supported flag aliases, such as ["-t", "--time"].
            takes_value: Whether the flag accepts a value instead of acting as a
                boolean switch.
            type: Value type for flags that take a value. Defaults to str.
            default: Default flag value when the option is not present.

        Raises:
            ValueError: If no aliases are provided.
        """
        if not aliases:
            raise ValueError("Flag must have at least one alias")

        self.aliases: list[str] = aliases
        self.takes_value: bool = takes_value
        self.type: type = type if type is not None else str
        self.default: Any = default
        self.was_set: bool = False
        self.value: Any = default if takes_value else False

    def put(self, value: Any = True) -> None:
        """Mark the flag as set and store its parsed value."""
        self.was_set = True
        self.value = value

    def __bool__(self) -> bool:
        """Return True when the flag was provided on the command line."""
        return self.was_set

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        if self.takes_value:
            return f"Flag(aliases={self.aliases}, value={self.value!r})"
        return f"Flag(aliases={self.aliases}, set={self.was_set})"

    def clone(self) -> "Flag":
        """Return a fresh copy of the flag descriptor."""
        return Flag(
            aliases=list(self.aliases),
            takes_value=self.takes_value,
            type=self.type,
            default=self.default,
        )


class CliAppError(Exception): ...


MISSING = object()


class Command:
    """Wraps a command function and handles argument parsing."""

    @staticmethod
    def _annotation_to_type(annotation: Any) -> type:
        """Convert a parameter annotation into a concrete Python type.

        Args:
            annotation: Raw annotation from the function signature.

        Returns:
            A Python type to use for parsing CLI strings.
        """
        if annotation is inspect._empty or annotation is Any:
            return str
        if annotation is Flag:
            return str
        if getattr(annotation, "__origin__", None) is None:
            return annotation
        if getattr(annotation, "__origin__", None) is type(None):
            return str
        return str

    @staticmethod
    def parse_func(func: Callable) -> dict:
        """Parse function parameters and build metadata for CLI dispatch.

        Args:
            func: The function registered as a command.

        Returns:
            A dictionary of parameter metadata used by the CLI parser.
        """
        sig = inspect.signature(func)
        parameters = {}

        for name, param in sig.parameters.items():
            annotation = param.annotation
            has_default = param.default is not inspect._empty
            default = param.default if has_default else MISSING
            is_flag = isinstance(default, Flag)
            flag_aliases = []
            takes_value = False
            flag_type = str
            flag_default = None

            if is_flag:
                flag_aliases = list(default.aliases)
                takes_value = default.takes_value
                flag_type = default.type
                flag_default = default.default

            param_type = Command._annotation_to_type(annotation)
            parameters[name] = {
                "name": name,
                "param": param,
                "annotation": annotation,
                "has_default": has_default,
                "default": default,
                "is_flag": is_flag,
                "flag_aliases": flag_aliases,
                "takes_value": takes_value,
                "type": flag_type if is_flag else param_type,
                "default_value": flag_default if is_flag else default,
            }

        return parameters

    def __init__(self, func: Callable):
        """Create a command wrapper for a registered function.

        Args:
            func: The callable to expose as a CLI command.
        """
        self.func = func
        self.name: str = func.__name__
        self.docstring: str = str(func.__doc__)
        self.signature = inspect.signature(func)
        self.args: dict = self.parse_func(func)

    def _parse_value(self, expected_type: type, value: str) -> Any:
        try:
            if expected_type is bool:
                lower = value.lower()
                if lower in {"1", "true", "yes", "on"}:
                    return True
                if lower in {"0", "false", "no", "off"}:
                    return False
            return expected_type(value)
        except ValueError as exc:
            raise CliAppError(
                f"Invalid argument type for value {value!r}. Expected {expected_type.__name__}."
            ) from exc

    def _find_flag_param(self, alias: str, alias_to_param: dict[str, str]) -> str:
        if alias not in alias_to_param:
            raise CliAppError(f"Unknown option: {alias}")
        return alias_to_param[alias]

    def __call__(self, args: list[str]):
        """Parse CLI arguments and invoke the wrapped command.

        Args:
            args: List of command-line arguments after the command name.

        Raises:
            CliAppError: If parsing fails or an unknown option is encountered.
        """
        alias_to_param: dict[str, str] = {}
        param_values: dict[str, Any] = {}
        positional_names: list[str] = []

        for name, meta in self.args.items():
            if meta["is_flag"]:
                alias_to_param.update({alias: name for alias in meta["flag_aliases"]})
                param_values[name] = Flag(
                    aliases=list(meta["flag_aliases"]),
                    takes_value=meta["takes_value"],
                    type=meta["type"],
                    default=meta["default_value"],
                )
            elif meta["has_default"]:
                param_values[name] = meta["default"]
            else:
                param_values[name] = MISSING

            if not meta["is_flag"]:
                positional_names.append(name)

        positional_tokens: list[str] = []
        i = 0

        while i < len(args):
            token = args[i]

            if token == "--":
                # Treat all following tokens as positional arguments.
                positional_tokens.extend(args[i + 1 :])
                break

            if token.startswith("--"):
                # Parse long option forms like --flag and --flag=value.
                if "=" in token:
                    option, raw_value = token.split("=", 1)
                else:
                    option, raw_value = token, None

                param_name = self._find_flag_param(option, alias_to_param)
                meta = self.args[param_name]
                option_flag: Flag = param_values[param_name]

                if meta["takes_value"]:
                    if raw_value is None:
                        i += 1
                        if i >= len(args):
                            raise CliAppError(f"Missing value for option: {option}")
                        raw_value = args[i]
                    option_flag.put(self._parse_value(meta["type"], raw_value))
                else:
                    if raw_value is not None:
                        raise CliAppError(f"Option {option} does not accept a value")
                    option_flag.put(True)

                i += 1
                continue

            if token.startswith("-") and token != "-":
                # Parse short option groups like -abc and value forms like -i=value.
                raw_short = token[1:]
                while raw_short:
                    alias = f"-{raw_short[0]}"
                    param_name = self._find_flag_param(alias, alias_to_param)
                    meta = self.args[param_name]
                    option_flag = param_values[param_name]
                    raw_short = raw_short[1:]

                    if meta["takes_value"]:
                        raw_short = raw_short.removeprefix("=")
                        if raw_short:
                            raw_value = raw_short
                        else:
                            i += 1
                            if i >= len(args):
                                raise CliAppError(f"Missing value for option: {alias}")
                            raw_value = args[i]
                        option_flag.put(self._parse_value(meta["type"], raw_value))
                        raw_short = ""
                        break
                    option_flag.put(True)

                i += 1
                continue

            if "=" in token:
                # Parse keyword-style values like name=value for non-flag parameters.
                key, raw_value = token.split("=", 1)
                if key not in self.args or self.args[key]["is_flag"]:
                    raise CliAppError(f"Unknown keyword argument: {key}")
                meta = self.args[key]
                param_values[key] = self._parse_value(meta["type"], raw_value)
                i += 1
                continue

            positional_tokens.append(token)
            i += 1

        positional_index = 0
        for name in positional_names:
            if param_values[name] is not MISSING:
                continue
            if positional_index >= len(positional_tokens):
                raise CliAppError(f"Missing positional argument: {name}")
            meta = self.args[name]
            param_values[name] = self._parse_value(
                meta["type"], positional_tokens[positional_index]
            )
            positional_index += 1

        if positional_index < len(positional_tokens):
            raise CliAppError(
                f"Unexpected positional arguments: {positional_tokens[positional_index:]}"
            )

        try:
            self.func(**param_values)
        except CliAppError:
            raise
        except Exception as exc:
            raise CliAppError(f"Error occurred while executing command: {exc}") from exc


class CliApplication:
    def __init__(
        self,
        name: str = "CLI Application",
        description: str = "A simple CLI application",
        one_command: Callable | None = None,
    ):
        self.name = name
        self.description = description
        self.commands: dict[str, Command] = {}

        self.one_command: Callable | None = one_command
        if one_command:
            self.commands["main"] = Command(one_command)

    def command(self, func: Callable) -> Callable:
        """Decorator to register a function as a command."""

        self.commands[func.__name__] = Command(func)
        return func

    def run(self, args: list[str] = sys.argv[1:]):
        if len(args) == 0:
            self.print_help()
            return

        if not getattr(self, "one_command", None):
            command_name = args[0]
            command_args = args[1:]
        else:
            command_name = "main"
            command_args = args

        if command_name in self.commands:
            command_func = self.commands[command_name]
            command_func(command_args)
        else:
            print(f"Unknown command: {command_name}")
            self.print_help()

    def print_help(self):
        print(f"{self.name}\n\n{self.description}")
        print("Available commands:")
        for command_name, command in self.commands.items():
            doc = command.docstring
            if not doc:
                doc = "Unknown."

            print(f"  {command_name}: {doc}")
