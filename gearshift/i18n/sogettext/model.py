try:
    from sqlobject import *
    from datetime import *

    from gearshift.database import PackageHub

    # create a PackageHub
    hub = PackageHub("gearshift.i18n.sogettext")
    __connection__ = hub

    class TG_Domain(SQLObject):

        name = StringCol(alternateID=True)
        messages = MultipleJoin("TG_Message")

        class sqlmeta:
            table="tg_i18n_domain"
            defaultOrder="name"

    class TG_Message(SQLObject):

        name = UnicodeCol()
        text = UnicodeCol(default="")
        domain = ForeignKey("TG_Domain")
        locale = StringCol(length=15)
        created= DateTimeCol(default=datetime.now)
        updated=DateTimeCol(default=None)

        def _set_text(self, text):

            self._SO_set_text(text)
            self.updated = datetime.now()

        class sqlmeta:
            table="tg_i18n_message"
            defaultOrder="name"

except ImportError:
    pass
