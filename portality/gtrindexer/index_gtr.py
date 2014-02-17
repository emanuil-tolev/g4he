# import portality.models, workflows, cerif

from portality import models
from portality.gtrindexer import workflows
from portality.gtrindexer import cerif
from portality import settings

def project_handler(project, cerif_project):
    proj = models.Project(**project.as_dict())
    print "saving data from " + project.url()
    proj.save()
    if cerif_project is not None:
        cproj = models.CerifProject(**cerif_project.as_dict())
        print "saving data from " + cerif_project.url()
        cproj.save()
    
def person_handler(person):
    pers = models.Person(**person.as_dict())
    print "saving data from " + person.url()
    pers.save()
    
def organisation_handler(organisation):
    org = models.Organisation(**organisation.as_dict())
    print "saving data from " + organisation.url()
    org.save()
    
def publication_handler(publication):
    pub = models.Publication(**publication.as_dict())
    print "saving data from " + publication.url()
    pub.save()

def initialise_index():
    mappings = settings.GTR_MAPPINGS
    i = str(settings.ELASTIC_SEARCH_HOST).rstrip('/')
    i += '/' + settings.GTR_INDEX
    for key, mapping in mappings.iteritems():
        im = i + '/' + key + '/_mapping'
        exists = requests.get(im)
        if exists.status_code != 200:
            ri = requests.post(i)
            r = requests.put(im, json.dumps(mapping))
            print key, r.status_code

def indexgtr():
    # ensure the index with the right mappings exists
    initialise_index()
    
    # use the crawler to crawl all of the gtr data
    workflows.crawl("http://gtr.rcuk.ac.uk/", min_request_gap=0,
        project_limit=None, project_callback=project_handler, pass_cerif_project=True,
        person_limit=None, person_callback=person_handler, 
        organisation_limit=None, organisation_callback=organisation_handler, 
        publication_limit=None, publication_callback=publication_handler
    )

    # index the cerif classes
    client = cerif.GtRCerif("http://gtr.rcuk.ac.uk/")
    classes = client.cerif_classes()
    for k, o in classes.iteritems():
        c = models.CerifClass(**o)
        print "saving cerif class " + k
        c.save()


if __name__ == "__main__":
    indexgtr()

