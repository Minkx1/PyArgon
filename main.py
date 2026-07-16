import sys

from argon import CliApplication, Flag, flag

app = CliApplication()


@app.command(names=["main", "print"])
def main(
    *words: str,
    time: Flag = flag("-t", "--time-on"),
    sugar: Flag = flag("-s", "--sugar"),
    log: Flag = flag("-l", "--log", takes_value=True, type=str),
):
    """Command prints some words."""
    message: str = ""
    if sugar:
        print("Adding some !!!AMAZING!!! SUGA~A~AR!\n")
    for w in words:
        if time:
            message += "[TIME] "
        message += w
        message += "\n"

    message = message.removesuffix("\n")

    if log:
        with open(log.value, "w") as f:
            f.write(message)

    print(message, flush=True)


if __name__ == "__main__":
    args: list[str] = sys.argv[1:]  # List of system arguments without `file.py` .
    app.run(args, set_default="$only")
