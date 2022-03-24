import nox
from nox import options

options.sessions = ["format", "mypy"]


@nox.session
def mypy(session):
    session.install("mypy")
    session.run("mypy", ".")


@nox.session
def format(session):
    session.install("isort")
    session.run("isort", "scrolls")
