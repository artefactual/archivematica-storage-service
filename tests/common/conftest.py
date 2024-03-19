import pytest


@pytest.fixture(autouse=True)
def do_not_reset_the_root_logger(mocker):
    # Some management commands suppress logging from models/package.py
    # by calling logging.config.dictConfig directly which breaks the caplog
    # fixture. See https://github.com/pytest-dev/pytest/discussions/11011
    #
    # This avoids breaking the caplog fixture when those management command
    # modules are imported or called during tests.
    mocker.patch("logging.config")
