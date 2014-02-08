from flask import Blueprint, request, abort, make_response, render_template, redirect

import portality.util as util
import portality.models as models
import portality.mine as mine
from portality.view.forms import dropdowns

from datetime import datetime
from copy import deepcopy
import json, csv, StringIO, time, os, requests

blueprint = Blueprint('organisation', __name__)

#####################################################################
# base organisation api
#####################################################################

@blueprint.route("/")
def organisations():
    """
    Any request to the base of the organisations url space
    """
    
    if 'q' in request.values:
        # FIXME: should be in the models layer
        query = {
            "query" : {
                "query_string" : {
                    "query" : "collaboratorOrganisation.canonical:*" + request.values['q'] + "*"
                }
            },
            "size" : 0,
            "facets" : {
                "orgs" : {
                    "terms" : {
                        "field" : "collaboratorOrganisation.canonical.exact",
                        "size" : 25,
                        "script" : "term.toLowerCase() contains '" + request.values['q'].lower() + "'"
                    }
                }
            }
        }
        r = models.Record.query(q=query)
        resp = make_response(json.dumps(r['facets']['orgs']['terms']))
        resp.mimetype = "application/json"
        return resp
        
    else:

        #logofolder = os.path.dirname(os.path.abspath( __file__ )).replace('/view','/static/logos')
        #logos=sorted(os.listdir(logofolder))
        logos = []

        return render_template(
            'organisation/orgs.html',
            logos=logos,
            orgs=json.dumps(dropdowns('record','collaboratorOrganisation.canonical'))
        )


@blueprint.route("/<mainorg>")
@blueprint.route("/<mainorg>.json")
def organisation(mainorg, raw=False):
    """
    Any request to a specific organisation's home page
    """
    
    # TODO:
    # list all this orgs projects
    # list a blurb and website about this org
    # list the main contact of this org (and perhaps other users)
    # offer ability to update the page about this org
    # show this org snapshot data, top projects, recent funding by years, pubs
    # offer a download report overview of this org

    logo = mainorg.lower().replace(' ','_').replace("'",'').replace('university_','').replace('_university','').replace('_of','').replace('of_','').replace('_the','').replace('the_','').replace('_and','').replace('and_','').replace('_for','').replace('for_','').replace('_.','.') + '.png';
    
    logofolder = os.path.dirname(os.path.abspath( __file__ )).replace('/view','/static/logos')
    logos=os.listdir(logofolder)
    if logo not in logos:
        logo = ''
    else:
        logo = '/static/logos/' + logo
    # logo = ""

    # FIXME: should be in the models layer
    qry = {
        "query": {
            "term": {
                "collaboratorOrganisation.canonical.exact": mainorg
            }
        },
        "size": 1,
        "facets": {
            "collaborators":{
                "terms_stats" : {
                    "key_field" : "collaboratorOrganisation.canonical.exact",
                    "value_field" : "project.fund.valuePounds",
                    "size" : 0
                }
            },
            "value_stats" : {
                "statistical" : {
                    "field" : "project.fund.valuePounds"
                }
            }
        }
    }
    r = models.Record.query(q=qry)

    org = {
        'name': mainorg,
        'logo': logo,
        'projects': r.get('hits',{}).get('total',0),
        'collaborators': len(r.get('facets',{}).get('collaborators',{}).get('terms',[])) - 1,
        'totalfunding': "{:,.0f}".format(r.get('facets',{}).get('value_stats',{}).get('total',0))
    }
    
    # TODO: post codes should perhaps be processed into the index data, to save 
    # processing them here
    # get post code - lat long lookup table
    pcll = json.load(open("postcodes.json"))
    try:
        orgs = r.get('hits',{}).get('hits',[])[0]['_source']['collaboratorOrganisation']
        for o in orgs:
            if o['canonical'] == mainorg:
                outcode = o['organisation']['address']['postCode'].replace(' ','')
        if len(outcode) == 7: outcode = outcode[0:4]
        elif len(outcode) == 6: outcode = outcode[0:3]
        pc = pcll[outcode]
        org['lat'] = pc['lat']
        org['lng'] = pc['lng']
    except:
        org['lat'] = 0
        org['lng'] = 0

    # TODO: should really have an org object with the above info in it and it 
    # should be passed to the page instead of the mainorg string
    if raw:
        return org
    elif util.request_wants_json():
        resp = make_response(json.dumps(org))
        resp.mimetype = "application/json"
        return resp
    else:
        return render_template('organisation/org.html', org=org)



