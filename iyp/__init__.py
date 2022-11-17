import logging
import sys
import datetime
from neo4j import GraphDatabase

NODE_CONSTRAINTS = {
        'AS': {
                'asn': set(['UNIQUE', 'NOT NULL'])
                } ,

        'PREFIX': {
                'prefix': set(['UNIQUE', 'NOT NULL']), 
                'af': set(['NOT NULL'])
                },
        
        'IP': {
                'ip': set(['UNIQUE', 'NOT NULL']),
                'af': set(['NOT NULL'])
                },

        'DOMAIN_NAME': {
                'name': set(['UNIQUE', 'NOT NULL'])
                },

        'COUNTRY': {
                'country_code': set(['UNIQUE', 'NOT NULL'])
                },

        'ORGANIZATION': {
                'name': set(['NOT NULL'])
                }
    }

# Set of node labels with constrains (ease search for node merging)
NODE_CONSTRAINTS_LABELS = set(NODE_CONSTRAINTS.keys())

def format_properties(prop):
    """Make sure certain properties are always formatted the same way.
    For example IPv6 addresses are stored in lowercase, or ASN are kept as 
    integer not string."""

    # asn is stored as an int
    if 'asn' in prop:
        prop['asn'] = int(prop['asn'])

    # ipv6 is stored in lowercase
    if 'ip' in prop:
        prop['ip'] = prop['ip'].lower()
    if 'prefix' in prop:
        prop['prefix'] = prop['prefix'].lower()

    # country code is kept in capital letter
    if 'country_code' in prop:
        prop['country_code'] = prop['country_code'].upper()

    return prop


def dict2str(d, eq=':', pfx=''):
    """Converts a python dictionary to a Cypher map."""

    data = [] 
    for key, value in d.items():
        if isinstance(value, str) and '"' in value:
            escaped = value.replace("'", r"\'")
            data.append(f"{pfx+key}{eq} '{escaped}'")
        elif isinstance(value, str) or isinstance(value, datetime.datetime):
            data.append(f'{pfx+key}{eq} "{value}"')
        else:
            data.append(f'{pfx+key}{eq} {value}')

    return '{'+','.join(data)+'}'


class IYP(object):

    def __init__(self):

        logging.debug('Wikihandy: Enter initialization')

        # TODO: get config from configuration file
        self.server = 'localhost'
        self.port = 7687
        self.login = "neo4j"
        self.password = "password"

        # Connect to the database
        uri = f"neo4j://{self.server}:{self.port}"
        self.db = GraphDatabase.driver(uri, auth=(self.login, self.password))

        if self.db is None:
            sys.exit('Could not connect to the Neo4j database!')
        else:
            self.session = self.db.session()

        self._db_init()


    def _db_init(self):
        """Add constraints (implictly add indexes for corresponding keys)"""

        for label, prop_constraints in NODE_CONSTRAINTS.items():
            for property, constraints in prop_constraints.items():

                for constraint in constraints:
                    constraint_formated = constraint.replace(' ', '')
                    self.session.run(
                        f" CREATE CONSTRAINT {label}_{constraint_formated}_{property} IF NOT EXISTS "
                        f" FOR (n:{label}) "
                        f" REQUIRE n.{property} IS {constraint} ")


    def get_node(self, type, prop, create=False):
        """Find the ID of a node in the graph. Return None if the node does not
        exist or create the node if create=True."""

        prop = format_properties(prop)

        # put type in a list
        type_str = str(type)
        if isinstance(type, list):
            type_str = ':'.join(type)
        else:
            type = [type]

        if create:
            has_constraints = NODE_CONSTRAINTS_LABELS.intersection(type)
            if len( has_constraints ):
                ### MERGE node with constraints
                ### Search on the constraints and set other values
                label = has_constraints.pop()
                constraint_prop = dict([ (c, prop[c]) for c in NODE_CONSTRAINTS[label].keys() ]) 
                #values = ', '.join([ f"a.{p} = {val}" for p, val in prop.items() ])
                labels = ', '.join([ f"a:{l}" for l in type])

                result = self.session.run (
                    f"""MERGE (a:{label} {dict2str(constraint_prop)}) 
                        ON MATCH
                            SET {dict2str(prop, eq='=', pfx='a.')[1:-1]}, {labels}
                        ON CREATE
                            SET {dict2str(prop, eq='=', pfx='a.')[1:-1]}, {labels}
                        RETURN ID(a)"""
                        ).single()
            else:
                ### MERGE node without constraints
                result = self.session.run(f"MERGE (a:{type_str} {dict2str(prop)}) RETURN ID(a)").single()
        else:
            ### MATCH node
            result = self.session.run(f"MATCH (a:{type_str} {dict2str(prop)}) RETURN ID(a)").single()

        if result is not None:
            return result[0]
        else:
            return None

    def get_node_extid(self, id_type, id):
        """Find a node in the graph which has an EXTERNAL_ID relationship with
        the given ID. Return None if the node does not exist."""

        result = self.session.run(f"MATCH (a)-[:EXTERNAL_ID]->(:{id_type} {{id:{id}}}) RETURN ID(a)").single()
        print(f"MATCH (a)-[:EXTERNAL_ID]->(:{id_type} {{id:{id}}}) RETURN ID(a)")

        if result is not None:
            return result[0]
        else:
            return None



    def add_links(self, src_node, links):
        """Create links from src_node to the destination nodes given in parameter
        links. This parameter is a list of [link_type, dst_node_id, prop_dict].
        The dictionary prop_dict should at least contain a 'source', 'point in time', 
        and 'reference URL'. Keys in this dictionary should contain no space.

        By convention link_type is written in UPPERCASE and keys in prop_dict are
        in lowercase."""

        
        for type, dst_node, prop in links:

            assert 'source' in prop
            assert 'reference_url' in prop
            assert 'point_in_time' in prop

            prop = format_properties(prop)

            self.session.run(
                " MATCH (a), (b) " 
                " WHERE ID(a) = $src_node AND ID(b) = $dst_node "
                f" MERGE (a)-[:{type}  {dict2str(prop)}]->(b) ",
                src_node=src_node, dst_node=dst_node).consume()


    def close(self):
        self.session.close()
        self.db.close()



