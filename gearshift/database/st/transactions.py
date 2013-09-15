import logging

import cherrypy
from cherrypy import request

log = logging.getLogger("gearshift.database")

class StormTool(cherrypy.Tool):
    """Transaction tool"""
    def __init__(self):
        super(StormTool, self).__init__("on_start_resource", self.begin)

    def begin(self):
        request.rolledback = False

    def commit(self):
        try:
            store = cherrypy.thread_data.store
        except AttributeError:
            log.error("Found no database connection to commit")
            return

        if hasattr(request, "rolledback") and not request.rolledback:
            try:
                store.commit()
            except Exception:
                store.rollback()
                log.error("ROLLBACK - " + cherrypy._cperror.format_exc())

    def rollback(self):
        try:
            store = cherrypy.thread_data.store
        except AttributeError:
            log.error("Found no database connection to rollback")
            return

        store.rollback()
        log.error("ROLLBACK - " + cherrypy._cperror.format_exc())
        request.rolledback = True

    def _setup(self):
        conf = self._merged_args()
        p = conf.pop("priority", None)
        if p is None:
            p = getattr(self.callable, "priority", self._priority)
        cherrypy.request.hooks.attach(self._point, self.callable, priority=p, **conf)

        cherrypy.request.hooks.attach('before_error_response', self.rollback)
        cherrypy.request.hooks.attach('on_end_request', self.commit, priority=60)

cherrypy.tools.storm = StormTool()
