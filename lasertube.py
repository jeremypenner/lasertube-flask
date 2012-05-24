import flask
from flask import g, session, request, abort, render_template
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid
import json
import models
from datetime import datetime, timedelta

DATABASE = 'sqlite:///lasertube.db'
DEBUG = True
SECRET_KEY = "barglargl"
USERNAME = 'admin'
PASSWORD = 'password'
SWF_DIR = 'C:/dev/flash/LaserTube/bin'

app = flask.Flask(__name__)
app.config.from_object(__name__)

engine = create_engine(app.config['DATABASE'])
Session = sessionmaker(bind=engine)

def connect_db():
    return Session()

def init_db():
    models.Base.metadata.create_all(engine)

@app.before_request
def before_request():
    g.db = connect_db()

@app.teardown_request
def teardown_request(e):
    g.db.close()

def requires_login(dg):
    def func(*args, **kwargs):
        if not session.get('logged_in'):
            abort(401)
        return dg(*args, **kwargs)
    func.__name__ = dg.__name__
    return func

def verify_edit(dg):
    def func(id, *args, **kwargs):
        try:
            edit = g.db.query(models.EditSession).filter_by(disc_id=id).one()
        except:
            return flask.jsonify(err='invalid')
        if edit.guid != request.json['csrf'] or edit.expires < datetime.utcnow():
            g.db.delete(edit)
            g.db.commit()
            return flask.jsonify(err='expired')
        g.session = create_session(id)
        return dg(id, *args, **kwargs)
    func.__name__ = dg.__name__
    return func

def create_session(disc_id):
    g.db.query(models.EditSession).filter_by(disc_id=disc_id).delete()
    edit = models.EditSession()
    edit.disc_id = disc_id
    edit.guid = uuid.uuid4().hex
    edit.expires = datetime.utcnow() + timedelta(hours=1)
    g.db.add(edit)
    g.db.commit()
    return edit

@app.route("/")
def list_discs():
    entries = [{'id': row[0], 'title': row[1]} for row in g.db.query(models.Disc.id, models.Disc.title)]
    return render_template('show_discs.html', entries=entries, fShowEdit=session.get('logged_in'))

@app.route("/add", methods=['POST'])
@requires_login
def add_disc():
    # if not session.get('logged_in'):
    #     abort(401)
    disc = models.fromJso(request.form, models.Disc, ('title', 'url', 'ktube'))
    g.db.add(disc)
    g.db.commit()
    flask.flash("New entry was successfully posted")
    return flask.redirect(flask.url_for('list_discs'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form['username'] != app.config['USERNAME']:
            error = 'Invalid username'
        elif request.form['password'] != app.config['PASSWORD']:
            error = 'Invalid password'
        else:
            session['logged_in'] = True
            flask.flash('You were logged in')
            return flask.redirect(flask.url_for('list_discs'))
    return render_template('login.html', error=error)

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('logged_in', None)
    flask.flash('You were logged out')
    return flask.redirect(flask.url_for('list_discs'))

# for debugging
@app.route('/swf/<path:fn>')
def swf(fn):
    return flask.send_from_directory(app.config['SWF_DIR'], fn)

@app.route('/disc/<int:id>/')
def disc_play(id):
    return render_disc(id)

@app.route('/disc/<int:id>/json/')
def disc_json(id):
    disc = g.db.query(models.Disc).filter_by(id=id).one()
    return json.dumps(models.toJso(disc))

@app.route('/disc/<int:id>/edit/', methods=['GET', 'POST'])
@requires_login
def disc_edit(id):
    if request.method == 'POST':
        try:
            jsoDisc = json.loads(request.form['jsonNew'])
            if 'qtes' in jsoDisc:
                g.db.query(models.Qte).filter(models.Qte.disc_id == id).delete()
                for jsoQte in jsoDisc['qtes']:
                    qte = models.fromJso(jsoQte, models.Qte)
                    qte.disc_id = id
                    g.db.add(qte)
                g.db.commit()
            else:
                raise Exception("Invalid json")
        except:
            g.db.rollback()
            flask.flash("Could not parse json")
    return render_disc(id, urlPostQte=flask.url_for('edit_qte', id=id, _external=True), csrf=create_session(id).guid)

@app.route('/disc/<int:id>/qte/', methods=['POST'])
@verify_edit
def edit_qte(id):
    if request.json['action'] == 'put':
        qte = models.fromJso(request.json['qte'], models.Qte)
        # verify no overlapping qtes
        #  t----f t-f t----f
        #     t---------f
        # yes this is row-by-agonizing-row but there should only be one row
        # right now the debug info is more useful than optimizing with a bulk delete
        to_delete = g.db.query(models.Qte).filter(models.Qte.disc_id == id,
            models.Qte.ms_trigger <= qte.ms_finish, models.Qte.ms_finish >= qte.ms_trigger)
        print "adding qte", qte.ms_trigger, qte.ms_finish
        for qte_to_delete in to_delete:
            print "  deleting", qte_to_delete.ms_trigger, qte_to_delete.ms_finish
            g.db.delete(qte_to_delete)
        qte.disc_id = id
        g.db.add(qte)
        g.db.commit()
        return flask.jsonify(err='ok', csrf=g.session.guid)
    elif request.json['action'] == 'delete':
        deleted = g.db.query(models.Qte).filter_by(disc_id=id, ms_trigger=request.json['ms_trigger']).delete()
        if deleted > 0:
            print "DELETE: ", deleted, "qtes deleted", request.json['ms_trigger']
        else:
            print "DELETE: nothing deleted", request.json['ms_trigger']
        g.db.commit()
        return flask.jsonify(err='ok', csrf=g.session.guid)
    else:
        return flask.jsonify(err='invalid_action', csrf=g.session.guid)

def render_disc(id, **kwargs):
    disc = g.db.query(models.Disc).filter_by(id=id).one()
    flashvars = {'jsonDisc': json.dumps(models.toJso(disc))}
    for k, v in kwargs.iteritems():
        flashvars[k] = json.dumps(v)
    return render_template('disc.html', flashvars=flashvars, disc=disc_edit)

if __name__ == '__main__':
    app.run()