#####################################################################
# matching (new potential) report
#####################################################################
# Web API endpoints associated with the matching/New Potential 
# Report
#####################################################################

@blueprint.route("/<mainorg>/matching", methods=["GET", "POST"])
@blueprint.route("/<mainorg>/matching.<suffix>", methods=["GET", "POST"])
def matching(mainorg, suffix=None):

    # get any match parameters provided in the request
    if request.json:
        project = request.json.get('project',[])
        person = request.json.get('person',[])
        keyword = request.json.get('keyword',[])
        url = request.json.get('url',[])
    else:
        project = request.values.get('project',"").split(',')
        person = request.values.get('person',"").split(',')
        keyword = request.values.get('keyword',"").split(',')
        url = request.values.get('url',"").split(',')

    # process the match parameters into search parameters
    # TODO: should make this a dict by weightings and include them from below
    # and also enable end users to prioritise certain keywords or types
    # TODO: perhaps also add maximums from each source, or maximum length of params overall?    
    params = []
    for k in keyword:
        if k not in params and len(k) > 0: params.append(k)

    for pr in project:
        # match project title to a project
        if len(pr) > 0:
            r = models.Record.pull_by_key('project.title',pr)
            if r is not None:
                extract = mine.mine_project_record(r)
                count = 0 # TODO: proper control of how many url-extracted keywords to include
                for e in extract:
                    for i in extract[e]:
                        count += 1
                        if count <= 10:
                            if i not in params: params.append(i.replace('(','')) # TODO: regex out anything non-az09

    for u in url:
        if len(u) > 0:
            if not u.startswith('http://') and not u.startswith('https://'):
                u = 'http://' + u
            #try:
            r = requests.get(u)
            clean = mine.html_text(r.text)
            extract = mine.full_extract(web_text=clean, web_weight=5)
            count = 0 # TODO: proper control of how many url-extracted keywords to include
            for e in extract:
                for i in extract[e]:
                    count += 1
                    if count <= 10:
                        if i not in params: params.append(i)
            #except:
            #    pass

    potential = []
    # perform the search with the defined params and build a list of matching orgs
    if len(params) > 0 or len(person) > 0:
        qry = {
            'query': {
                'bool': {
                    'must': [
                        {
                            'query_string': {
                                'query': " OR ".join(params)
                            }
                        }
                    ],
                    'must_not': [
                        {
                            'term': {
                                'collaboratorOrganisation.canonical.exact': mainorg
                            }
                        }
                    ]
                }
            },
            "size": 1000,
            "facets" : {
                "collaborators" : {
                    "terms" : {
                        "field" : "collaboratorOrganisation.canonical.exact",
                        "size" : 100
                    }
                }
            }
        }

        # add people, if any , to the search
        if len(person) > 0:
            qry['query']['bool']['should'] = []
            qry['query']['bool']['minimum_should_match'] = 1
            for p in person:
                if len(p) > 0:
                    qry['query']['bool']['should'].append({
                        'term': {
                            'collaboratorPerson.canonical.exact': p
                        }
                    })

        # get the collaborator orgs found in the search results
        # strip the ones who already collaborate with the mainorg
        # then find out some info about the remaining ones
        r = models.Record.query(q=qry)
        collabs = [i['term'] for i in r.get("facets", {}).get("collaborators", {}).get("terms", [])]


        collaboration_definition = ["leadro", "principal_investigator", "co_investigator", "fellow"] # FIXME: collaboration definition is going to need to pervade the code
        cs = [i['term'] for i in models.Record().ordered_collaborators(mainorg,10000,collaboration_definition)]

        for collab in collabs:
            if collab not in cs and len(potential) < 10:
                p = organisation(collab, raw=True)
                p['related'] = []
                for i in r.get("hits", {}).get("hits",[]):
                    canonicals = [l.get('canonical','') for l in i['_source'].get('collaboratorOrganisation',[])]
                    title = i['_source']['project']['title']
                    if collab in canonicals and mainorg not in canonicals and title not in p['related']:
                        p['related'].append(title)
                potential.append(p)
                
        
    matchinfo = {
        "new_potential": potential,
        "params": params,
        "person": person,
        "project": project,
        "keyword": keyword,
        "url": url
    }
    
    if util.request_wants_json():
        resp = make_response(json.dumps(matchinfo))
        resp.mimetype = "application/json"
        return resp
    elif suffix == "csv":
        output = StringIO.StringIO()
        writer = csv.writer(output)
    
        if len(potential) > 0:
            headers = ["name","projects","collaborators","funding","related"]
            writer.writerow(headers)
            for p in potential:
                r = [
                    p['name'],
                    p['projects'],
                    p['collaborators'],
                    p['totalfunding'],
                    len(p['related'])
                ]
                writer.writerow(r)
    
        resp = make_response(output.getvalue())
        resp.mimetype = "text/csv"
        resp.headers['Content-Disposition'] = 'attachment; filename="' + mainorg + '_new_potential_report.csv"'
        return resp
    else:
        return render_template('organisation/match.html', org=mainorg, matchinfo=matchinfo)



