from portality import models
import json, hashlib, sys
from datetime import datetime
from copy import deepcopy


#######################################################################
## conversion tables and other useful "configuration"
#######################################################################

ROLE_MAP = {
    "PRINCIPAL_INVESTIGATOR" : "principalInvestigator",
    "CO_INVESTIGATOR" : "coInvestigator",
    "FELLOW" : "fellowPerson"
}

# load the cerif classes into memory for convenience
CERIF_CLASSES = {}
def load_cerif_classes():
    for k in models.CerifClass.iterall():
        cfclassid = k.get("cfClassId")
        value = None
        for jax in k.get("cfDescrOrCfDescrSrcOrCfTerm", []):
            name = jax.get("JAXBElement", {}).get("name")
            if name == "{urn:xmlns:org:eurocris:cerif-1.5-1}cfTerm":
                value = jax.get("JAXBElement", {}).get("value", {}).get("value")
                break
        CERIF_CLASSES[cfclassid] = _normalise(value)

#######################################################################

#######################################################################
## Utilities
#######################################################################

def append(dictionary, key, value):
    """ 
    appends the value to the key in the dictionary, or creates a one 
    element array with that value in it, if the key does not already exist
    """
    if key in dictionary:
        dictionary[key].append(value)
    else:
        dictionary[key] = [value]

def _normalise(s):
    """
    normalise the string to our preferred format - camel case
    """
    camel = "".join([w[0].upper() + w[1:] for w in s.lower().split(" ") if w != ""])
    return camel[0].lower() + camel[1:]

def cleanup(project):
    if "organisation" in project:
        del project['organisation']
    if "projectPerson" in project:
        del project['projectPerson']
    if "collaborator" in project:
        del project['collaborator']
    if "leadResearchOrganisation" in project:
        del project['leadResearchOrganisation']

#######################################################################


###########################################################################
## Methods to restructure the people associated
###########################################################################

# take the project record and bring the people up to the top level, under keys for their roles
def restructure_people(project):
    # list all of the people on the project
    people = project.get('projectPerson', [])
    
    for person in people:
        # first look up the person's organisation in the index
        org = models.Person.org_record(person["id"])
        
        # now look for the person in this project in the history data
        corrected_org_id = models.PersonHistory.get_org_id(person['id'], project.get("project", {}).get("id"))
        if corrected_org_id is not None:
            print "has corrected org"
            # if there is a corrected id, we want to use that as the org instead
            corrected_org = models.Organisation.pull_by_key("organisationOverview.organisation.id", corrected_org_id)
            if corrected_org is not None:
                orgrecord = corrected_org.get("organisationOverview", {}).get("organisation")
                if orgrecord is not None:
                    org = orgrecord
        
        # now make a full person record, with their associated org
        full_record = {"person" : person, "organisation" : org}
        
        # go through all the roles that the person might have had on the project, and make the appropriate
        # record for each one
        for role in person.get('projectRole'):
            mapped_role = ROLE_MAP.get(role, role)
            
            # add the person to the array for that role, so we can search on people or affiliations
            # by their person role on the project
            append(project, mapped_role, full_record) 
            
            # all people are now potentially collaborators, so record them also in the collaboratorPerson
            # field
            add_collaborator_person(project, mapped_role, full_record)
            
            # all related orgs are now potentially collaborators, so record them also in the collaboratorOrgs
            # field
            add_collaborator_org(project, mapped_role, full_record.get("organisation"))

def add_collaborator_person(project, role, person):
    collp = deepcopy(person)
    cname = canonical_name(collp)
    if cname is None:
        return
    
    unique = unique_person_key(collp)
    if is_duplicate_collaborator_person(project, unique):
        return
    
    collp['slug'] = unique
    collp['canonical'] = cname
    
    if role is "principalInvestigator":
        collp["principalInvestigator"] = cname
    
    if role is "coInvestigator":
        collp["coInvestigator"] = cname
    
    append(project, "collaboratorPerson", collp)

def canonical_name(person):
    sn = person.get("person", {}).get("surname")
    fn = person.get("person", {}).get("firstName")
    if sn is not None and fn is not None:
         return fn + " " + sn
    if sn is None and fn is not None:
        return fn
    if sn is not None and fn is None:
        return sn
    return None

def unique_person_key(person):
    p = person.get("person", {})
    o = person.get("organisation", {})
    s = p.get("firstName", "") + p.get("surname", "") + o.get("name", "")
    key = hashlib.md5(s.encode("utf-8")).hexdigest()
    return key

def is_duplicate_collaborator_person(project, unique):
    for cp in project.get("collaboratorPerson", []):
        if cp.get("slug") == unique:
            return True
    return False

##############################################################################


##############################################################################
## Methods for restructuring organisation information
##############################################################################

