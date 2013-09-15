import logging
from datetime import datetime

from google.appengine.ext import db

from gearshift import config
from gearshift.util import load_class
from gearshift.visit.api import BaseVisitManager, Visit

log = logging.getLogger("gearshift.visit.aevisit")

visit_class = None

class AppEngineVisitManager(object):

    def __init__(self, timeout):
        global visit_class
        visit_class_path = config.get("tools.visit.aeprovider.model",
            "gearshift.visit.aevisit.TG_Visit")
        visit_class = load_class(visit_class_path)
        if not visit_class:
            log.error("Error loading \"%s\"" % visit_class_path)
        
        self.create_model()
        self.timeout = timeout

    def create_model(self):
        # Nothing to do here
        return

    def new_visit_with_key(self, visit_key):
        expiry = datetime.now()+self.timeout
        
        key = "VISIT:%s" % visit_key # Sanitize to meet GAE requirements
        visit = visit_class(key_name=key, expiry=expiry)
        visit.put()

        return Visit(visit_key, True)

    def visit_for_key(self, visit_key):
        """Return the visit for this key.

        Returns None if the visit doesn't exist or has expired.

        """
        visit = visit_class.lookup_visit(visit_key)
        now = datetime.now()
        if not visit or visit.expiry < now:
            return None
        
        # Visit hasn't expired, extend it. On the GAE we don't have threads and
        # it might be a better approach to set a long expiry (e.g. 14 days) 
        # and not extend it to avoid extending visits on every request
        if config.get("tools.visit.extend_timeout", True):
            visit.expiry = now+self.timeout
            visit.put()
        
        return Visit(visit_key, False)

class TG_Visit(db.Model):

    created = db.DateTimeProperty(auto_now=True)
    expiry = db.DateTimeProperty()

    @classmethod
    def lookup_visit(cls, visit_key):
        key = "VISIT:%s" % visit_key
        return cls.get_by_key_name(key)