#####################################################################
# General utilities
#####################################################################
# Web API endpoints which provide generally useful functions for
# the front-end
#####################################################################

@blueprint.route("/<mainorg>/funders")
def funders(mainorg=None):
    # extract the values from the request
    start = request.values.get("start")
    c.models.Record()
    funders = c.funders(mainorg, start=start)
    resp = make_response(json.dumps(funders))
    resp.mimetype = "application/json"
    return resp

@blueprint.route("/<mainorg>/allfunders")
def allfunders(mainorg=None):
    c = models.Record()
    funders = c.all_funders()
    resp = make_response(json.dumps(funders))
    resp.mimetype = "application/json"
    return resp

@blueprint.route("/<mainorg>/grantcategories")
def grantcategories(mainorg=None):
    c = models.Record()
    funders = c.grant_categories()
    resp = make_response(json.dumps(funders))
    resp.mimetype = "application/json"
    return resp

def _make_csv(name, headers, rows):
    output = StringIO.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    resp = make_response(output.getvalue())
    resp.mimetype = "text/csv"
    resp.headers['Content-Disposition'] = 'attachment; filename="' + name + '.csv"'
    return resp


#####################################################################
# benchmarking report
#####################################################################
# Web API endpoints associated with the benchmarking report
#####################################################################

"""
Benchmarking report parameters objects have the following shape

    {
        "mainorg" : "<primary organisation>",
        "type" : "<report type: publications|award_value|num_projects>",
        "granularity" : "<month|quarter|year>",
        "start" : "<report start date>",
        "end" : "<report end date>",
        "funder" : "<funder constraint>",
        "grantcategory" : "<grant category constraint>",
        "leadonly" : <true|false>,
        "compare_org" : [<list of organisations to benchmark (may include mainorg)>],
        "compare_groups" : {
            "<group name>" : [<list of person names in this group>] 
        }
    }

"""

