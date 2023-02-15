This module is the main point of interaction for most uses of Scrolls. The `scrolls.interpreter.run.Interpreter` implements functions that
interpret Scrolls scripts. The `scrolls.interpreter.state.InterpreterContext` class is responsible for tracking the state of the Scrolls
interpreter.

# Using the Interpreter

## Quickstart

Basic usage of the interpreter is straightforward. Instantiate `scrolls.interpreter.run.Interpreter`, and configure it with the desired
features, either from `scrolls.builtins`, or custom modules. Then, the interpreter may be used to run Scrolls scripts.

```py
import scrolls

# Create an interpreter. Note that an interpreter created this 
# way will not actually do anything. It's the responsibility of 
# the user to configure with the desired language features.
interpreter = scrolls.Interpreter()

# Configure the interpreter with the base language.
# scrolls.base_config is provided to make this common task
# a bit easier.
scrolls.base_config.configure(interpreter)

# Configure with stdio commands like input, and print
interpreter.command_handlers.add(scrolls.StdIoCommandHandler())

# Run your script.
script = """
!repeat(4) {
    print "Hello world!"
}
"""
interpreter.run(script)

# Note: This will print
# Hello world!
# Hello world!
# Hello world!
# Hello world!
```

`scrolls.__main__` implements a bare minimum standalone Scrolls interpreter with this interface. Take a look if you
need a more concrete example.

## Extensions

Of course, the main usage of Scrolls is not as a standalone language, but as an engine embedded in a parent application.
Eventually, you'll most likely need to implement extensions to the language.

The primary method of extending Scrolls is through call handlers (`scrolls.interpreter.callhandler.CallHandler`).

### Call Types

Calls come in three different types, however all calls are fundamentally function calls. Most of the time, they will
call into some python code, but support is offered for calls written in Scrolls code themselves (see `!def`).

#### Command Calls

Command calls are what most languages would refer to as "statements".

```scrolls
print "Tell me your name:"
input name
print "Hello," $name
```

In the above example, `print` and `input` are command calls. Command calls do not return anything. In `scrolls.interpreter`
terms, command calls are calls for which `scrolls.interpreter.callhandler.CallHandler.handle_call` returns `None`. Command calls are counted as
statements. See `scrolls.interpreter.run.Interpreter.interpret_statement`.

#### Expansion Calls

Expansion calls are what most languages would refer to as "functions".

```scrolls
print "Here's a random choice:" $(select foo bar baz)
print "9 + 10 is:" $(+ 9 10)
```

In the above example, `select` and `+` are expansion calls. Expansion calls always return strings. In `scrolls.interpreter`
terms, expansion calls are calls for which `scrolls.interpreter.callhandler.CallHandler.handle_call` returns `str`. Expansion calls are **not**
counted as statements, and must be used in the context of either a command call, or control call.

Note that even arithmetic operations like `+ - * /` are implemented as expansion calls.
See `scrolls.builtins.ArithmeticExpansionHandler`.

#### Control Calls

Control calls implement control structures.

```scrolls
!repeat(4) {
    print "Hello world!"
}
!if($true) print "This was a true statement."
```

In the above example, `repeat` and `if` are control calls. Control calls are unique in that they take a Scrolls
statement in addition to the normal call arguments. This can be used to implement common control structures like
`if`, `while`, etc. See `scrolls.builtins.BuiltinControlHandler`. Control calls do not return anything, like command calls.
Control calls are counted as statements.

### Implementing Call Handlers

The bare minimum for implementing a call handler is to implement the `scrolls.interpreter.callhandler.CallHandler` protocol. Call handlers must implement
two functions:

- `handle_call`: Called when a call is invoked.
- `__contains__`: Should return `True` if the call handler supports a call, i.e. `"call_name" in handler`.

Let's make a simple command call handler for a call named `printargs`, which prints out all of the arguments passed to
it.

```py
import scrolls

# Create interpreter
interpreter = scrolls.Interpreter()

# Create your handler
class PrintArgsHandler:
    def handle_call(self, ctx: scrolls.InterpreterContext) -> None:
        if ctx.call_name == "printargs":
            for arg in ctx.args:
                print(arg)

    def __contains__(self, call_name: str) -> bool:
        return call_name == "printargs"

# Add the handler to the interpreter
interpreter.command_handlers.add(PrintArgsHandler())

# Run a script containing your command:
interpreter.run("""
printargs foo bar "this is one argument" baz
""")

# NOTE - Prints
# foo
# bar
# this is one argument
# baz
```

### Using `CallbackCallHandler`

The `scrolls.interpreter.callhandler.CallHandler` protocol is deliberately left simple for maximum flexibility, but it's also kind of awkward for most
uses. A basic call handler is provided to handle boilerplate, `scrolls.interpreter.callhandler.CallbackCallHandler`. 
Let's implement `printargs` with `scrolls.interpreter.callhandler.CallbackCallHandler`.

```py
import scrolls

# Create interpreter
interpreter = scrolls.Interpreter()

# Create your handler
# Note that this may also use the shortcut: scrolls.CallbackCommandHandler,
# but it's the same thing.
class PrintArgsHandler(scrolls.CallbackCallHandler[None]):
    def __init__(self):
        super().__init__()
        self.add_call("printargs", self.printargs)
        
    def printargs(self, ctx: scrolls.InterpreterContext) -> None:
        for arg in ctx.args:
            print(arg)

# Add the handler to the interpreter
interpreter.command_handlers.add(PrintArgsHandler())

# Run a script containing your command:
interpreter.run("""
printargs foo bar "this is one argument" baz
""")

# NOTE - Prints
# foo
# bar
# this is one argument
# baz
```

`scrolls.interpreter.callhandler.CallbackCallHandler` may be considered the base call handler class for most purposes. All builtin language features
are implemented with `scrolls.interpreter.callhandler.CallbackCallHandler`. See `scrolls.builtins`.