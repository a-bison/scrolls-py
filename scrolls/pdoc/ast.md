# Using The Parser

## Quickstart

Often, all you need to do is parse a script and get the syntax tree. To do this:

```py
import scrolls

script = "..."
tokenizer = scrolls.Tokenizer(script)
ast = scrolls.parse_scroll(tokenizer)
```

The `AST` ([Abstract Syntax Tree](https://en.wikipedia.org/wiki/Abstract_syntax_tree)) is a generic structure
that represents the semantic content of a script. This structure is what is actually interpreted by
the Scrolls interpreter. See `scrolls.interpreter` for more detail on `AST` interpretation. See the following
sections for a more detailed description of the parsing process.

## Tokenizing

Parsing is done in two stages, tokenizing, and parsing. First, the
`Tokenizer` is used to break a script into a list of pieces, assigning
meaning to each. These pieces are called tokens (see `Token`).

```pycon
>>> import scrolls
>>> script = """
... !repeat(4) {
...     print "Hello, world!"
... }
... """
>>> tokenizer = scrolls.Tokenizer(script)
>>> tokens = tokenizer.get_all_tokens()
>>> for tok in tokens:
...     print(tok)
...
CONTROL_SIGIL:'!'
STRING_LITERAL:'repeat'
OPEN_PAREN:'('
STRING_LITERAL:'4'
CLOSE_PAREN:')'
OPEN_BLOCK:'{'
COMMAND_SEP:'\n'
STRING_LITERAL:'print'
STRING_LITERAL:'Hello, world!'
COMMAND_SEP:'\n'
CLOSE_BLOCK:'}'
EOF:''
>>>
```

Each token represents a `TokenType` and an associated value. For instance,
the second token shown above, `STRING_LITERAL:'repeat'` is a string literal token, with the value `repeat`.

.. NOTE::
    Typically, you won't need to pull tokens from the `Tokenizer`, just configure it. It's just
    helpful to understand what it actually does.

## Parsing

The tokens are then passed to the parser, the entry point of which is `parse_scroll`. This function will
automatically pull tokens from a `Tokenizer` object, and generate the corresponding `AST`. 

```pycon
>>> import scrolls
>>> script = """
... !repeat(4) {
...     print "Hello, world!"
... }
... """
>>> tokenizer = scrolls.Tokenizer(script)
>>> ast = scrolls.parse_scroll(tokenizer)
>>> print(ast.prettify())
{
    "_tok": "None",
    "_type": "ROOT",
    "children": [
        {
            "_tok": "CONTROL_SIGIL:'!'",
            "_type": "CONTROL_CALL",
            "children": [
                {
                    "_tok": "STRING_LITERAL:'repeat'",
                    "_type": "STRING",
                    "children": []
                },
                {
                    "_tok": "OPEN_PAREN:'('",
                    "_type": "CONTROL_ARGUMENTS",
                    "children": [
                        {
                            "_tok": "STRING_LITERAL:'4'",
                            "_type": "STRING",
                            "children": []
                        }
                    ]
                },
                {
                    "_tok": "OPEN_BLOCK:'{'",
                    "_type": "BLOCK",
                    "children": [
                        {
                            "_tok": "STRING_LITERAL:'print'",
                            "_type": "COMMAND_CALL",
                            "children": [
                                {
                                    "_tok": "STRING_LITERAL:'print'",
                                    "_type": "STRING",
                                    "children": []
                                },
                                {
                                    "_tok": "STRING_LITERAL:'Hello, world!'",
                                    "_type": "COMMAND_ARGUMENTS",
                                    "children": [
                                        {
                                            "_tok": "STRING_LITERAL:'Hello, world!'",
                                            "_type": "STRING",
                                            "children": []
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]
}
```

AST instances consist of a tree of `ASTNode` objects. Each node keeps track of the token that triggered 
its generation. This is used primarily for informative display of errors during interpreter runtime.

Scrolls uses a [recursive descent](https://en.wikipedia.org/wiki/Recursive_descent_parser)
approach, implemented with [parser combinators](https://en.wikipedia.org/wiki/Parser_combinator).
The parsing scheme of Scrolls is intentionally barebones, and does not include any control structures
at all. Instead, all identifiers are `ASTNodeType.STRING`, which are interpreted at runtime based on
their location in the syntax tree.
