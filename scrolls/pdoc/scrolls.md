# What is this?

Scrolls is designed to allow the execution of arbitrary untrusted code, without
opening yourself up to possible sandbox escapes. The original intended purpose
of this scripting engine is to allow users of Discord bots to create their own
custom commands with a simple scripting language. Because of this origin, there
are a few key design elements:

- The syntax for statements resembles discord bot prefix commands.
- The interpreter is designed to be as pluggable as possible - it will only
  ever do what you tell it to.
- Optimization isn't much of a priority - most commands will involve CPU or
  network-intensive operations, so the interpreter itself doesn't really need to
  be fast.

# What is this not?

- Scrolls is not meant for performance. If you want a decently fast embedded scripting
  language, try [Lua](https://www.lua.org/).
- Scrolls is meant for scripting *services* - chatbots, web interfaces, etc. While it
  can be used locally, there are better options when you don't need to worry about
  sandboxing.

# Quickstart

- Read [Language Overview](#language-overview) for an introduction to the Scrolls language.
- See `scrolls.interpreter` for an introduction to embedding Scrolls.
- See `scrolls.ast` for an explanation of the parser.

# Language Overview

Scrolls was originally designed to combine existing discord bot commands
into new ones. As such, the statement syntax was heavily based on bash/sh.
Other influences include python, lisp, and perl.

## Statements

There are three types of statements in Scrolls.

### Command
```scrolls
# syntax:
NAME SPACE_DELIMITED_ARGUMENTS
```

Similarly to shell scripts, the most basic form of a scrolls script is just a
sequence of commands:

```scrolls
print hello world
print this is an example
do-something 10 20
```

A command name may be any string that does not contain `$ ^ ! ( ) { } ; #`. Arguments
are set apart by spaces. Commands may be put on the same line using semicolons:

```scrolls
print hello world; print this is an example
do-something 10 20
```

You can terminate lines with semicolons if you want, but this is optional.

### Control
```scrolls
# syntax:
!NAME(SPACE_DELIMITED_ARGUMENTS) STATEMENT
```

Control structures all follow the same syntax in Scrolls. `!`, followed by the control name,
followed by arguments, followed by a single statement. Scrolls supports a number of traditional
control structures, including `while`, `if`, and `for`. 

In Scrolls, control structures are pluggable. Adding new ones does not increase the
complexity of syntax; they're technically function calls, not keywords.
Because of this, some shorthand structures are provided as well, such as `repeat`:

```scrolls
!repeat(4) print "hello world"

# equivalent to:
print hello world
print hello world
print hello world
print hello world
```

### Block
```scrolls
# syntax:
{
    STATEMENT
    STATEMENT
    ...
}
```

Blocks group together multiple statements into a single one. They can be placed anywhere a statement
is expected. This is used to achieve more recognizable control structures with code blocks:

```scrolls
!repeat(4) {
    print hello
    print world
}

# equivalent to:
print hello
print world
print hello
print world
print hello
print world
print hello
print world
```

## Comments

Comments may be defined with the `#` character.

```scrolls
# This is a comment.
print hello world# comments can border literals, though it doesn't look great.
print foo bar #comments! can( contain) any; character, and last until end of line.
```

## Variable Substitution

Scrolls supports variable expansion with `$`. Variables may be set with the built-in `set`
command.

```scrolls
set test hello world
print $test

# prints:
# hello world
```

There is also a built in `for` control call, which will run a code block repeatedly
with different parameters.

```scrolls
!for(x in 1 2 3 4 5) {
    print $x
}

# prints:
# 1
# 2
# 3
# 4
# 5
```

## Expansion Calls

In addition to variable expansion, expansions may call into some code, in which case
the code will determine what the expansion is replaced with. For example,
`$(select hello world)` will randomly be replaced by `hello` 50% of the time, and `world` otherwise. This may
be used to randomly select arguments to commands, or randomly select the commands
themselves:

```scrolls
command $(select arg1 arg2)
$(select command1 command2) hello world
```

The general form of an expansion call is `$(NAME SPACE_DELIMITED_ARGUMENTS)`. 
Expansion calls and variable references may be nested indefinitely:

```scrolls
set v test
command $(select $(select arg1 arg2 $v) $v)
```

## Functions / Defining Commands

Custom commands and substitution calls may be defined through the `def` control
structure.

**Defining a Command**
```scrolls
!def(commandname arg1 arg2) {
    print $arg1
    print $arg2
}
commandname hello world
```

**Defining an Expansion Call**
```scrolls
!def(square x) {
    return $(* x x)
}
print "4 squared is" $(square 4)
```

The key difference is the presence of the `return` command. If a `def` block
contains a `return` statement, it defines an expansion call. If not, it defines
a new command.

Note that it is currently not possible to define custom control structures with
Scrolls code. See [Extensions](interpreter.html#extensions) for more info on how to
define custom control structures.

## Math

Arithmetic and logic operators are implemented as expansion calls. This results
in a prefix syntax that [may look familiar](https://en.wikipedia.org/wiki/Polish_notation) if
you've ever used lisp:

```scrolls
# converts celsius to fahrenheit
!def(c_to_f c) {
    return $(+ $(* $c 1.8) 32)
}
```

## Datatypes

Scrolls is a weakly typed language, and its only real datatype is the string (specifically
utf-8 strings). All calls will convert to other datatypes internally as needed, and will
always return strings. That being said, built-in Scrolls calls will follow certain rules
when interpreting strings.

### Numeric

For the purposes of arithmetic and numeric comparisons:
- Floats are strings such as `3.5`, `-0.12`, `1.0`, etc.
- Integers are any numeric string with no decimal point; `1`, `-32`, etc.

Most arithmetic operators operate as follows:
- If all inputs are formatted as integers, the output will be too.
- If one or more inputs are formatted as floats, the output will be formatted as float.

For example:
- `$(+ 1 2 3)` will result in `6`
- `$(+ 1 2 3.0)` will result in `6.0`

Notable exceptions to this are:
- Division (`/`) will always output floats.

### Strings

Strings are the default datatype in Scrolls, and do not need to be enclosed in quotes.
If you need to include special characters or newlines in strings, you may use double
quotes:

```scrolls
print "hello world (foo bar) {this is fine}"
print "spacing      is      preserved"
print "newlines
are
allowed
too"
```

In order to include characters like `"`, you can use escape sequences:

```scrolls
# prints "quoted string"
print "\"quoted string\""
```

Nearly everything is a string, including all call names and variable references. As such,
call names may be stored in variables as a primitive form of indirection:

```scrolls
!for(operator in + - * /) {
  print $($operator 5 8) 
}

# Equivalent to...
print $(+ 5 8)
print $(- 5 8)
print $(* 5 8)
print $(/ 5 8)
```

See [arithmetic.scrl](examples/arithmetic.scrl) for an example of this idea. 

Using quoted literals, we can make the "everything is a string" idea a bit more obvious:

```scrolls
# Does the same thing as the above example
!"for"("operator" "in" "+" "-" "*" "/") {
  "print" $($"operator" "5" "8")
}
```

### Structures (Lists, etc.)

There are no dedicated datastructures in Scrolls, however there is built in support
for manipulating space-delimited lists of strings referred to as *vectors*. For example,
here is how to iterate over each element in a vector:

```scrolls
set vector 1 2 3 4 5
!while($(not $(vempty? $vector))) {
  print $(vhead $vector)      # vhead returns the first item in a vector
  set vector $(vtail $vector) # vtail returns all but the first item in a vector
}
```
Of course, this operation is common enough that a dedicated control structure is
provided for it:
```scrolls
set vector 1 2 3 4 5
!for(x in $^vector) {
  print $x
}
```

`$^` is the *vector expansion operator*. It will split the value of the expansion
along spaces, and pass the pieces as separate arguments. The best way to illustrate the
difference is with an example:

```scrolls
set vector 1 2 3 4 5
!for(x in $^vector) {
  print $x
}

# prints:
# 1
# 2
# 3
# 4
# 5
```

Contrast with removing `^`: 

```scrolls
set vector 1 2 3 4 5
!for(x in $vector) { # note the ^ is missing here! 
  print $x
}

# prints:
# 1 2 3 4 5
```

Above, the vector is being passed as a single, unsplit string. The primary use of
the `^` operator is to pass vectors into calls that do not understand them directly. For
example, the `shuffle` builtin, which shuffles its arguments, but does not understand
vectors:

```scrolls
# will always print 1 2 3 4 5
set vector 1 2 3 4 5
print $(shuffle $vector) # shuffle is only taking 1 argument here

# will shuffle as expected, ex 3 5 1 2 4
print $(shuffle $^vector) # note the added ^, shuffle is taking each element
                          # in $vector as its own argument
```

# Further Reading

- See `scrolls.builtins` for a reference of commands, control structures and expansions
included with Scrolls.
- See the [examples directory](https://github.com/a-bison/scrolls-py/tree/master/examples)
  for more complete examples of Scrolls code.
- See the source code: https://github.com/a-bison/scrolls-py