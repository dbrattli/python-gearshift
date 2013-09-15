import cherrypy

def _error_handler(url='/error', internal=True):
    """Raise InternalRedirect or HTTPRedirect to the given url."""

    #cherrypy.log("CherryPy %s error (%s) for request '%s'" % (status, error_msg, url), traceback=True)
    
    ##send_exception_email()

    if internal:
        url = "%s?%s" % (url, urllib.urlencode(dict(url=cherrypy.url())))
        raise cherrypy.InternalRedirect(url)
    else:
        raise cherrypy.HTTPRedirect(url)

class ErrorTool(cherrypy.Tool):
    """Tool which is used to replace the default request.error_response."""
    
    def __init__(self, callable, name=None):
        Tool.__init__(self, None, callable, name)
    
    def _wrapper(self):
        self.callable(**self._merged_args())
    
    def _setup(self):
        """Hook this tool into cherrypy.request.
        
        The standard CherryPy request object will automatically call this
        method when the tool is "turned on" in config.
        """
        cherrypy.request.error_response = self._wrapper
        
        
class Error2Tool(cherrypy.Tool):
    """A TurboGears Flash Tool"""

    def __init__(self, commit_veto=None):        
        
        return super(TransactionTool, self).__init__("on_start_resource", 
                                                     self.begin)
                
    def begin(self):
        pass
    def end(self):
        pass    
    def _setup(self):
        conf = self._merged_args()
        p = conf.pop("priority", None)
        if p is None:
            p = getattr(self.callable, "priority", self._priority)
            
        request.hooks.attach(self._point, self.callable, priority=p, **conf)

        request.hooks.attach('before_error_response', self.error)
        
        # Lower priority for commit to run before TG EndTransactions hook
        request.hooks.attach('on_end_resource', self.end, priority=40)
        
        # Not necessary because of TG EndTransactions hook, but perhaps we 
        # could remove the hook and use this tool instead?
        request.hooks.attach('on_end_request', self.end_all, priority=50)
