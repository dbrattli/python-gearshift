import cherrypy
from cherrypy import request
from cherrypy._cpdispatch import Dispatcher, PageHandler, LateParamPageHandler

from gearshift import config
from gearshift import controllers

class RestDispatcher(Dispatcher):
    dispatch_method_name = '_cp_dispatch'
    dispatch_method_name__doc = """
    The name of the dispatch method that nodes may optionally implement
    to provide their own dynamic dispatch algorithm.
    """
    
    def __call__(self, path_info):
        """RestDispatcher must be used together with the RestController
        in order for parameters to be collected. See RestController above."""

        resource, vpath = self.find_handler(path_info)
        
        if callable(resource):
            # Use CherryPy normal dispatching for "new", "edit" etc
            Dispatcher.__call__(self, path_info)
        elif resource:
            # Set Allow header
            avail = [m for m in ["PUT", "POST", "DELETE"] if hasattr(resource, m)]
            for m in ["GET", "GET_ONE", "GET_ALL"]:
                if hasattr(resource, m):
                    avail.append("GET")
                    break # Need only one GET in allow header
                    
            if "GET" in avail and "HEAD" not in avail:
                avail.append("HEAD")
            
            avail.sort()
            cherrypy.response.headers['Allow'] = ", ".join(avail)

            # Find the subhandler
            meth = request.method.upper()
            if meth == "POST":
                # FIXME: CP 3.2
                if "_method" in request.query_string and "_method" not in request.params:
                    request.process_query_string()
                    
                # For POST we accept method overriding with _method param
                meth = request.params.pop("_method", meth)
            
            # For GET we also accept the GET_ONE or GET_ALL methods if they
            # exist. If not use try to use the default GET
            if meth == "GET":
                if getattr(request, "tg_rest_get_one", False):
                    if hasattr(resource, "GET_ONE"):
                        meth = "GET_ONE"
                elif hasattr(resource, "GET_ALL"):
                    meth = "GET_ALL"
            
            func = getattr(resource, meth, None)
            if func is None and meth == "HEAD":
                if getattr(request, "tg_rest_get_one", False):
                    func = getattr(resource, "GET_ONE", None)
                else:
                    func = getattr(resource, "GET_ALL", None)
            if func:
                # Decode any leftover %2F in the virtual_path atoms.
                vpath = [x.replace("%2F", "/") for x in vpath]
                request.handler = LateParamPageHandler(func, *vpath)
            else:
                request.handler = cherrypy.HTTPError(405)
            
            # Update any config attched on the method handler, so we can
            # expose different templates for each method etc.
            handler = request.handler
            if isinstance(handler, PageHandler) and \
                                    hasattr(handler.callable, "_cp_config"):
                request.config.update(handler.callable._cp_config)
        else:
            request.handler = cherrypy.NotFound()
            