# restructure the organisational portions of the data for indexing purposes
def restructure_orgs(project):
    # get the cerif record for the project
    pid = project.get("project", {}).get("id")
    cproj = models.CerifProject.pull_by_key("cfClassOrCfClassSchemeOrCfClassSchemeDescr.cfProj.cfProjId", pid)
    
    # now mine the orgs, and cross-reference with the cerif data
    orgs = project.get("organisation", [])
    for org in orgs:
        # get the org's class id from the cerif project
        classids = _org_class_from_cerifproject(cproj, org['id'])
        
        for cid in classids:
            # look the class id up for it's human readable value
            classname = CERIF_CLASSES.get(cid)
            
            # add the org to the dictionary for that class name
            append(project, classname, org)
            
            # add the org to the list of collaborating organisations
            add_collaborator_org(project, classname, org)
    
    # now finally rationalise the lead research organisations data (this will
    # de-duplicate with any existing known leadRO)
    if "leadResearchOrganisation" in project:
        add_collaborator_org(project, "leadRo", project.get("leadResearchOrganisation"))

def add_collaborator_org(project, role, org):
    co = {"organisation" : org}
    cname, alts = org_names(org)
    
    # find out if this is a duplicate of an existing org record
    slug = unique_org_key(org, cname)
    if is_duplicate_collaborator_org(project, slug):
        return
    
    co['slug'] = slug
    co['canonical'] = cname
    co['alt'] = alts
    # co[role] = cname
    
    append(project, "collaboratorOrganisation", co)

def org_names(org):
    # FIXME: needs to bind to the alternate names api when that is ready
    name = org.get("name")
    return name, [name]

def unique_org_key(org, cname):
    # we only really have the name to key off
    return hashlib.md5(cname.encode("utf-8")).hexdigest()

def is_duplicate_collaborator_org(project, slug):
    for o in project.get("collaboratorOrganisation", []):
        if o.get("slug") == slug:
            return True
    return False

def _org_class_from_cerifproject(cproj, org_id):
    cids = []
    descs = cproj.get("cfClassOrCfClassSchemeOrCfClassSchemeDescr", [])
    for desc in descs:
        for jax in desc.get("cfProj", {}).get("cfTitleOrCfAbstrOrCfKeyw", []):
            name = jax.get("JAXBElement", {}).get("name")
            if name == "{urn:xmlns:org:eurocris:cerif-1.5-1}cfProj_OrgUnit":
                ouid = jax.get("JAXBElement", {}).get("value", {}).get("cfOrgUnitId")
                if ouid == org_id:
                    cids.append(jax.get("JAXBElement", {}).get("value", {}).get("cfClassId"))
    return cids

###############################################################################


###############################################################################
## Methods for dealing with funders
###############################################################################

def primary_funder(project):
    funder_id = project.get("project", {}).get("fund", {}).get("funder", {}).get("id")
    if funder_id is None:
        return
    full_org = models.Organisation.pull_by_key("organisationOverview.organisation.id", funder_id)
    project['primaryFunder'] = full_org.get("organisationOverview", {}).get("organisation", {})

###############################################################################


def indexg4he(whichindex=None, limit=None, batch_size=1000):
    if whichindex == 'G4HEA':
        r = models.RecordA
    else:
        r = models.RecordB
        
    print "Indexing G4HE data from cached GtR data"
    print "index:", r, "limit: ", limit, " batch size: ", batch_size
    
    start = datetime.now()
    lastrun = start
    batch = []
    COUNTER = 1
    
    print "loading cerif classes...",
    load_cerif_classes()
    print len(CERIF_CLASSES), " cerif classes loaded"
    
    projects = models.Project.iterall(limit=limit)
    for project in projects:
        # unwrap from the unnecessary projectComposition
        project = project.get("projectComposition")
        
        print str(COUNTER) + ": processing " + str(project.get("project", {}).get("id")) + "...", # comma on purpose
        sys.stdout.flush()
        
        # run all the restructuring tasks
        restructure_people(project)
        print "done people;",
        sys.stdout.flush()
        
        primary_funder(project)
        print "done funder;", 
        sys.stdout.flush()
        
        restructure_orgs(project)
        print "done org;",
        sys.stdout.flush()
        
        cleanup(project)
        print "cleaned up"
        
        # write to the batch
        batch.append(project)
        
        if COUNTER % batch_size == 0:
            interim = datetime.now()
            sofar_diff = interim - start
            since_diff = interim - lastrun
            sofar_seconds = sofar_diff.total_seconds()
            since_seconds = since_diff.total_seconds()
            lastrun = interim
            print "writing batch (took "+ str(since_seconds) +"s to generate) (processing for " + str(sofar_seconds) + "s so far)"
            
            r.bulk(batch)
            del batch[:] # empty the list, do not re-assign it
        
        # finally, increment the counter
        COUNTER += 1
    
    # at the end there might still be stuff to bulk load
    if len(batch) > 0:
        print "writing final batch"
        r.bulk(batch)
        
    end = datetime.now()
    diff = end - start
    total_seconds = diff.total_seconds()
    print "finished, took " + str(total_seconds) + "s"
    
    # when we finish, refresh the index
    print "REFRESHING ELASTIC SEARCH"
    r.refresh()
    
    # TODO: other things we may want to add here:
    # build an index of all organisations and track the different names that may be them
    # calculate some values for particular organisations, like their total projects value
    # build a config list of all organisation upfront display names, to save querying for the list

if __name__ == "__main__":
    LIMIT = None
    BATCH_SIZE = 1000
    indexg4he(limit=LIMIT, batch_size=BATCH_SIZE)

