import pytest
import logging

@pytest.fixture(scope='session')
def logger():
    logger = logging.getLogger('pytest_logger')
    logger.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    ch.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(ch)

    return logger