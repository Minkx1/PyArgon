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
        if not aliases:
            raise ValueError("Flag must have at least one alias")

        self.aliases: list[str] = aliases
        self.takes_value: bool = takes_value
        self.type: type = type if type is not None else str
        self.default: Any = default
        self.was_set: bool = False
        self.value: Any = default if takes_value else False

    def set(self, value: Any = True) -> None:
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


def flag(
    *aliases: str,
    takes_value: bool = False,
    type: type | None = None,
    default: Any = None,
) -> Flag:
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

    return Flag(list(aliases), takes_value=takes_value, type=type, default=default)


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
                "kind": param.kind,
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
        var_positional_name: str | None = None
        var_keyword_name: str | None = None
        var_keyword_values: dict[str, Any] = {}

        for name, meta in self.args.items():
            if meta["is_flag"]:
                alias_to_param.update({alias: name for alias in meta["flag_aliases"]})
                param_values[name] = Flag(
                    aliases=list(meta["flag_aliases"]),
                    takes_value=meta["takes_value"],
                    type=meta["type"],
                    default=meta["default_value"],
                )
            elif meta["kind"] == inspect.Parameter.VAR_POSITIONAL:
                var_positional_name = name
                param_values[name] = ()
            elif meta["kind"] == inspect.Parameter.VAR_KEYWORD:
                var_keyword_name = name
                param_values[name] = {}
            elif meta["has_default"]:
                param_values[name] = meta["default"]
            else:
                param_values[name] = MISSING

            if not meta["is_flag"] and meta["kind"] not in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            ):
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
                    option_flag.set(self._parse_value(meta["type"], raw_value))
                else:
                    if raw_value is not None:
                        raise CliAppError(f"Option {option} does not accept a value")
                    option_flag.set(True)

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
                        option_flag.set(self._parse_value(meta["type"], raw_value))
                        raw_short = ""
                        break
                    option_flag.set(True)

                i += 1
                continue

            if "=" in token:
                # Parse keyword-style values like name=value for non-flag parameters.
                key, raw_value = token.split("=", 1)
                if key in self.args and not self.args[key]["is_flag"]:
                    meta = self.args[key]
                    if meta["kind"] == inspect.Parameter.VAR_POSITIONAL:
                        raise CliAppError(
                            f"Cannot assign value to variadic positional parameter: {key}"
                        )
                    param_values[key] = self._parse_value(meta["type"], raw_value)
                elif var_keyword_name is not None:
                    var_keyword_values[key] = raw_value
                else:
                    raise CliAppError(f"Unknown keyword argument: {key}")
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

        remaining_positionals = positional_tokens[positional_index:]
        if var_positional_name is not None:
            var_meta = self.args[var_positional_name]
            element_type = Command._annotation_to_type(var_meta["annotation"])
            param_values[var_positional_name] = tuple(
                self._parse_value(element_type, token)
                for token in remaining_positionals
            )
        elif remaining_positionals:
            raise CliAppError(
                f"Unexpected positional arguments: {remaining_positionals}"
            )

        if var_keyword_name is not None:
            param_values[var_keyword_name] = var_keyword_values

        positional_args: list[Any] = []
        keyword_args: dict[str, Any] = {}
        for name, meta in self.args.items():
            if meta["kind"] == inspect.Parameter.VAR_POSITIONAL:
                positional_args.extend(param_values[name])
            elif meta["kind"] == inspect.Parameter.VAR_KEYWORD:
                keyword_args.update(param_values[name])
            elif meta["kind"] == inspect.Parameter.POSITIONAL_ONLY:
                positional_args.append(param_values[name])
            else:
                keyword_args[name] = param_values[name]

        try:
            self.func(*positional_args, **keyword_args)
        except CliAppError:
            raise
        except Exception as exc:
            raise CliAppError(f"Error occurred while executing command: {exc}") from exc


class CliApplication:
    def __init__(
        self,
        name: str = "CLI Application",
        description: str = "A simple CLI application",
    ):
        self.name = name
        self.description = description
        self.commands: dict[str, Command] = {}
        self.command_names: dict[Command, list[str]] = {}
        self.command_count: int = 0

        self.commands_map: list[tuple[list[str], Command]] = []

    def command(self, names: list[str] | str = "") -> Callable:
        """Decorator to register a function as a command.

        Args:
            names(list[str]|str): the name(s) of the function, that can be called in the arguments.
        """

        def decorator(func: Callable):
            cmd = Command(func)
            if not names:
                self.commands[func.__name__] = cmd
                self.command_names[cmd] = [func.__name__]

                self.commands_map.append(([func.__name__], cmd))
            else:
                for n in names:
                    self.commands[n] = cmd
                self.command_names[cmd] = list(names)
                self.commands_map.append((list(names), cmd))
            self.command_count += 1
            return func

        return decorator

    def run(self, args: list[str] = sys.argv[1:], set_default: str = "$only"):
        """Runs CliApplication with given arguments(default: system arguments)

        Args:
            args(list[str]): List of command-line arguments after the command name.
            set_default(str, optional): Default command name or "$only" to use the only
                registered command when exactly one command exists.

        """
        if len(args) == 0:
            self.print_help()
            return

        if args[0] in self.commands:
            command_name = args[0]
            command_args = args[1:]
        elif set_default == "$only" and self.command_count == 1:
            command_name = next(iter(self.commands.keys()))
            command_args = args
        elif set_default != "$only" and set_default in self.commands:
            command_name = set_default
            command_args = args
        else:
            command_name = args[0]
            command_args = args[1:]

        if command_name in self.commands:
            command_func = self.commands[command_name]
            command_func(command_args)
        else:
            print(f"Unknown command: {command_name}")
            self.print_help()

    def print_help(self):
        print(f"{self.name}\n\n{self.description}")
        print("Available commands:")
        for command_names, command in self.commands_map:
            doc = command.docstring
            if doc == "None":  # No docstring
                doc = "Usage unknown."

            aliases = ""
            for name in command_names:
                if name != "":
                    aliases += name + ", "
            aliases = aliases.removesuffix(", ")
            print(f"  {aliases} : {doc}")
