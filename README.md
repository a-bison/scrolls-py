<p align="center">
  <img src="media/scrolls-logo.png" width="200"/>
</p>

<h1 align="center">Scrolls</h1>
Scrolls is a small interpreter originally designed to allow users of my discord bots to
make custom commands. It prioritizes control over the interpreter to help prevent abuse,
while still allowing tight integration with python code.

## Why?
The two other candidates for user scripts were python and Lua. Python code is a nightmare
to sandbox properly, and the available Lua interpreters for python didn't give me the kind
of control I wanted over the interpreter. In addition, Lua was a bit much for simple
custom commands. So, I made my own interpreter.

There is a scripting language available for Rust called [Rhai](https://rhai.rs/book/) with
a similar concept.

Also, I just kinda wanted to try making an interpreted language...

## Goals

- Allow the developer to prevent abuse.
- Integrate tightly with the parent python application.
- Keep the syntax as simple as possible.

## Language Overview

### Command Calls

Scrolls uses a simplistic shell-like syntax. The most basic form of a scrolls script is
just a sequence of commands:

```
print hello world
print this is an example
do-something 10 20
```

A command name may be any string that does not contain `$ ^ ! ( ) { } ;`. Arguments
are set apart by spaces. Commands may be put on the same line using semicolons:

```
print hello world; print this is an example
do-something 10 20
```

You can terminate lines with semicolons if you want, but this is optional.

Commands are more specifically referred to as "command calls". Each command call calls
into some python code.

### Control Calls

```
!repeat(4) {
    print hello world
}
```
equivalent to...
```
print hello world
print hello world
print hello world
print hello world
```

Control calls are not keywords, but ordinary python functions that can be customized.
The difference is that control calls take a scrolls statement as an argument, and command
calls do not. Control call names MUST start with `!`. Other than that, the same naming
rules apply, no `$ ! ( ) { } ;` (`!` may not appear anywhere but the start). Note that 
control calls also take their arguments in parentheses, as opposed to commands.

### Statements

There are three types of statements in Scrolls:

#### Command
```
NAME SPACE_DELIMITED_ARGUMENTS
```

#### Block
```
{
    STATEMENT
    STATEMENT
    ...
}
```

#### Control
```
!NAME(SPACE_DELIMITED_ARGUMENTS) STATEMENT
```

Due to this definition, the following is also valid:

```
!repeat(4) print hello world
```

### Variable Substitution

Scrolls supports variable expansion with `$`. Variables may be set with the built-in `set`
command call.

```
set test hello world
print $test
```
will print...
```
hello world
```

There is also a built in `for` control call, which will run a code block repeatedly
with different parameters.

```
!for(x in 1 2 3 4 5) {
    print $x
}
```
will print...
```
1
2
3
4
5
```

### Substitution Calls

In addition to variable expansion, expansions may call into python code, in which case
the python code will determine what the expansion is replaced with. For example,
`$(select hello world)` will randomly be replaced by `hello` 50% of the time, and `world` otherwise. This may
be used to randomly select arguments to commands, or randomly select the commands
themselves:

```
command $(select arg1 arg2)
$(select command1 command2) hello world
```

The general form of a substitution call is `$(NAME SPACE_DELIMITED_ARGUMENTS)`.
Substitution calls and variable references may be nested indefinitely:

```
set v test
command $(select $(select arg1 arg2 $v) $v)
```

### Comments

Scrolls does not currently support comments.

## API Documentation

TODO, sorry!

## Acknowledgements

- [hikari-lightbulb](https://github.com/tandemdude/hikari-lightbulb) by tandemdude, which inspired the default commands interface 
  for Scrolls (see [here](scrolls/commands.py)).