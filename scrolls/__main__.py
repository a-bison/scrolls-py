import argparse
import pathlib
import sys

import scrolls


def set_up_argparse() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scrolls",
        description=(
            "A basic interpreter for scrolls."
        )
    )

    parser.add_argument(
        "file", type=str, help=(
            "The file to interpret."
        )
    )

    return parser


def main() -> None:
    parser = set_up_argparse()
    args = parser.parse_args()

    file = pathlib.Path(args.file)

    if not file.exists():
        parser.error(f"file: cannot find {file}")

    if not file.is_file():
        parser.error(f"file: {file} is not a file")

    interpreter = scrolls.Interpreter()
    interpreter.control_handlers.add(scrolls.BuiltinControlHandler())
    interpreter.command_handlers.add(scrolls.BuiltinCommandHandler())
    interpreter.command_handlers.add(scrolls.StdIoCommandHandler())
    interpreter.expansion_handlers.add(scrolls.RandomExpansionHandler())
    interpreter.expansion_handlers.add(scrolls.ArithmeticExpansionHandler())
    interpreter.expansion_handlers.add(scrolls.ComparisonExpansionHandler())
    interpreter.expansion_handlers.add(scrolls.LogicExpansionHandler())

    with open(file, 'r') as f:
        script = f.read()

    try:
        interpreter.run(script)
    except scrolls.ScrollError as e:
        print(f"error:\n{e}", file=sys.stderr)
        sys.exit(1)


main()
