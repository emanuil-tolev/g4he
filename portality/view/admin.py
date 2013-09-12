import json

from flask import Blueprint, request, flash, abort, make_response
from flask import render_template, redirect, url_for
from flask.ext.login import current_user

from portality.core import app
import portality.models as models

from portality.gtrindexer.index_gtr import indexgtr
from portality.gtrindexer.index_g4he import indexg4he


blueprint = Blueprint('admin', __name__)


# restrict everything in admin to super users for now
@blueprint.before_request
def restrict():
    if current_user.is_anonymous():
        return redirect('/account/login?next=' + request.path)
    elif not current_user.is_super:
        abort(401)
    

# build an admin page where things can be done
@blueprint.route('/')
def index():
    live = models.Config.pull('indexing').data['live'] if models.Config.pull('indexing') is not None else None
    return render_template('admin/index.html', live=live)


# catch requests to rebuild or delete indexes
@blueprint.route('/index/<indexname>/<action>')
def indexing(indexname,action):
    conf = models.Config.pull('indexing')
    if conf is None: conf = models.Config(id='indexing')

    if indexname in ['G4HEA','G4HEB']:
        if action == 'rebuild':
            pass
            '''# wipe the index
            if indexname == 'G4HEA':
                r = models.RecordA
            else:
                r = models.RecordB
            r.delete_index()
            # create the record mapping
            r.put_mapping(app.config["GTR_MAPPINGS"]["record"])
            # run the index rebuild process into this index
            indexg4he(indexname)'''
        elif action == 'live':
            # set the stored flexible indexing config value to state which index is live
            conf.data['live'] = indexname
            conf.save()
            return redirect(url_for('.index'))
    elif indexname == 'GTR':
        if action == 'rebuild':
            pass
            '''# wipe the gtr index
            models.Project.delete_index()
            # put the mappings for the gtr index (first map creates index)
            for key, mapping in app.config["GTR_MAPPINGS"].iteritems():
                klass = getattr(models, key[0].capitalize() + key[1:] )
                klass.put_mapping(mapping)
            # run the index rebuild process into this index
            indexgtr()'''
        elif action == 'delete':
            pass
            #models.Project.delete_index()
        
        
