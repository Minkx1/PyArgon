import sys
import time

from argon import CliApplication, Flag

app = CliApplication()


@app.command
def sum(
    first_num: float,
    second_num: float,
    print_time: Flag | None = None,  # print_time: Flag = Flag(["-t", "--time"])
) -> None:
    """Prints the sum of two numbers.

    Args:
        first_num(float): The first number to be summed.
        second_num(float): The second number to be summed.
    """
    # if print_time is None:
    # print_time = Flag(["-t", "--time"])

    msg = f"Result of sum: {first_num + second_num}"

    if print_time:
        t = time.localtime()
        msg = f"[{t.tm_hour}:{t.tm_min}:{t.tm_sec}] " + msg

    print(msg)


if __name__ == "__main__":
    arguments: list[str] = sys.argv[1::]  # List of system arguments without `file.py` .

    app.run(arguments)