def _sanitise_benchmark_parameters(j):
    start = j.get("start")
    end = j.get("end")
    
    try:
        if start is not None:
            j["start"] = datetime.strftime(datetime.strptime(start, "%d/%m/%Y"), "%Y-%m-%d")
        if end is not None:
            j["end"] = datetime.strftime(datetime.strptime(end, "%d/%m/%Y"), "%Y-%m-%d")
    except ValueError:
        # do nothing, values should be correctly formatted
        pass
        
    return j

@blueprint.route("/<mainorg>/benchmarking", methods=["GET", "POST"])
@blueprint.route("/<mainorg>/benchmarking.<suffix>", methods=["GET"])
def benchmarking(mainorg=None, suffix=None):
    if request.method == "GET":
        returntype = "csv" if suffix == "csv" else "html"
        return GET_benchmarking(mainorg, returntype)
    elif request.method == "POST":
        return POST_benchmarking(mainorg)

def GET_benchmarking(mainorg, returntype):
    if returntype == "html":
        return render_template('organisation/bench.html', mainorg=mainorg)
    elif returntype == "csv":
        # get the report parameters out of the request
        j = request.values.get("obj")
        obj = json.loads(j)
        obj = _sanitise_benchmark_parameters(obj)
        
        # generate the report itself
        b = models.Record()
        report = b.benchmark(**obj)
        output = _to_csv(report, obj.get("type"))
        
        resp = make_response(output.getvalue())
        resp.mimetype = "text/csv"
        resp.headers['Content-Disposition'] = 'attachment; filename="' + mainorg + '_benchmarking_report.csv"'
        return resp
        
        #benchmark = {"parameters" : obj, "report" : {}}
        #return _get_csv(mainorg, benchmark)

def POST_benchmarking(mainorg):
    j = _sanitise_benchmark_parameters(request.json)
    b = models.Record()
    report = b.benchmark(**j)
    
    # now make the response
    benchmark = {"parameters" : j, "report" : report}
    resp = make_response(json.dumps(benchmark))
    resp.mimetype = "application/json"
    return resp

@blueprint.route("/<mainorg>/benchmarking/details", methods=["POST"])
def details(mainorg=None):
    j = _sanitise_benchmark_parameters(request.json)
    b = models.Record()
    report = b.benchmark_details(**j)
    
    # now make the response
    benchmark = {"parameters" : j, "report" : report}
    resp = make_response(json.dumps(benchmark))
    resp.mimetype = "application/json"
    return resp

def _to_csv(report, type):
    value_field = "count"
    date_field = "time"
    if type == "award_value":
        value_field = "total"
    
    rows, dates, orgs = _get_report_rows(report, value_field=value_field, date_field=date_field)

    output = StringIO.StringIO()
    writer = csv.writer(output)
    
    headers = ["date"] + [org for org in orgs]
    writer.writerow(headers)
    for row in rows:
        formatted = [time.strftime("%Y-%m-%d", time.gmtime(row[0]/1000))] + row[1:]
        writer.writerow(formatted)
    
    return output

def _get_report_rows(data, value_field="count", date_field="time"):
    dates = []
    orgs = []
    row_sets = {}
    for org in data:
        orgs.append(org)
        org_rows = {}
        for p in data.get(org):
            if p[date_field] not in dates:
                dates.append(p[date_field])
            org_rows[p[date_field]] = p[value_field]
        row_sets[org] = org_rows
    
    dates.sort()
    orgs.sort()
    rows = []
    for date in dates:
        row = [date]
        for org in orgs:
            if date in row_sets[org]:
                row.append(row_sets[org][date])
            else:
                row.append(0)
        rows.append(row)
    
    return rows, dates, orgs

######################################################################
# collaboration report
######################################################################
# Wep API endpoints for constructing the collaboration report
######################################################################

