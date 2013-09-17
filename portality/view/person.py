from flask import Blueprint, render_template, request, make_response

import json

import portality.models as models


blueprint = Blueprint('person', __name__)


# FIXME: mainorg is currently ignored here, as there is no way to constrain the list of people
# to the supplied organisation with the index in its current form
@blueprint.route("/")
@blueprint.route("/<pid>")
def person(pid=""):

    if 'q' in request.values:
        r = models.Record.query(q={
            'query': {
                'match_all': {}
            },
            'size': 0,
            'facets': {
                'persons': {
                    'terms': {
                        'field': 'collaboratorPerson.canonical.exact'                        
                    },
                    'facet_filter': {
                        'query':{
                            'query_string':{
                                'query': '*' + request.values['q'] + '*',
                                'default_field': 'collaboratorPerson.canonical'
                            }
                        }
                    }
                }
            }
        })
        resp = make_response(json.dumps(r['facets']['persons']['terms']))
        resp.mimetype = "application/json"
        return resp
        
    else:

        project = models.Record.pull(pid)
        return render_template("person/person.html", project=project)


