import logging
from datetime import datetime

import couchdb
from couchdb.client import ResourceConflict
from couchdb.schema import Document, Schema, BooleanField, DateTimeField, \
                           IntegerField, TextField, DictField, ListField, View

from gearshift import config
from gearshift.util import load_class
from gearshift.visit.api import BaseVisitManager, Visit
from gearshift.database.cd import datastore

log = logging.getLogger("gearshift.visit.cdvisit")

visit_class = None

class CouchDbVisitManager(BaseVisitManager):

    def __init__(self, timeout):
        global visit_class
        visit_class_path = config.get("tools.visit.cdprovider.model",
            "gearshift.visit.cdvisit.TG_Visit")
        visit_class = load_class(visit_class_path)
        if not visit_class:
            log.error("Error loading \"%s\"" % visit_class_path)
        
        self.create_model()
        self.timeout = timeout
        
        super(CouchDbVisitManager, self).__init__(timeout)

    def create_model(self):
        # Nothing to do here
        return

    def new_visit_with_key(self, visit_key):
        expiry = datetime.now()+self.timeout
        
        key = "VISIT:%s" % visit_key
        visit = visit_class(id=key, expiry=expiry)
        try:
            visit.store(datastore.db)
        except ResourceConflict:
            log.error("Error storing new visit: %s" % key)
        except AttributeError:
            # AttributeError: 'NoneType' object has no attribute 'makefile'
            log.error("CouchDB server is down")
            return None
        
        return Visit(visit_key, True)

    def visit_for_key(self, visit_key):
        """Return the visit for this key.

        Returns None if the visit doesn't exist or has expired.

        """
        visit = visit_class.lookup_visit(visit_key)
        now = datetime.now()
        
        if visit is None or visit.expiry < now:
            return None
        
        # Visit hasn't expired, extend it
        self.update_visit(visit_key, now+self.timeout)
        return Visit(visit_key, False)
        
    def update_queued_visits(self, queue):
        for visit_key, expiry in queue.items():
            visit = visit_class.load(datastore.db, "VISIT:%s" % visit_key)
            visit.expiry = expiry
            visit.store(datastore.db)
        
class TG_Visit(Document):
    type = TextField(default="Visit")

    created = DateTimeField(default=datetime.now)
    expiry = DateTimeField()

    @classmethod
    def lookup_visit(cls, visit_key):
        key = "VISIT:%s" % visit_key
        return cls.load(datastore.db, key)
