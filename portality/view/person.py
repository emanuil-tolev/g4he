from flask import Blueprint, render_template

import portality.models as models


blueprint = Blueprint('person', __name__)


# FIXME: mainorg is currently ignored here, as there is no way to constrain the list of people
# to the supplied organisation with the index in its current form
@blueprint.route("/")
@blueprint.route("/<pid>")
def person(pid=""):
    project = models.Record.pull(pid)
    return render_template("person/person.html", project=project)


