# Key runnable files

* index_gtr - clone the entire GtR database via the GtR-1.0 API
* personhistory - load from the csvs provided by GtR the historical person/project/org affiliations
* index_g4he - take the raw indexed gtr data and munge it into the Record format required by the g4he application

# Process

1. Run index_gtr; this will clone all of the data in the GtR service into a local copy of the index

2. Run personhisotry; this will load the historical person/project/org affiliations into our local index

3. Run index_g4he; this will take the local indexes and build the g4he reporting index

# Files you can ignore

* comparepeople - this was an initial experiment to ascertain the impact on the index of incorporating the historical person data
* index_projects - the original attempt to build the g4he index directly from GtR.  It has been superseded by index_gtr


# G4HE Index Data Structure

    {
        "id": "<opaque identifier for record>",
        
        "project" : {
            "id": "<gtr project id>",
            "abstractText": "<abstract>",
            "grantCategory": "<grant category>",
            "grantReference": "<grant reference>",
            "keyFindingsText": "<key findings>",
            "nonAcademicUsesText": "<non academic uses>",
            "potentialImpactText": "<potential impact>",
            "status": "<project status>",
            "title": "<project title>",
            "url": "<gtr url>"
            
            "fund": {
                "end": "<project end date>",
                "start": "<project start date>",
                "valuePounds": "<project value>",
                "funder": {
                    "id": "<gtr id of funder>",
                    "name": "<name of funder>",
                    "url": "<gtr url of funder>"
                },
            },
            
            "identifier": {
                "type": "<identifier type>",
                "value" : "<identifier>"
            },
            
            "output": {
                "collaborationOutput": {<collaboration output object>},
                "intellectualPropertyOutput": {<intellectual property output object>},
                "policyInfluenceOutput": {<policy influence output object>},
                "productOutput": {<product output>},
                "researchMaterialOutput": {<research material output>},
                "spinOutOutput": {<spinout output>}
            },
            
            "publication": [{<publication object>}]
        }
        
        "coFunder": [{<org record with co-funder role>}],
        
        "collaboration": [{<org record with collaboration role>}],
        
        "evalCollaboration": [{<org record with evalCollaboration role>}],
        
        "fellow": [{<org record with fellow role>}],
        
        "leadRo": [{<org record for lead research organisation>}],
        
        "primaryFunder": {<org record for funder>},
        
        "projectPartner": [{<org record with project partner role}]
        
        "coInvestigator": [
            {
                "organisation": "<organisation record for host of co-i>",
                "person", "<person record for co-i>"
            }
        ],
        
        "fellowPerson": [
            {
                "organisation": "<organisation record for host of fellow>",
                "person", "<person record for fellow>"
            }
        ],
        
        "principalInvestigator": [
            {
                "organisation": "<organisation record for host of p-i>",
                "person", "<person record for p-i>"
            }
        ],
        
        "collaboratorOrganisation": [
            {
                "alt": "<alternative names for organisation>",
                "canonical": "<canonical name for organisation>",
                "slug": "<slugified version of name for organisation>",
                "organisation": {<organisation record>},
            }
        ],
        
        "collaboratorPerson": [
            {
                "canonical": "<canonical name for person>",
                "coInvestigator": "<true/false if co-i>",
                "principalInvestigator": "<true/false if pi>",
                "slug": "<slugified version of name for person>",
                "organisation": {<person host org record>},
                "person": {<person record>},
            }
        ]
    }
