<p align="center">
  <img src="media/scrolls-logo.png" width="200"/>
</p>

<h1 align="center">Scrolls</h1>
Scrolls is a small interpreter originally designed to allow users of my discord bots to
make custom commands. It prioritizes control over the interpreter to help prevent abuse,
while still allowing tight integration with python code.

## Links

- Documentation: https://a-bison.github.io/scrolls-py-docs/

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

A command name may be any string that does not contain `$ ^ ! ( ) { } ; #`. Arguments
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

# equivalent to:
print hello world
print hello world
print hello world
print hello world
```

Control calls are not keywords, but ordinary python functions that can be customized.
The difference is that control calls take a scrolls statement as an argument, and command
calls do not. Control call names MUST start with `!`. Other than that, the same naming
rules apply, no `$ ! ( ) { } ; #` (`!` may not appear anywhere but the start). Note that 
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

### Comments

Comments may be defined with the `#` character.

```
# This is a comment.
print hello world# comments can border literals, though it doesn't look great.
print foo bar #blah () {} comments can contain any character, and last until end of line.
```

### Variable Substitution

Scrolls supports variable expansion with `$`. Variables may be set with the built-in `set`
command call.

```
set test hello world
print $test

# prints:
# hello world
```

There is also a built in `for` control call, which will run a code block repeatedly
with different parameters.

```
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

### Datatypes

Scrolls is a weakly typed language, and its only real datatype is the string (specifically
utf-8 strings). All calls will convert to other datatypes internally as needed, and will
always return strings. That being said, built-in Scrolls calls will follow certain rules
when interpreting strings.

#### Numeric

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

#### Strings

Strings are the default datatype in Scrolls, and do not need to be enclosed in quotes.
If you need to include special characters or newlines in strings, you may use double
quotes:

```
print "hello world (foo bar) {this is fine}"
print "spacing      is      preserved"
print "newlines
are
allowed
too"
```

In order to include characters like `"`, you can use escape sequences:

```
# prints "quoted string"
print "\"quoted string\""
```

Nearly everything is a string, including all call names and variable references. As such,
call names may be stored in variables as a primitive form of indirection:

```
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

```
# Does the same thing as the above example
!"for"("operator" "in" "+" "-" "*" "/") {
  "print" $($"operator" "5" "8")
}
```

#### Structures (Lists, etc.)

There are no dedicated datastructures in Scrolls, however there is built in support
for manipulating space-delimited lists of strings referred to as *vectors*. For example,
here is how to iterate over each element in a vector:

```
set vector 1 2 3 4 5
!while($(not $(vempty? $vector))) {
  print $(vhead $vector)      # vhead returns the first item in a vector
  set vector $(vtail $vector) # vtail returns all but the first item in a vector
}
```
Of course, this operation is common enough that a dedicated control structure is
provided for it:
```
set vector 1 2 3 4 5
!for(x in $^vector) {
  print $x
}
```

`$^` is the *vector expansion operator*. It will split the value of the expansion
along spaces, and pass the pieces as separate arguments. The best way to illustrate the
difference is with an example:

```
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

```
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

```
# will always print 1 2 3 4 5
set vector 1 2 3 4 5
print $(shuffle $vector) # shuffle is only taking 1 argument here

# will shuffle as expected, ex 3 5 1 2 4
print $(shuffle $^vector) # note the added ^, shuffle is taking each element
                          # in $vector as its own argument
```

## API Documentation

TODO, sorry!

## Acknowledgements

- [hikari-lightbulb](https://github.com/tandemdude/hikari-lightbulb) by tandemdude, which inspired the default commands interface 
  for Scrolls (see [here](scrolls/commands.py)).