@blueprint.route("/<mainorg>/collaboration/top")
@blueprint.route("/<mainorg>/collaboration/top.<form>")
def top(mainorg=None, form="json"):
    """
    List the top collaborators for the mainorg
    """
    
    # extract the values from the request
    count = int(request.values.get("count", 0))
    order = request.values.get("order", "projects")
    defn = request.values.get("collaboration_definition")
    collaboration_definition = None
    if defn is None:
        collaboration_definition = ["leadro", "principal_investigator", "co_investigator", "fellow"] # FIXME: this should be in config
    else:
        collaboration_definition = [d.strip() for d in defn.split(",")]
    start = request.values.get("start")
    
    # pass the parameters to the Record model
    c = models.Record()
    top_collabs = c.ordered_collaborators(mainorg, count, collaboration_definition, start=start, order=order)
    
    # make the response and send it back
    if form == "raw":
        return top_collabs
    elif form == "json":
        resp = make_response(json.dumps(top_collabs))
        resp.mimetype = "application/json"
        return resp
    
    elif form == "csv":
        headers = ["organisation", "number of collaborative projects", "total value of collaborative projects"]
        rows = []
        for row in top_collabs:
            rows.append([row['term'], row['count'], row['total']])
            
        return _make_csv(mainorg + " Collaborators", headers, rows)

@blueprint.route("/<mainorg>/collaboration/funders")
@blueprint.route("/<mainorg>/collaboration/funders.<form>")
def funders(mainorg=None, form="json"):
    """
    All the funders for the mainorg
    """
    # extract the values from the request
    start = request.values.get("start")
    
    c = models.Record()
    funders = c.ordered_funders(mainorg, start=start)
    
    if form == "json":
        resp = make_response(json.dumps(funders))
        resp.mimetype = "application/json"
        return resp
    
    elif form == "csv":
        headers = ["funder", "number of collaborative projects funded", "total value of collaborative projects funded"]
        rows = []
        for row in funders:
            rows.append([row['term'], row['count'], row['total']])
            
        return _make_csv(mainorg + " Collaboration Funders", headers, rows)

