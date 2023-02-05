# Changelog
All notable changes to this project will be documented in this file.

- The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
- This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2023-02-05
**Beta Release** - `0.x.y` should not be considered stable, and backwards
incompatible changes may be made at any time.

### FIXED
- Fixed incomplete comment for `scrolls.unified_config`.
- Fixed `scrolls` module missing `UnifiedCommandSettingHandler` at top level.

## [0.3.0] - 2023-02-05
**Beta Release** - `0.x.y` should not be considered stable, and backwards
incompatible changes may be made at any time.

### ADDED
- Add `!else` and `!elif` builtins.
- Add `scrolls.CallContext.else_signal` for plugin support of `!else`.
- Add `scrolls.InterpreterContext.parent_call_context`.
- Add math builtins:
  - `**`: Exponentiation
  - `sqrt`: Square root
  - `round`, `floor`, `ciel`: Rounding
- Add `vlen` builtin.
- Add a base call context (command, name `__main__`, no arguments) for toplevel code.
- Add `use-unified-commands`, which allows expansions to be used as commands.

### CHANGED
- Empty parenthesis are now optional for control calls: `!else() -> !else`

### REMOVED
- Remove `scrolls.InterpreterContext.in_call`, because it no longer makes sense
  to ask whether the interpreter is in a call or not due to base context.

### FIXED
- Fix oversight in `scrolls.InterpreterContext.interpret_ast` leading to
  incomplete initialization of context for full AST execution.

## [0.2.0] - 2022-08-16
**Beta Release** - `0.x.y` should not be considered stable, and backwards
incompatible changes may be made at any time.

### ADDED
- Add `scrolls.Tokenizer.set_comments_enable`.
- Add `scrolls.Tokenizer.set_newlines_separate_strings`.

### FIXED
- Fix `scrolls.Tokenizer.set_quoted_literals_enable` not disabling
  quoted literals when called with `False`.
- Fix KeyError on partially filled optional args for callbase commands.

## [0.1.1]
**Beta Release** - `0.x.y` should not be considered stable, and backwards
incompatible changes may be made at any time.

### FIXED
- Fix issue in `scrolls.ext.callbase` causing `GREEDY` options not returning
  a `Sequence` if only one argument is parsed.
- Fix `scrolls.ext.callbase` not included in package.

## [0.1.0] - 2022-05-05
**Beta Release** - This version should not be considered stable, and backwards
incompatible changes may be made at any time.

### ADDED
Initial release.