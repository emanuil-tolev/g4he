from flask import Blueprint, request, render_template

import portality.models as models


blueprint = Blueprint('project', __name__)


@blueprint.route('/')
@blueprint.route('/<pid>')
def project(pid=""):
    project = models.Record.pull(pid)
    mainorg = request.values.get('org',None)
    return render_template("project/project.html", project=project, mainorg=mainorg)

