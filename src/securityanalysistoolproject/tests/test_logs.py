from core.logging_utils import LoggingUtils

def test_logs(get_db_client):
    LOGGR = LoggingUtils.get_logger()
    LOGGR.debug('debug test message')
    LOGGR.info('info test message')
    LOGGR.warning('warning tet message')
    LOGGR.error('error test message')
    LOGGR.critical('critical test message')                