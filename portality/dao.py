import os, json, UserDict, requests, uuid

from datetime import datetime

from portality.core import app, current_user

'''
All models in models.py should inherig this DomainObject to know how to save themselves in the index and so on.
You can overwrite and add to the DomainObject functions as required. See models.py for some examples.
'''
    
    
class DomainObject(UserDict.IterableUserDict):
    __type__ = "" # set the type on the model that inherits this

    # set index connections data
    HOST = str(app.config.get('ELASTIC_SEARCH_HOST','http://localhost:9200'))
    INDEX = str(app.config['ELASTIC_SEARCH_INDEX'])
    HOSTINDEX = HOST + '/' + INDEX + '/'
    HOSTINDEXTYPE = HOSTINDEX + __type__ + '/'


    def __init__(self, **kwargs):
        if 'host' in kwargs:
            cls.HOST = kwargs['host']
        if 'index' in kwargs:
            cls.INDEX = kwargs['index']

        if '_source' in kwargs:
            self.data = dict(kwargs['_source'])
            self.meta = dict(kwargs)
            del self.meta['_source']
        elif 'data' in kwargs:
            self.data = dict(kwargs['data'])
        else:
            self.data = dict(kwargs)
            if 'host' in self.data: del self.data['host']
            if 'index' in self.data: del self.data['index']
            
    
    @classmethod
    def makeid(cls):
        '''Create a new id for data object
        overwrite this in specific model types if required'''
        return uuid.uuid4().hex

    @property
    def id(self):
        return self.data.get('id', None)
        
    @property
    def version(self):
        return self.meta.get('_version', None)

    @property
    def json(self):
        return json.dumps(self.data)

    def save(self):
        if 'id' in self.data:
            id_ = self.data['id'].strip()
        else:
            id_ = self.makeid()
            self.data['id'] = id_
        
        self.data['last_updated'] = datetime.now().strftime("%Y-%m-%d %H%M")

        if 'created_date' not in self.data:
            self.data['created_date'] = datetime.now().strftime("%Y-%m-%d %H%M")
            
        if 'author' not in self.data:
            try:
                self.data['author'] = current_user.id
            except:
                self.data['author'] = "anonymous"

        r = requests.post(self.HOSTINDEXTYPE + self.data['id'], data=json.dumps(self.data))


    @classmethod
    def bulk(cls, bibjson_list, idkey='id', refresh=False):
        data = ''
        for r in bibjson_list:
            data += json.dumps( {'index':{'_id':r[idkey]}} ) + '\n'
            data += json.dumps( r ) + '\n'
        r = requests.post(cls.HOSTINDEXTYPE + '_bulk', data=data)
        if refresh: cls.refresh()
        return r.json()


    @classmethod
    def refresh(cls):
        r = requests.post(cls.HOSTINDEX + '_refresh')
        return r.json()


    @classmethod
    def pull(cls, id_):
        '''Retrieve object by id.'''
        if id_ is None:
            return None
        try:
            out = requests.get(cls.HOSTINDEXTYPE + id_)
            if out.status_code == 404:
                return None
            else:
                return cls(**out.json())
        except:
            return None

    @classmethod
    def keys(cls,mapping=False,prefix=''):
        # return a sorted list of all the keys in the index
        if not mapping:
            mapping = cls.query(endpoint='_mapping')[cls.__type__]['properties']
        keys = []
        for item in mapping:
            if mapping[item].has_key('fields'):
                for item in mapping[item]['fields'].keys():
                    if item != 'exact' and not item.startswith('_'):
                        keys.append(prefix + item + app.config['FACET_FIELD'])
            else:
                keys = keys + cls.keys(mapping=mapping[item]['properties'],prefix=prefix+item+'.')
        keys.sort()
        return keys

    
    @classmethod
    def put_mapping(cls):
        mapping = app.config.get("MAPPINGS",{}).get(cls.__type__,None)
        if mapping is None:
            return False
        else:
            im = HOSTINDEXTYPE + '/_mapping'
            exists = requests.get(im)
            if exists.status_code != 200:
                ri = requests.post(HOSTINDEX)
            r = requests.put(im, json.dumps(mapping))
            return True


    @classmethod
    def mapping(cls):
        return cls.query(endpoint='_mapping')[cls.__type__]


    @classmethod
    def query(cls, recid='', endpoint='_search', q='', terms=None, facets=None, **kwargs):
        '''Perform a query on backend.

        :param recid: needed if endpoint is about a record, e.g. mlt
        :param endpoint: default is _search, but could be _mapping, _mlt, _flt etc.
        :param q: maps to query_string parameter if string, or query dict if dict.
        :param terms: dictionary of terms to filter on. values should be lists. 
        :param facets: dict of facets to return from the query.
        :param kwargs: any keyword args as per
            http://www.elasticsearch.org/guide/reference/api/search/uri-request.html
        '''
        if recid and not recid.endswith('/'): recid += '/'
        if isinstance(q,dict):
            query = q
        elif q:
            query = {'query': {'query_string': { 'query': q }}}
        else:
            query = {'query': {'match_all': {}}}

        if facets:
            if 'facets' not in query:
                query['facets'] = {}
            for k, v in facets.items():
                query['facets'][k] = {"terms":v}

        if terms:
            boolean = {'must': [] }
            for term in terms:
                if not isinstance(terms[term],list): terms[term] = [terms[term]]
                for val in terms[term]:
                    obj = {'term': {}}
                    obj['term'][ term ] = val
                    boolean['must'].append(obj)
            if q and not isinstance(q,dict):
                boolean['must'].append( {'query_string': { 'query': q } } )
            elif q and 'query' in q:
                boolean['must'].append( query['query'] )
            query['query'] = {'bool': boolean}

        for k,v in kwargs.items():
            if k == '_from':
                query['from'] = v
            else:
                query[k] = v

        if endpoint in ['_mapping']:
            r = requests.get(cls.HOSTINDEXTYPE + endpoint)
        else:
            r = requests.post(cls.HOSTINDEXTYPE + recid + endpoint, data=json.dumps(query))
        return r.json()

    def accessed(self):
        if 'last_access' not in self.data:
            self.data['last_access'] = []
        try:
            usr = current_user.id
        except:
            usr = "anonymous"
        self.data['last_access'].insert(0, { 'user':usr, 'date':datetime.now().strftime("%Y-%m-%d %H%M") } )
        r = requests.put(self.HOSTINDEXTYPE + self.data['id'], data=json.dumps(self.data))

    def delete(self):        
        r = requests.delete(self.HOSTINDEXTYPE + self.id)

    @classmethod
    def delete_type(cls):
        r = requests.delete(self.HOSTINDEXTYPE)

    @classmethod
    def delete_index(cls):
        r = requests.delete(self.HOSTINDEX)





