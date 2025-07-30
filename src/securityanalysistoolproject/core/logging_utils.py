'''logging module'''
import logging
import os
import sys
import platform
#from databricks.sdk.runtime import dbutils

class LoggingUtils():
    '''Logging utils helper'''
    loglevel = logging.INFO

    @classmethod
    def set_logger_level(cls, loglevel_v):
        '''set the logger level before calling get_logger'''
        cls.loglevel = loglevel_v

    #DEBUG < INFO < WARNING < ERROR < CRITICAL
    @classmethod
    def get_logger(cls, modname='_profiler_'):
        '''get logger object'''
        log_base_dir = f"{cls.basePath()}/logs"

        if not os.path.isdir(log_base_dir):
            os.makedirs(log_base_dir)

        # logpath='/var/log/dbrprofiler.log'
        logpath = f"{log_base_dir}/sat.log"

        if not os.path.exists(logpath):
            with open(logpath, 'w') as f:
                f.write("")
        

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
    def get_log_level(vloglevel):
        '''get log level that is set'''
        vloglevel = vloglevel.upper()
        if vloglevel == "DEBUG": return logging.DEBUG
        elif vloglevel == "INFO": return logging.INFO
        elif vloglevel == "WARNING": return logging.WARNING
        elif vloglevel == "ERROR": return logging.ERROR
        elif vloglevel == "CRITICAL": return logging.CRITICAL
    # pylint: enable=multiple-statements
    


    @staticmethod
    def basePath():
        path = os.getcwd()
        ind=path.find("/notebooks")
        if ind==-1:
            return("~/temp")
        path = path[: ind]
        if path.startswith('/Workspace'):
            return(f'{path}')
        return f"/Workspace{path}"
    
 