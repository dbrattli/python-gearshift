import logging

import cherrypy
from cherrypy import request
import transaction # Zope transaction
from repoze.tm import TM

from gearshift import database
from gearshift.database import so

log = logging.getLogger("gearshift.database")

def commit_veto(environ, status, headers):
    """
    This hook is called by repoze.tm in case we want to veto a commit
    for some reason. Return True to force a rollback.

    By default we veto if the response's status code is an error code.
    Override this method, or monkey patch the instancemethod, to fine
    tune this behaviour.
    """
    # CherryPY internal redirects have no status
    if status:
        # CherryPy status is either an int or a str
        if isinstance(status, str):
            status = int(status.split()[0])

        # Accept status codes between 200 and 399. CherryPy HTTP redirects
        # will give 302 or 303, so we must make sure we accept those.
        ret = not (200 <= status < 400)
    else:
        ret = False
    return ret

class TransactionTool(cherrypy.Tool):
    """A TurboGears Transaction tool using repose.tm"""

    def __init__(self, commit_veto=None):
        # Embed repoze.tm.TM for now
        self.tm = TM(application=None, commit_veto=commit_veto)

        log.info("Transaction Tool initialized")

        cherrypy.engine.subscribe('stop', self.end_all)

        return super(TransactionTool, self).__init__("on_start_resource",
                                                     self.begin)

    def begin(self):
        request.in_transaction = True
        t = transaction.begin()

        so_dm = so.SODataManager()
        t.join(so_dm)

    def end(self):
        # ZODB 3.8 + has isDoomed
        if hasattr(transaction, 'isDoomed') and transaction.isDoomed():
            self.tm.abort()
        if self.tm.commit_veto is not None:
            try:
                if self.tm.commit_veto(None, cherrypy.response.status,
                                       cherrypy.response.headers):
                    log.debug("Commit veto, calling abort!")
                    self.tm.abort()
            except:
                self.tm.abort()
                raise
            else:
                self.tm.commit()
        else:
            self.tm.commit()
        request.in_transaction = False
    end.failsafe = True

    def end_all(self):
        so.end_all()
        request.in_transaction = False
    end_all.failsafe = True

    def error(self):
        self.tm.abort()

    def _setup(self):
        conf = self._merged_args()
        p = conf.pop("priority", None)
        if p is None:
            p = getattr(self.callable, "priority", self._priority)

        request.hooks.attach(self._point, self.callable, priority=p, **conf)

        request.hooks.attach('before_error_response', self.error)
        request.hooks.attach('on_end_request', self.end, priority=40)        
        request.hooks.attach('on_end_request', self.end_all, priority=50)

cherrypy.tools.transactions = TransactionTool(commit_veto) 
