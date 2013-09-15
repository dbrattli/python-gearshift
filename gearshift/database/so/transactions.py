import cherrypy

from gearshift.database import so

class SOTransactionTool(cherrypy.Tool):
    """Transaction tool"""
    def __init__(self):
        return super(SOTransactionTool, self).__init__("on_start_resource", self.begin)
        
    def begin(self):
        cherrypy.request.in_transaction = True        

    def _setup(self):
        conf = self._merged_args()
        p = conf.pop("priority", None)
        if p is None:
            p = getattr(self.callable, "priority", self._priority)
        cherrypy.request.hooks.attach(self._point, self.callable, priority=p, **conf)

        cherrypy.request.hooks.attach('before_error_response', so.rollback_all)
        cherrypy.request.hooks.attach('on_end_request', so.commit_all, priority=60)
        cherrypy.request.hooks.attach('on_end_request', so.end_all, priority=70)
        
cherrypy.tools.transactions = SOTransactionTool()

