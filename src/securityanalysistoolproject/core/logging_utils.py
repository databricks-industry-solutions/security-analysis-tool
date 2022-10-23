'''logging module'''
import logging
import os
import sys
import platform

class LoggingUtils():
    '''Logging utils helper'''
    loglevel = logging.INFO

    @classmethod
    def set_logger_level(cls, loglevel_v):
        '''set the logger level before calling get_logger'''
        cls.loglevel=loglevel_v

    #DEBUG < INFO < WARNING < ERROR < CRITICAL
    @classmethod
    def get_logger(cls, modname='_profiler_'):
        '''get logger object'''
        logpath=''
        if platform.system()=='Darwin':
            logpath='./Logs/dbrprofiler.log'
            if not os.path.isdir('./Logs/'):
                os.makedirs('./Logs/')
        else:
            logpath='/var/log/dbrprofiler.log'

        # Create a custom logger
        logger = logging.getLogger(modname)

        if logger.handlers == []:
            # Create handlers
            c_handler = logging.StreamHandler(sys.stdout)
            f_handler = logging.FileHandler(logpath)
            # Create formatters and add it to handlers
            c_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            f_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            c_handler.setFormatter(c_format)
            f_handler.setFormatter(f_format)

            # Add handlers to the logger
            logger.addHandler(c_handler)
            logger.addHandler(f_handler)
        logger.setLevel(cls.loglevel)
        return logger


    #DEBUG < INFO < WARNING < ERROR < CRITICAL
    # pylint: disable=multiple-statements
    @staticmethod
    def get_log_level( vloglevel):
        '''get log level that is set'''
        vloglevel=vloglevel.upper()
        if vloglevel == "DEBUG": return logging.DEBUG
        elif vloglevel == "INFO": return logging.INFO
        elif vloglevel == "WARNING": return logging.WARNING
        elif vloglevel == "ERROR": return logging.ERROR
        elif vloglevel == "CRITICAL": return logging.CRITICAL
    # pylint: enable=multiple-statements



    # def check_error(response, ignore_error_list=default_ignore_error_list):
    #   default_ignore_error_list =['RESOURCE_ALREADY_EXISTS']
    #   return ('error_code' in response and response['error_code'] not in ignore_error_list) \
    #             or ('error' in response and response['error'] not in ignore_error_list) \
    #             or (type(response)==dict and response.get('resultType', None) == 'error' \
    #                   and 'already exists' not in response.get('summary', None))
