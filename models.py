from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import ForeignKey, PrimaryKeyConstraint
from sqlalchemy.types import TypeDecorator, BLOB, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String
import numbers
import json

# jso: An object which can be encoded in JSON

def attr_spec(k):
    if not isinstance(k, basestring):
        return k
    else:
        return k, None

def rgattr_spec(o, spec):
    if spec == None:
        return ((attr, None) for attr in o)
    else:
        return (attr_spec(k) for k in spec)

def toJso(o, spec=None):
    if isinstance(o, (basestring, numbers.Number)):
        return o
    if isinstance(o, list):
        result = []
        for v in o:
            result.append(toJso(v, spec))
        return result

    if isinstance(o, dict):
        result = {}
        for attr, specNew in rgattr_spec(o, spec):
            result[attr] = toJso(o[attr], specNew)
        return result
    if spec == None and hasattr(o, '__json_spec__'):
        spec = o.__json_spec__
    if spec != None:
        result = {}
        for attr, specNew in rgattr_spec(o, spec):
            result[attr] = toJso(getattr(o, attr), specNew)
        return result

    raise Exception("Don't know how to convert " + str(type(o)) + " to json: " + repr(o))

def fromJso(jso, classes, spec=None):
    if classes == None:
        return jso

    if isinstance(classes, type):
        classes = (classes,)

    if spec == None:
        spec = classes[0].__json_spec__

    if len(classes) == 1:
        if hasattr(classes[0], '__json_classmap__'):
            classmap = classes[0].__json_classmap__
        else:
            classmap = {}
    else:
        classmap = classes[1]

    def set_attr(o, k, v):
        if isinstance(o, dict):
            o[k] = v
        else:
            setattr(o, k, v)

    if isinstance(jso, dict):
        o = classes[0]()
        for attr, specNew in (attr_spec(k) for k in spec):
            set_attr(o, attr, fromJso(jso[attr], classmap.get(attr), specNew))
        return o

    if isinstance(jso, list):
        return [fromJso(v, spec, classes) for v in jso]

    return jso

class JsonSqlType(TypeDecorator):
    impl = BLOB

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = json.loads(value)
        return value

Base = declarative_base()

class Disc(Base):
    __tablename__ = 'disc'

    id = Column(Integer, primary_key=True)
    title = Column(String(128))
    url = Column(String(256))
    ktube = Column(String(10))

class Qte(Base):
    __tablename__ = 'qte'

    disc_id = Column(Integer, ForeignKey("disc.id"))
    ms_trigger = Column(Integer)
    ms_finish = Column(Integer)
    shape = Column(JsonSqlType)

    disc = relationship("Disc", backref="qtes")
    __table_args__ = (PrimaryKeyConstraint('disc_id', 'ms_trigger'),)

class EditSession(Base):
    __tablename__ = 'editsession'

    disc_id = Column(Integer, ForeignKey("disc.id"), primary_key=True)
    guid = Column(String(32))
    expires = Column(DateTime)

Disc.__json_spec__ = ('id', 'title', 'url', 'ktube', 'qtes')
Disc.__json_classmap__ = {'qtes': Qte}
Qte.__json_spec__ = ('ms_trigger', 'ms_finish', 'shape')
