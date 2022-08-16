# Changelog
All notable changes to this project will be documented in this file.

- The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
- This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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