import cherrypy
from cherrypy import request
from cherrypy._cptools import ErrorTool

from gearshift.util import Enum

#from gearshift.tools.errorhandling import _error_handler

FailsafeSchema = Enum("none", "values", "map_errors", "defaults")

def error_handler(error_func):
    def decorate(func):
        def error_wrapper(*args, **kwargs):           
            # Check for errors
            if hasattr(request, 'validation_errors') and request.validation_errors:
                # Call error handler
                kwargs['tg_errors'] = request.validation_errors
                params = error_func(*args, **kwargs)
            else:
                # Call default handler
                params = func(*args, **kwargs)
            return params
        return error_wrapper

    return decorate

#cherrypy.tools.exception = ErrorTool(_error_handler)
#exception_handler = cherrypy.tools.exception
exception_handler = None
