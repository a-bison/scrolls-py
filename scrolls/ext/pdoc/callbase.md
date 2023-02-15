# Basic Usage

Here's an example that implements the [`print`](../builtins.html#scrolls.builtins.StdIoCommandHandler.print) builtin:

```py
import typing
import scrolls

# Note that callbase is an extension, and is not part of the main scrolls namespace.
from scrolls.ext import callbase

interpreter = scrolls.Interpreter()
commands: callbase.CallBaseCallHandler[None] = callbase.CallBaseCallHandler()
interpreter.command_handlers.add(commands)

@commands.add_callbase
@callbase.Option(
    "args",
    type=str,
    modifier=callbase.OptionModifier.GREEDY
)
@callbase.make_callbase(
    "print",
    "Prints all arguments."
)
def print_(ctx: scrolls.InterpreterContext, args: typing.Sequence[typing.Any]) -> None:
    print(" ".join(args))
```

# About

Callbase handles the job of parsing arguments, and allows some additional information
to be attached to Scrolls calls. Using callbase also means you do not need to implement
`scrolls.interpreter.callhandler.CallHandler` yourself in order to get started extending Scrolls.

None of the calls defined in `scrolls.builtins` use this extension. It is solely for
external users.