from datetime import datetime

from sqlobject import SQLObject, SQLObjectNotFound, StringCol, DateTimeCol
from sqlobject.sqlbuilder import Update

from gearshift import config
from gearshift.database.so import PackageHub
from gearshift.util import load_class
from gearshift.visit.api import BaseVisitManager, Visit

hub = PackageHub("gearshift.visit")
__connection__ = hub

import logging

log = logging.getLogger("gearshift.visit.sovisit")

visit_class = None


class SqlObjectVisitManager(BaseVisitManager):

    def __init__(self, timeout):
        global visit_class
        visit_class_path = config.get("tools.visit.soprovider.model",
            "gearshift.visit.sovisit.TG_Visit")
        visit_class = load_class(visit_class_path)
        if visit_class:
            log.info("Successfully loaded \"%s\"" % visit_class_path)
        # base-class' __init__ triggers self.create_model, so mappers need to
        # be initialized before.
        super(SqlObjectVisitManager, self).__init__(timeout)

    def create_model(self):
        try:
            # Create the Visit table if it doesn't already exist
            hub.begin()
            visit_class.createTable(ifNotExists=True)
            hub.commit()
            hub.end()
        except KeyError:
            # No database configured...
            log.info("No database is configured: Visit Tracking is disabled.")
            return

    def new_visit_with_key(self, visit_key):
        hub.begin()
        visit = visit_class(visit_key=visit_key,
            expiry=datetime.now()+self.timeout)
        hub.commit()
        hub.end()
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
        if hub is None: # if VisitManager extension wasn't shutted down cleanly
            return
        hub.begin()
        try:
            conn = hub.getConnection()
            try:
                # Now update each of the visits with the most recent expiry
                for visit_key, expiry in queue.items():
                    u = Update(visit_class.q,
                        {visit_class.q.expiry.fieldName: expiry},
                        where=(visit_class.q.visit_key==visit_key))
                    conn.query(conn.sqlrepr(u))
                hub.commit()
            except:
                hub.rollback()
                raise
        finally:
            hub.end()

class TG_Visit(SQLObject):

    class sqlmeta:
        table = "tg_visit"

    visit_key = StringCol(length=40, alternateID=True,
            alternateMethodName="by_visit_key")
    created = DateTimeCol(default=datetime.now)
    expiry = DateTimeCol()

    @classmethod
    def lookup_visit(cls, visit_key):
        try:
            return cls.by_visit_key(visit_key)
        except SQLObjectNotFound:
            return None
