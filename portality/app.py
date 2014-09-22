
from flask import Flask, request, abort, render_template
from flask.views import View
from flask.ext.login import login_user, current_user

import json, os

import portality.models as models
from portality.core import app, login_manager

from portality.view.forms import dropdowns


from portality.view.account import blueprint as account
from portality.view.admin import blueprint as admin
from portality.view.graph import blueprint as graph
from portality.view.contact import blueprint as contact
from portality.view.query import blueprint as query
from portality.view.stream import blueprint as stream
from portality.view.organisation import blueprint as organisation
from portality.view.project import blueprint as project
from portality.view.person import blueprint as person

app.register_blueprint(account, url_prefix='/account')
app.register_blueprint(admin, url_prefix='/admin')
app.register_blueprint(graph, url_prefix='/graph')
app.register_blueprint(contact, url_prefix='/contact')
app.register_blueprint(query, url_prefix='/query')
app.register_blueprint(stream, url_prefix='/stream')
app.register_blueprint(organisation, url_prefix="/organisation")
app.register_blueprint(project, url_prefix="/project")
app.register_blueprint(person, url_prefix="/person")


@login_manager.user_loader
def load_account_for_login_manager(userid):
    out = models.Account.pull(userid)
    return out

@app.context_processor
def set_current_context():
    """ Set some template context globals. """
    return dict(current_user=current_user, app=app)

@app.before_request
def standard_authentication():
    """Check remote_user on a per-request basis."""
    remote_user = request.headers.get('REMOTE_USER', '')
    if remote_user:
        user = models.Account.pull(remote_user)
        if user:
            login_user(user, remember=False)
    # add a check for provision of api key
    elif 'api_key' in request.values:
        res = models.Account.query(q='api_key:"' + request.values['api_key'] + '"')['hits']['hits']
        if len(res) == 1:
            user = models.Account.pull(res[0]['_source']['id'])
            if user:
                login_user(user, remember=False)


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(401)
def page_not_found(e):
    return render_template('401.html'), 401
        
        
@app.route('/')
def index():

    #logofolder = os.path.dirname(os.path.abspath( __file__ )) + '/static/logos'
    #logos=sorted(os.listdir(logofolder))
    logos = []

    return render_template(
        'index.html',
        logos=logos,
        orgs=json.dumps(dropdowns('record','collaboratorOrganisation.canonical'))
    )

    return render_template('index.html')
    

if __name__ == "__main__":
    import sys
    pycharm_debug = app.config.get('DEBUG_PYCHARM', False)
    if len(sys.argv) > 1:
        if sys.argv[1] == '-d':
            pycharm_debug = True

    if pycharm_debug:
        app.config['DEBUG'] = False
        import pydevd
        pydevd.settrace(app.config.get('DEBUG_PYCHARM_SERVER', 'localhost'), port=app.config.get('DEBUG_PYCHARM_PORT', 6000), stdoutToServer=True, stderrToServer=True)

    app.run(host='0.0.0.0', debug=app.config['DEBUG'], port=app.config['PORT'])

