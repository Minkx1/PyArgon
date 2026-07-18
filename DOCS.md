# Argon Documentation

## Table of Contents

- [Introduction](#introduction)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Commands](#commands)
- [Flag Parameters](#flag-parameters)
- [Argument Parsing](#argument-parsing)
- [Examples](#examples)
  - [Boolean Flag](#boolean-flag)
  - [Value Flag](#value-flag)
  - [Combined Short Flags](#combined-short-flags)
- [Error Handling](#error-handling)
- [Project Structure](#project-structure)

## Introduction

PyArgon is a small Python library for building command-line applications with decorator-based command registration. It keeps CLI code simple by exposing Python functions as commands and supporting flags through the `Flag` helper.

## Installation

Install the package from PyPI or directly from GitHub:

```bash
pip install pyargon
```

or:

```bash
pip install git+https://github.com/Minkx1/PyArgon.git
```

## Quick Start

Create a `CliApplication`, register commands with `@app.command`, and call `app.run(sys.argv[1:])` in `__main__`.

`CliApplication.run` also supports a `set_default` value:

- `set_default="$only"` (the default) uses the only registered command when exactly one command exists.
- `set_default="command_name"` forces a specific default command when the first argument is not a recognized command.

## Commands

A command is any Python function registered with `@app.command`.

- The function name becomes the command name when no explicit names are provided.
- `@app.command(names=["main", "print"])` can expose multiple aliases for the same command.
- Positional function parameters are populated from CLI positional arguments.
- Parameters with default values are optional.
- A `Flag` default marks the parameter as a command-line option.

## Flag Parameters

`Flag` is the runtime descriptor for CLI flags. It accepts:

- `aliases`: list of supported aliases, for example, `['-t', '--time']`
- `takes_value`: whether the option requires a value
- `type`: conversion type for parsed values
- `default`: fallback value when the flag is not provided

Example:

```python
from pyargon import CliApplication, Flag, flag

app = CliApplication()


@app.command
def sum(
    first_num: int | float,
    second_num: int | float = 1,
    print_time: Flag = flag("-t", "--time"),
) -> None:
    message = f"Result of sum: {first_num + second_num}"
    if print_time:
        message = f"[TIME] {message}"
    print(message)
```

## Argument Parsing

PyArgon supports the following CLI forms:

- Positional args: `command 1 2`
- Long flags: `--time`
- Long flags with value: `--path=foo` or `--path foo`
- Short flag groups: `-cv` for boolean flags
- Keyword-style parameters for normal args: `name=value`
- Variadic args: allow `*args` in command functions to collect remaining positionals
- Keyword kwargs: allow `**kwargs` in command functions to collect unknown `name=value` pairs
- Separator `--` stops option parsing and treats remaining tokens as positional arguments

## Examples

### Boolean Flag

```bash
python main.py sum 1 2 -t
python main.py sum 1 2 --time
```

### Value Flag

```python
@app.command
def upload(path: Flag = flag("-p", "--path", takes_value=True, type=str)) -> None:
    print(path.value)
```

```bash
python main.py upload -p=path/to/file.txt
python main.py upload --path path/to/file.txt
```

### Combined Short Flags

```python
@app.command
def status(
    compact: Flag = Flag(["-c", "--compact"]),
    verbose: Flag = Flag(["-v", "--verbose"]),
) -> None:
    print(compact, verbose)
```

```bash
python main.py status -cv
```

## Error Handling

PyArgon raises `CliAppError` for CLI parsing failures, including:

- unknown option aliases
- missing option values
- invalid argument types
- unexpected positional arguments
- missing required positional arguments

## Project Structure

- `pyargon/cli.py`: CLI parser implementation
- `pyargon/__init__.py`: package exports
- `main.py`: example entry point