@blueprint.route('/<mainorg>/collaboration')
def collaboration(mainorg=None):
    """
    The main function for generating the collaboration report
    """
    
    # allowable parameters of the report
    funder = request.values.get("funder")
    start = request.values.get("start")
    end = request.values.get("end")
    lower = request.values.get("lower")
    upper = request.values.get("upper")
    collab_orgs = []
    result_format = request.values.get("format", "html")
    category = request.values.get("category")
    status = request.values.get("status")
    
    defn = request.values.get("collaboration_definition")
    collaboration_definition = None
    if defn is None:
        collaboration_definition = ["leadro", "principal_investigator", "co_investigator", "fellow"] # FIXME: this should be in config
    else:
        collaboration_definition = [d.strip() for d in defn.split(",")]
    
    for k, v in request.values.items():
        if k.startswith("collab") and k != "collaboration_definition":
            orgs = v.split(",")
            collab_orgs += orgs
    
    # we want the start and end dates in a nice big-endian format, so we 
    # may need to rejig them
    try:
        if start is not None:
            start = datetime.strftime(datetime.strptime(start, "%d/%m/%Y"), "%Y-%m-%d")
        if end is not None:
            end = datetime.strftime(datetime.strptime(end, "%d/%m/%Y"), "%Y-%m-%d")
    except ValueError:
        # do nothing, it's fine
        pass
    
    # if we've been asked for the landing page for the collaboration report,
    # don't bother doing any of the hard work
    if (result_format == "html" and funder is None and start is None and
            end is None and lower is None and upper is None and len(collab_orgs) == 0):
        return render_template('organisation/collab.html', mainorg=mainorg, report=None)
    
    c = models.Record()
    collaboration_report = c.collaboration_report(mainorg, collaboration_definition,
                                funder=funder, collab_orgs=collab_orgs,
                                start=start, end=end, 
                                lower=lower, upper=upper, category=category, status=status)
    
    
    # generate the report rows.  For each project we need to determine (based on the
    # collaborator definition) what the list of collaborators actually is, and then
    # build the report around that.
    
    display_roles = {
        "principalInvestigator" : "Principal Investigator",
        "coInvestigator" : "Co-Investigator",
        "fellow" : "Fellow",
        "leadRo" : "Lead Research Organisation",
        "coFunder" : "Co-Funder",
        "projectPartner" : "Project Partner",
        "collaboration" : "Resulting Collaboration"
    }
    
    report = []
    for p in collaboration_report.projects:
        actual_collaborators = collaboration_report.collaborators(p)
        for co in actual_collaborators:
        # for co in p.get("collaboratorOrganisation", []):
            # if the collaborating organisation is the main organisation, skip it
            if co.get("name") == mainorg:
                continue
            
            # get the roles of this organisation on the project
            collab_roles = collaboration_report.roles(co.get("name"), p)
            # print collab_roles
            displayable_roles = [display_roles.get(r, r) for r in collab_roles]
            displayable_roles = ", ".join(displayable_roles)
            
            row = {}
            row["pid"] = p.get("id")
            row['collaborator'] = co.get("name")
            row["collaborator_role"] = displayable_roles
            row['projectTitle'] = p.get("project", {}).get("title", "untitled")
            row['projectValue'] = p.get("project", {}).get("fund", {}).get("valuePounds", 0)
            row['formattedProjectValue'] = "{:,.0f}".format(row["projectValue"])
            row['collaborationSize'] = len(actual_collaborators)
            row['awardRef'] = p.get("project", {}).get("grantReference", "unknown")
            row['funder'] = p.get("primaryFunder", {}).get("name", "unknown")
            row['startDate'] = p.get("project", {}).get("fund", {}).get("start")
            if row["startDate"] is not None:
                row["formattedStartDate"] = datetime.strftime(datetime.strptime(row["startDate"], "%Y-%m-%d"), "%d/%m/%Y")
            else:
                row["formattedStartDate"] = None
            row['endDate'] = p.get("project", {}).get("fund", {}).get("end")
            if row["endDate"] is not None:
                row["formattedEndDate"] = datetime.strftime(datetime.strptime(row["endDate"], "%Y-%m-%d"), "%d/%m/%Y")
            else:
                row["formattedEndDate"] = None
            
            # extract the PIs (of which there should only be one)
            pis = p.get("principalInvestigator", [])
            if len(pis) > 0:
                row["principalInvestigator"] = pis[0].get("person", {}).get("firstName", "") + " " + pis[0].get("person", {}).get("surname", "")
                row["piOrganisation"] = pis[0].get("organisation", {}).get("name", "")
            else:
                row["principalInvestigator"] = ""
                row["piOrganisation"] = ""
            
            report.append(row)
    
    data = {
        "rows" : report,
        "collaborators" : collaboration_report.collaborators_facet(),
        "value_stats" : collaboration_report.value_stats(),
        "funders" : collaboration_report.funders_facet(),
        "count" : collaboration_report.count()
    }
    
    #FIXME: we need to do a proper treatment of the HTML version of the report with arguments - at the 
    # moment the report is basically ignored
    if result_format == "html":
        return render_template('organisation/collab.html', mainorg=mainorg, report=data)

    elif result_format == "json":
        resp = make_response(json.dumps(data))
        resp.mimetype = "application/json"
        return resp

    elif result_format == "csv":
        headers = ["collaborator", "collaborator role on project", "project title", "principal investigator", "pi organisation" , "number of project collaborators", "total project funding", 
                    "funder", "award ref", "project start date", "project end date"]
        rows = []
        for row in report:
            rows.append([row['collaborator'], row["collaborator_role"], row['projectTitle'], row["principalInvestigator"], row["piOrganisation"], row['collaborationSize'], row['projectValue'], 
                    row['funder'], row['awardRef'], row['startDate'], row['endDate']])
        return _make_csv(mainorg + " Collaborations Report", headers, rows)
            
    abort(406)

    
