# import portality.models, workflows, cerif

from portality import models
from portality.gtrindexer import workflows
from portality.gtrindexer import cerif

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


def indexgtr():
    workflows.crawl("http://gtr.rcuk.ac.uk/", min_request_gap=0,
        project_limit=0, project_callback=project_handler, pass_cerif_project=True,
        person_limit=None, person_callback=person_handler, 
        organisation_limit=0, organisation_callback=organisation_handler, 
        publication_limit=0, publication_callback=publication_handler
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

