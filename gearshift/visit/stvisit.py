from datetime import datetime

import storm
from storm.locals import *
import cherrypy

from gearshift import config
from gearshift.util import load_class
from gearshift.visit.api import BaseVisitManager, Visit

import logging

log = logging.getLogger("gearshift.visit.sovisit")

visit_class = None

class StormVisitManager(BaseVisitManager):

    def __init__(self, timeout):
        global visit_class
        visit_class_path = config.get("tools.visit.stprovider.model",
            "gearshift.visit.stvisit.TG_Visit")
        visit_class = load_class(visit_class_path)
        if visit_class:
            log.info("Successfully loaded \"%s\"" % visit_class_path)
        # base-class' __init__ triggers self.create_model, so mappers need to
        # be initialized before.
        super(StormVisitManager, self).__init__(timeout)

    def create_model(self):
        return

    def new_visit_with_key(self, visit_key):
        store = cherrypy.thread_data.store

        visit = visit_class(visit_key=visit_key,
            expiry=datetime.now()+self.timeout)
        store.add(visit)
        return Visit(visit_key, True)

    def visit_for_key(self, visit_key):
        """Return the visit for this key.

        Returns None if the visit doesn't exist or has expired.

        """
        visit = visit_class.lookup_visit(visit_key)
        now = datetime.now()
        if not visit or visit.expiry < now:
            return None
        # Visit hasn't expired, extend it
        self.update_visit(visit_key, now+self.timeout)
        return Visit(visit_key, False)

    def update_queued_visits(self, queue):
        # TODO: get_connection()
        database = create_database(config.get('storm.dburi'))
        store = Store(database)

        try:
            try:
                # Now update each of the visits with the most recent expiry
                for visit_key, expiry in queue.items():
                    visit_key = unicode(visit_key)
                    store.find(visit_class, visit_class.visit_key == visit_key).set(expiry=expiry)
                store.commit()
            except:
                store.rollback()
                raise
        finally:
            store.close()

class TG_Visit(object):

    __storm_table__ = "tg_visit"

    id = Int(primary=True)
    visit_key = Unicode()
    created = DateTime(default=datetime.now)
    expiry = DateTime()

    @classmethod
    def lookup_visit(cls, visit_key):
        try:
            return cls.by_visit_key(visit_key)
        except SQLObjectNotFound:
            return None

    @classmethod
    def by_visit_key(cls, visit_key):
        return store.find(cls, cls.visit_key == visit_key).one()
