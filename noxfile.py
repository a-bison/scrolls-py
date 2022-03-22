import nox


@nox.session
def mypy(session):
    session.install("mypy")
    session.run("mypy", ".")
