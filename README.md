<p align="center">
  <img src="https://raw.githubusercontent.com/a-bison/scrolls-py/0095423d692bb18d6b3f01125f32ddad710015d9/media/scrolls-logo.png" width="200"/>
</p>

<h1 align="center">Scrolls</h1>
Scrolls is a small interpreter originally designed to allow users of my discord bots to
make custom commands. It prioritizes control over the interpreter to help prevent abuse,
while still allowing tight integration with python code.

## Links

- Documentation: https://a-bison.github.io/scrolls-py-docs/
- Source Code: https://github.com/a-bison/scrolls-py
- PyPI: https://pypi.org/project/scrolls-py/

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

## Getting Started

Check out the [Links](#Links) section above.

### Installing

Scrolls may be installed through `pip`:

**Linux**
```
python3 -m pip install scrolls-py
```

**Windows**
```
py -3 -m pip install scrolls-py
```

### Command Line Usage

The module comes with a built-in interpreter that may be invoked by executing the
module. (Note that the linux version will be used from now on.)

```
python3 -m scrolls FILE
```

Try running some of the examples:
```
python3 -m scrolls ./examples/arithmetic.scrl
```

If no file is specified, the interpreter will run in interactive mode:
```
python3 -m scrolls
```

### Example Code

Here are some sample programs showcasing the basic syntax of Scrolls. See the examples directory for more.

[**Fizzbuzz**](https://en.wikipedia.org/wiki/Fizz_buzz)
```scrolls
!def(divisible? a b) {
    return $(eq? 0 $(% $a $b))
}

!for(n in $^(rangev 1 101)) {
    !if($(divisible? $n 15)) {
        print "FizzBuzz"
    } !elif($(divisible? $n 3)) {
        print "Fizz"
    } !elif($(divisible? $n 5)) {
        print "Buzz"
    } !else {
        print $n
    }
}
```

**Nth [Fibonacci Number](https://en.wikipedia.org/wiki/Fibonacci_number)**
```scrolls
print "This will calculate fib N where fib 0 = 0, fib 1 = 1"
print "Enter N."
input n

set output_msg "Fibonacci number" $n "is"

!if($(< $n 2)) {
    print $^output_msg $n
    stop
}

set fib_prev 0
set fib 1
set i 2

!while($(<= $i $n)) {
    set tmp $fib_prev
    set fib_prev $fib
    set fib $(+ $tmp $fib)
    set i $(+ $i 1)
}

print $^output_msg $fib
```

**Syntax Quirks**
```scrolls
# In scrolls everything is a string
"print" "Everything is a string:"
!"for"("operator" "in" "+" "-" "*" "/") {
  "print" $($"operator" "5" "8")
}
```

***String Escapes***
```scrolls
print "\"test escapes\"\n\ttabbed\n\tlines\nunicode is supported: \u0398hello\u0398\n"
```

### Programmatic Usage

Scrolls may be embedded into any python program:
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
print "Please enter your name:"
input name
!repeat(4) {
    print "Hello," $(cat $name "!")
}
"""
interpreter.run(script)
```

## Acknowledgements

- [hikari-lightbulb](https://github.com/tandemdude/hikari-lightbulb) by tandemdude, which inspired the
  CallBase extension (see [here](https://github.com/a-bison/scrolls-py/blob/cde0f5b9a88925541cc85c00a4a0e459f54a4f56/scrolls/ext/callbase.py)).