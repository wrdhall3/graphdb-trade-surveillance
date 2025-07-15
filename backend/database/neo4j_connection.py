from neo4j import GraphDatabase
from config import settings
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class Neo4jConnection:
    def __init__(self, uri: str, username: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        
    def close(self):
        if self.driver:
            self.driver.close()
            
    def execute_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a Cypher query and return results"""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]
    
    def execute_write_query(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a write query (CREATE, UPDATE, DELETE)"""
        with self.driver.session() as session:
            result = session.write_transaction(self._execute_query, query, parameters or {})
            return result
    
    def _execute_query(self, tx, query: str, parameters: Dict[str, Any]):
        result = tx.run(query, parameters)
        return [record.data() for record in result]
    
    def get_schema_info(self) -> Dict[str, Any]:
        """Get information about the database schema"""
        schema_info = {}
        
        # Get node labels
        node_labels_query = "CALL db.labels() YIELD label RETURN label"
        node_labels = self.execute_query(node_labels_query)
        schema_info['node_labels'] = [record['label'] for record in node_labels]
        
        # Get relationship types
        rel_types_query = "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
        rel_types = self.execute_query(rel_types_query)
        schema_info['relationship_types'] = [record['relationshipType'] for record in rel_types]
        
        # Get property keys
        prop_keys_query = "CALL db.propertyKeys() YIELD propertyKey RETURN propertyKey"
        prop_keys = self.execute_query(prop_keys_query)
        schema_info['property_keys'] = [record['propertyKey'] for record in prop_keys]
        
        # Get constraints
        constraints_query = "SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties RETURN name, type, labelsOrTypes, properties"
        try:
            constraints = self.execute_query(constraints_query)
            schema_info['constraints'] = constraints
        except Exception as e:
            logger.warning(f"Could not retrieve constraints: {e}")
            schema_info['constraints'] = []
            
        # Get indexes
        indexes_query = "SHOW INDEXES YIELD name, type, labelsOrTypes, properties RETURN name, type, labelsOrTypes, properties"
        try:
            indexes = self.execute_query(indexes_query)
            schema_info['indexes'] = indexes
        except Exception as e:
            logger.warning(f"Could not retrieve indexes: {e}")
            schema_info['indexes'] = []
            
        return schema_info
    
    def get_sample_data(self, label: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get sample data for a specific node label"""
        query = f"MATCH (n:{label}) RETURN n LIMIT {limit}"
        return self.execute_query(query)
    
    def get_relationship_sample(self, rel_type: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get sample relationships of a specific type"""
        query = f"MATCH (a)-[r:{rel_type}]->(b) RETURN a, r, b LIMIT {limit}"
        return self.execute_query(query)

# Global connection instance
db_connection = Neo4jConnection(
    uri=settings.neo4j_uri,
    username=settings.neo4j_username,
    password=settings.neo4j_password
) 