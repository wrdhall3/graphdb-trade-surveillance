from typing import Dict, List, Any, Optional, Set
import logging
from database.neo4j_connection import db_connection

logger = logging.getLogger(__name__)

class SchemaDiscovery:
    def __init__(self):
        self.db = db_connection
        self._schema_cache = None
    
    def discover_full_schema(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Discover the complete schema of the Neo4j database"""
        if self._schema_cache and not force_refresh:
            return self._schema_cache
        
        logger.info("Discovering Neo4j database schema...")
        
        schema = {
            'node_labels': self._get_node_labels(),
            'relationship_types': self._get_relationship_types(),
            'property_keys': self._get_property_keys(),
            'node_properties': {},
            'relationship_properties': {},
            'node_counts': {},
            'relationship_patterns': [],
            'indexes': self._get_indexes(),
            'constraints': self._get_constraints()
        }
        
        # Discover properties for each node label
        for label in schema['node_labels']:
            schema['node_properties'][label] = self._get_node_properties(label)
            schema['node_counts'][label] = self._get_node_count(label)
        
        # Discover relationship patterns and properties
        schema['relationship_patterns'] = self._discover_relationship_patterns()
        for rel_type in schema['relationship_types']:
            schema['relationship_properties'][rel_type] = self._get_relationship_properties(rel_type)
        
        self._schema_cache = schema
        return schema
    
    def _get_node_labels(self) -> List[str]:
        """Get all node labels in the database"""
        try:
            query = "CALL db.labels() YIELD label RETURN label ORDER BY label"
            results = self.db.execute_query(query)
            return [result['label'] for result in results]
        except Exception as e:
            logger.error(f"Error getting node labels: {e}")
            return []
    
    def _get_relationship_types(self) -> List[str]:
        """Get all relationship types in the database"""
        try:
            query = "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType"
            results = self.db.execute_query(query)
            return [result['relationshipType'] for result in results]
        except Exception as e:
            logger.error(f"Error getting relationship types: {e}")
            return []
    
    def _get_property_keys(self) -> List[str]:
        """Get all property keys in the database"""
        try:
            query = "CALL db.propertyKeys() YIELD propertyKey RETURN propertyKey ORDER BY propertyKey"
            results = self.db.execute_query(query)
            return [result['propertyKey'] for result in results]
        except Exception as e:
            logger.error(f"Error getting property keys: {e}")
            return []
    
    def _get_node_properties(self, label: str) -> Dict[str, Any]:
        """Get properties for a specific node label with sample values and types"""
        try:
            # Get sample of nodes to analyze properties
            query = f"MATCH (n:{label}) RETURN n LIMIT 100"
            results = self.db.execute_query(query)
            
            properties = {}
            for result in results:
                node = result['n']
                if hasattr(node, 'items'):
                    for key, value in node.items():
                        if key not in properties:
                            properties[key] = {
                                'type': type(value).__name__,
                                'sample_values': set(),
                                'null_count': 0,
                                'total_count': 0
                            }
                        
                        properties[key]['total_count'] += 1
                        if value is None:
                            properties[key]['null_count'] += 1
                        else:
                            # Keep sample values (limited to avoid memory issues)
                            if len(properties[key]['sample_values']) < 10:
                                properties[key]['sample_values'].add(str(value)[:100])  # Truncate long values
            
            # Convert sets to lists for JSON serialization
            for prop_info in properties.values():
                prop_info['sample_values'] = list(prop_info['sample_values'])
                
            return properties
        except Exception as e:
            logger.error(f"Error getting properties for {label}: {e}")
            return {}
    
    def _get_relationship_properties(self, rel_type: str) -> Dict[str, Any]:
        """Get properties for a specific relationship type"""
        try:
            query = f"MATCH ()-[r:{rel_type}]-() RETURN r LIMIT 100"
            results = self.db.execute_query(query)
            
            properties = {}
            for result in results:
                rel = result['r']
                if hasattr(rel, 'items'):
                    for key, value in rel.items():
                        if key not in properties:
                            properties[key] = {
                                'type': type(value).__name__,
                                'sample_values': set(),
                                'null_count': 0,
                                'total_count': 0
                            }
                        
                        properties[key]['total_count'] += 1
                        if value is None:
                            properties[key]['null_count'] += 1
                        else:
                            if len(properties[key]['sample_values']) < 10:
                                properties[key]['sample_values'].add(str(value)[:100])
            
            # Convert sets to lists
            for prop_info in properties.values():
                prop_info['sample_values'] = list(prop_info['sample_values'])
                
            return properties
        except Exception as e:
            logger.error(f"Error getting properties for relationship {rel_type}: {e}")
            return {}
    
    def _get_node_count(self, label: str) -> int:
        """Get count of nodes for a specific label"""
        try:
            query = f"MATCH (n:{label}) RETURN count(n) as count"
            results = self.db.execute_query(query)
            return results[0]['count'] if results else 0
        except Exception as e:
            logger.error(f"Error getting count for {label}: {e}")
            return 0
    
    def _discover_relationship_patterns(self) -> List[Dict[str, Any]]:
        """Discover relationship patterns between node types"""
        try:
            query = """
            MATCH (a)-[r]->(b)
            RETURN 
                labels(a) as source_labels,
                type(r) as relationship_type,
                labels(b) as target_labels,
                count(*) as count
            ORDER BY count DESC
            LIMIT 100
            """
            results = self.db.execute_query(query)
            
            patterns = []
            for result in results:
                pattern = {
                    'source_labels': result['source_labels'],
                    'relationship_type': result['relationship_type'],
                    'target_labels': result['target_labels'],
                    'count': result['count']
                }
                patterns.append(pattern)
            
            return patterns
        except Exception as e:
            logger.error(f"Error discovering relationship patterns: {e}")
            return []
    
    def _get_indexes(self) -> List[Dict[str, Any]]:
        """Get database indexes"""
        try:
            query = "SHOW INDEXES YIELD name, type, labelsOrTypes, properties, state RETURN name, type, labelsOrTypes, properties, state"
            return self.db.execute_query(query)
        except Exception as e:
            logger.warning(f"Could not retrieve indexes: {e}")
            return []
    
    def _get_constraints(self) -> List[Dict[str, Any]]:
        """Get database constraints"""
        try:
            query = "SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties RETURN name, type, labelsOrTypes, properties"
            return self.db.execute_query(query)
        except Exception as e:
            logger.warning(f"Could not retrieve constraints: {e}")
            return []
    
    def find_trading_related_nodes(self) -> Dict[str, Any]:
        """Identify which nodes might be related to trading based on property names"""
        schema = self.discover_full_schema()
        
        trading_indicators = {
            'trader_keywords': ['trader', 'user', 'client', 'account', 'participant'],
            'order_keywords': ['order', 'request', 'instruction'],
            'trade_keywords': ['trade', 'execution', 'transaction', 'deal'],
            'instrument_keywords': ['instrument', 'security', 'symbol', 'asset', 'stock'],
            'price_keywords': ['price', 'amount', 'value', 'cost'],
            'quantity_keywords': ['quantity', 'volume', 'size', 'amount'],
            'time_keywords': ['time', 'timestamp', 'date', 'created', 'updated'],
            'status_keywords': ['status', 'state', 'condition']
        }
        
        identified_nodes = {
            'potential_trader_nodes': [],
            'potential_order_nodes': [],
            'potential_trade_nodes': [],
            'potential_instrument_nodes': [],
            'temporal_properties': [],
            'price_properties': [],
            'quantity_properties': []
        }
        
        for label, properties in schema['node_properties'].items():
            label_lower = label.lower()
            prop_names = [prop.lower() for prop in properties.keys()]
            
            # Check node labels for trading concepts
            for keyword in trading_indicators['trader_keywords']:
                if keyword in label_lower:
                    identified_nodes['potential_trader_nodes'].append({
                        'label': label,
                        'properties': properties,
                        'reason': f'Label contains "{keyword}"'
                    })
            
            for keyword in trading_indicators['order_keywords']:
                if keyword in label_lower:
                    identified_nodes['potential_order_nodes'].append({
                        'label': label,
                        'properties': properties,
                        'reason': f'Label contains "{keyword}"'
                    })
            
            for keyword in trading_indicators['trade_keywords']:
                if keyword in label_lower:
                    identified_nodes['potential_trade_nodes'].append({
                        'label': label,
                        'properties': properties,
                        'reason': f'Label contains "{keyword}"'
                    })
            
            for keyword in trading_indicators['instrument_keywords']:
                if keyword in label_lower:
                    identified_nodes['potential_instrument_nodes'].append({
                        'label': label,
                        'properties': properties,
                        'reason': f'Label contains "{keyword}"'
                    })
            
            # Check properties for trading concepts
            for prop_name in prop_names:
                for keyword in trading_indicators['time_keywords']:
                    if keyword in prop_name:
                        identified_nodes['temporal_properties'].append({
                            'label': label,
                            'property': prop_name,
                            'type': properties[prop_name]['type']
                        })
                
                for keyword in trading_indicators['price_keywords']:
                    if keyword in prop_name:
                        identified_nodes['price_properties'].append({
                            'label': label,
                            'property': prop_name,
                            'type': properties[prop_name]['type']
                        })
                
                for keyword in trading_indicators['quantity_keywords']:
                    if keyword in prop_name:
                        identified_nodes['quantity_properties'].append({
                            'label': label,
                            'property': prop_name,
                            'type': properties[prop_name]['type']
                        })
        
        return identified_nodes
    
    def generate_sample_queries(self) -> List[Dict[str, str]]:
        """Generate sample queries based on the discovered schema"""
        schema = self.discover_full_schema()
        trading_nodes = self.find_trading_related_nodes()
        
        queries = []
        
        # Basic count queries for each node type
        for label in schema['node_labels']:
            queries.append({
                'description': f'Count all {label} nodes',
                'cypher': f'MATCH (n:{label}) RETURN count(n) as total_{label.lower()}_count'
            })
        
        # Relationship pattern queries
        for pattern in schema['relationship_patterns'][:5]:  # Top 5 patterns
            source_label = pattern['source_labels'][0] if pattern['source_labels'] else 'Node'
            target_label = pattern['target_labels'][0] if pattern['target_labels'] else 'Node'
            rel_type = pattern['relationship_type']
            
            queries.append({
                'description': f'Find {source_label} nodes connected to {target_label} via {rel_type}',
                'cypher': f'MATCH (a:{source_label})-[:{rel_type}]->(b:{target_label}) RETURN a, b LIMIT 10'
            })
        
        # Time-based queries if temporal properties exist
        for temp_prop in trading_nodes['temporal_properties'][:3]:
            label = temp_prop['label']
            prop = temp_prop['property']
            queries.append({
                'description': f'Find recent {label} nodes',
                'cypher': f'MATCH (n:{label}) WHERE n.{prop} IS NOT NULL RETURN n ORDER BY n.{prop} DESC LIMIT 10'
            })
        
        return queries

# Global schema discovery instance
schema_discovery = SchemaDiscovery() 