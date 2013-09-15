from datetime import datetime
from gearshift.database import mapper, metadata
from sqlalchemy import Table, Column, ForeignKey
from sqlalchemy import String, Unicode, Integer, DateTime
from sqlalchemy.orm import relation, backref

tg_domain_table = Table('tg_i18n_domain', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', Unicode, unique=True),
    )

tg_message_table = Table('tg_i18n_message', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', Unicode),
    Column('text', Unicode, default=u""),
    Column('domain_id', Integer, ForeignKey(tg_domain_table.c.id)),
    Column('locale', String(length=15)),
    Column('created', DateTime, default=datetime.now),
    Column('updated', DateTime, default=None),
)

class TG_Domain(object):
    pass

class TG_Message(object):
    pass

mapper(TG_Domain, tg_domain_table,
        properties=dict(
            messages=relation(
                TG_Message, backref='domain')
            ))

mapper(TG_Message, tg_message_table,
        properties=dict())

