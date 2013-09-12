from flask import Blueprint, render_template

import portality.models as models


blueprint = Blueprint('project', __name__)


@blueprint.route('/')
@blueprint.route('/<pid>')
def project(pid=""):
    project = models.Record.pull(pid)    
    return render_template("project/project.html", project=project)

