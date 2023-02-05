import argparse
import logging
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
        "file", nargs="?", help=(
            "The file to interpret."
        )
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help=(
            "Verbose mode."
        )
    )

    return parser


def scrolls_error(e: scrolls.ScrollError) -> None:
    print(f"error:\n{e}", file=sys.stderr)


def main() -> None:
    parser = set_up_argparse()
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    interpreter = scrolls.Interpreter()
    scrolls.base_config.configure(interpreter)
    scrolls.file_config.configure(interpreter)
    interpreter.command_handlers.add(scrolls.StdIoCommandHandler())
    interpreter.expansion_handlers.add(scrolls.RandomExpansionHandler())

    # Needs to go last, so it's the last attempted command handler.
    scrolls.unified_config.configure(interpreter)

    if args.file:
        file = pathlib.Path(args.file)

        if not file.exists():
            parser.error(f"file: cannot find {file}")

        if not file.is_file():
            parser.error(f"file: {file} is not a file")

        with open(file, 'r') as f:
            script = f.read()

        try:
            interpreter.run(script)
        except scrolls.ScrollError as e:
            scrolls_error(e)
            sys.exit(1)
    else:
        print(f"Scrolls v{scrolls.__version__} (interactive mode)")
        print("Type \"stop\" to quit.")
        interpreter.repl(on_error=scrolls_error)


main()
