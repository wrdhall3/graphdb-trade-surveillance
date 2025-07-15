from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import uuid
import logging
import hashlib
from database.neo4j_connection import db_connection
from database.schema_discovery import schema_discovery
from models.trading_models import SuspiciousActivity, SuspiciousPatternType
import re # Added for regex in spoofing detection

logger = logging.getLogger(__name__)

class AdaptivePatternDetector:
    def __init__(self):
        self.db = db_connection
        self.schema = None
        self.trading_elements = None
        self._initialize_schema()
    
    def _generate_deterministic_id(self, pattern_type: str, trader_id: str, instrument: str, related_items: List[str]) -> str:
        """Generate a deterministic activity ID based on pattern characteristics"""
        try:
            # Create a consistent string representation of the pattern
            # Limit related_items to first 10 to avoid performance issues with large lists
            limited_items = related_items[:10] if related_items else []
            related_items_sorted = sorted(limited_items)
            pattern_key = f"{pattern_type}:{trader_id}:{instrument}:{':'.join(related_items_sorted)}"
            
            # Generate a deterministic hash
            hash_object = hashlib.md5(pattern_key.encode())
            deterministic_id = hash_object.hexdigest()
            
            return deterministic_id
        except Exception as e:
            logger.warning(f"Error generating deterministic ID: {e}, falling back to UUID")
            return str(uuid.uuid4())
    
    def _get_account_for_transaction(self, transaction_id: str) -> Optional[str]:
        """Get the Account ID for a given transaction using the PLACED relationship"""
        try:
            query = """
            MATCH (a:Account)-[:PLACED]->(t:Transaction)
            WHERE t.transaction_id = $transaction_id
            RETURN a.account_id as account_id
            LIMIT 1
            """
            results = self.db.execute_query(query, {"transaction_id": transaction_id})
            if results and len(results) > 0:
                return results[0].get('account_id')
            return None
        except Exception as e:
            logger.warning(f"Error fetching account for transaction {transaction_id}: {e}")
            return None
    
    def _get_account_for_pattern(self, related_transactions: List[str]) -> Optional[str]:
        """Get the most common Account ID for a pattern based on related transactions"""
        try:
            if not related_transactions:
                return None
            
            # Take the first few transactions to avoid performance issues
            sample_transactions = related_transactions[:5]
            account_counts = {}
            
            for tx_id in sample_transactions:
                account_id = self._get_account_for_transaction(tx_id)
                if account_id:
                    account_counts[account_id] = account_counts.get(account_id, 0) + 1
            
            if account_counts:
                # Return the most common account_id
                return max(account_counts, key=account_counts.get)
            
            return None
        except Exception as e:
            logger.warning(f"Error determining account for pattern: {e}")
            return None
        
    def _initialize_schema(self):
        """Initialize and discover the database schema"""
        try:
            self.schema = schema_discovery.discover_full_schema()
            self.trading_elements = schema_discovery.find_trading_related_nodes()
            logger.info(f"Discovered {len(self.schema['node_labels'])} node types and {len(self.schema['relationship_types'])} relationship types")
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            self.schema = {'node_labels': [], 'relationship_types': [], 'node_properties': {}}
            self.trading_elements = {}
    
    def detect_all_patterns(self, lookback_hours: int = 168) -> List[SuspiciousActivity]:  # Changed from 24 to 168 hours (7 days)
        """Detect all available patterns based on the discovered schema"""
        all_activities = []
        
        if not self.schema or not self.trading_elements:
            logger.warning("No schema discovered, cannot detect patterns")
            return all_activities
        
        # Try to detect patterns based on what's available in the database
        try:
            spoofing_activities = self.detect_spoofing_patterns(lookback_hours)
            all_activities.extend(spoofing_activities)
            
            layering_activities = self.detect_layering_patterns(lookback_hours)
            all_activities.extend(layering_activities)
            
            # Detect unusual behavior patterns
            unusual_activities = self.detect_unusual_patterns(lookback_hours)
            all_activities.extend(unusual_activities)
            
            # Log summary of detected patterns
            pattern_summary = {}
            for activity in all_activities:
                pattern_type = activity.pattern_type.value if hasattr(activity.pattern_type, 'value') else str(activity.pattern_type)
                pattern_summary[pattern_type] = pattern_summary.get(pattern_type, 0) + 1
            
            logger.info(f"🔍 PATTERN DETECTION SUMMARY:")
            logger.info(f"   Total patterns found: {len(all_activities)}")
            for pattern_type, count in pattern_summary.items():
                logger.info(f"   - {pattern_type}: {count} patterns")
            
            if all_activities:
                logger.info(f"🚨 DETAILED PATTERN BREAKDOWN:")
                for i, activity in enumerate(all_activities, 1):
                    # Use only related_trades since we only have transactions, not orders
                    all_tx_ids = activity.related_trades
                    transaction_ids = ", ".join(all_tx_ids[:5]) if all_tx_ids else "None"
                    if len(all_tx_ids) > 5:
                        transaction_ids += f" (+{len(all_tx_ids) - 5} more)"
                    
                    logger.info(f"   Pattern #{i}: {activity.pattern_type.value if hasattr(activity.pattern_type, 'value') else activity.pattern_type} "
                              f"| Entity: {activity.trader_id} "
                              f"| Confidence: {activity.confidence_score:.2f} "
                              f"| Severity: {activity.severity} "
                              f"| Transaction IDs: {transaction_ids}")
            
        except Exception as e:
            logger.error(f"Error in pattern detection: {e}")
        
        return all_activities
    
    def detect_spoofing_patterns(self, lookback_hours: int = 168) -> List[SuspiciousActivity]:  # Changed from 24 to 168 hours (7 days)
        """Detect spoofing-like patterns based on available schema"""
        activities = []
        
        # Find suitable nodes and relationships for spoofing detection
        detection_config = self._identify_spoofing_elements()
        if not detection_config:
            logger.info("No suitable elements found for spoofing detection")
            return activities
        
        try:
            query = self._build_spoofing_query(detection_config, lookback_hours)
            if not query:
                return activities
                
            logger.info(f"Executing spoofing query with lookback_hours={lookback_hours}")
            results = self.db.execute_query(query, {"lookback_hours": lookback_hours})
            logger.info(f"Spoofing query returned {len(results)} results: {results}")
            
            # If no results with current relationship, try alternative patterns
            if not results and detection_config.get('entity_connection'):
                logger.info("No results with current relationship, trying alternatives...")
                
                # Get available relationship types from schema to avoid warnings
                available_relationships = self.schema.get('relationship_types', [])
                logger.info(f"Available relationships in database: {available_relationships}")
                
                # Try alternative relationships that actually exist
                alternatives = ['PLACED_BY', 'EXECUTED_BY', 'OWNS', 'HAS', 'BELONGS_TO']
                for alt_rel in alternatives:
                    if alt_rel in available_relationships and alt_rel != detection_config['entity_connection']['relationship']:
                        logger.info(f"Trying alternative relationship: {alt_rel}")
                        alt_config = detection_config.copy()
                        alt_config['entity_connection']['relationship'] = alt_rel
                        alt_query = self._build_spoofing_query(alt_config, lookback_hours)
                        if alt_query:
                            logger.info(f"Trying alternative query with {alt_rel}:\n{alt_query}")
                            alt_results = self.db.execute_query(alt_query, {"lookback_hours": lookback_hours})
                            logger.info(f"{alt_rel} query returned {len(alt_results)} results: {alt_results}")
                            if alt_results:
                                results = alt_results
                                detection_config = alt_config
                                break  # Found working relationship, stop trying others
                
                # If still no results, try without entity grouping - just find cancelled transactions
                if not results:
                    logger.info("No results with entity grouping, trying system-wide cancelled transaction detection...")
                    id_prop = self._find_id_property(detection_config['primary_node_properties']) or 'transaction_id'
                    simple_query = f"""
                    MATCH (n:{detection_config['primary_node']})
                    WHERE n.{detection_config['time_property']} >= datetime() - duration({{hours: $lookback_hours}})
                      AND n.{detection_config['status_property']} =~ '.*(?i)(cancel|abort|reject).*'
                    WITH collect(n) as cancelled_nodes, count(n) as cancelled_count
                    WHERE cancelled_count > 0
                    RETURN 'system_wide' as entity_id, 'unknown' as instrument, 
                           cancelled_count as total_items, cancelled_count as cancelled_count,
                           [node IN cancelled_nodes | node.{id_prop}][0..10] as related_items
                    """
                    logger.info(f"Trying simple system-wide query:\n{simple_query}")
                    simple_results = self.db.execute_query(simple_query, {"lookback_hours": lookback_hours})
                    logger.info(f"System-wide query returned {len(simple_results)} results: {simple_results}")
                    if simple_results:
                        results = simple_results
            
            for result in results:
                confidence_score = self._calculate_confidence_score(result, 'spoofing')
                
                if confidence_score >= 0.4:  # Lowered from 0.6 for smaller datasets
                    # Extract and ensure related_items is a proper list
                    related_items = result.get('related_items', [])
                    if related_items is None:
                        related_items = []
                    elif not isinstance(related_items, list):
                        # Handle case where it might be a single item or nested list
                        if isinstance(related_items, str):
                            related_items = [related_items]
                        else:
                            related_items = list(related_items) if related_items else []
                    
                    # Flatten any nested lists (common issue with Cypher results)
                    flattened_items = []
                    for item in related_items:
                        if isinstance(item, list):
                            flattened_items.extend(item)
                        else:
                            flattened_items.append(item)
                    
                    # Fallback: If no transaction IDs found, try to query for them directly
                    if not flattened_items:
                        logger.warning("⚠️ No transaction IDs found in primary query, attempting fallback query...")
                        try:
                            fallback_query = f"""
                            MATCH (n:{detection_config['primary_node']})
                            WHERE n.{detection_config['time_property']} >= datetime() - duration({{hours: $lookback_hours}})
                              AND n.{detection_config['status_property']} =~ '.*(?i)(cancel|abort|reject).*'
                            RETURN collect(n.{self._find_id_property(detection_config['primary_node_properties']) or 'transaction_id'})[0..10] as transaction_ids
                            """
                            fallback_results = self.db.execute_query(fallback_query, {"lookback_hours": lookback_hours})
                            if fallback_results and fallback_results[0].get('transaction_ids'):
                                flattened_items = fallback_results[0]['transaction_ids']
                                logger.info(f"✅ Fallback query found transaction IDs: {flattened_items}")
                        except Exception as e:
                            logger.error(f"❌ Fallback query failed: {e}")
                    
                    trader_id = result.get('entity_id', 'unknown')
                    instrument = result.get('instrument', 'unknown') or 'unknown'
                    activity_id = self._generate_deterministic_id('SPOOFING', trader_id, instrument, flattened_items)
                    
                    # Get account information for this pattern
                    account_id = self._get_account_for_pattern(flattened_items)
                    
                    activity = SuspiciousActivity(
                        activity_id=activity_id,
                        pattern_type=SuspiciousPatternType.SPOOFING,
                        trader_id=trader_id,
                        account_id=account_id,
                        instrument=instrument,
                        confidence_score=confidence_score,
                        timestamp=datetime.now(),
                        description=self._generate_spoofing_description(result),
                        related_trades=flattened_items,
                        related_orders=[],
                        severity=self._determine_severity(confidence_score)
                    )
                    activities.append(activity)
                    logger.info(f"🚨 SPOOFING PATTERN DETECTED: "
                              f"Entity={activity.trader_id}, "
                              f"Confidence={confidence_score:.2f}, "
                              f"Severity={activity.severity}, "
                              f"Description={activity.description}, "
                              f"Related_Transactions={activity.related_trades}")
                    
        except Exception as e:
            logger.error(f"Error detecting spoofing patterns: {e}")
            
        logger.info(f"Spoofing detection completed: Found {len(activities)} spoofing patterns")
        return activities
    
    def detect_layering_patterns(self, lookback_hours: int = 168) -> List[SuspiciousActivity]:  # Changed from 24 to 168 hours (7 days)
        """Detect layering-like patterns based on available schema"""
        activities = []
        
        detection_config = self._identify_layering_elements()
        if not detection_config:
            logger.info("No suitable elements found for layering detection")
            return activities
        
        try:
            primary_node = detection_config.get('primary_node')
            time_prop = detection_config.get('time_property')
            primary_id_prop = self._find_id_property(detection_config.get('primary_node_properties', {}))
            
            entity_conn = detection_config.get('entity_connection')
            
            query = self._build_layering_query(detection_config, lookback_hours)
            if not query:
                logger.info("No layering query could be built")
                return activities
                
            logger.info(f"Executing layering query with lookback_hours={lookback_hours}")
            results = self.db.execute_query(query, {"lookback_hours": lookback_hours})
            logger.info(f"Layering query returned {len(results)} results: {results}")
            
            # If no results with current relationship, try alternative patterns
            if not results and detection_config.get('entity_connection'):
                logger.info("No results with current relationship, trying alternatives...")
                
                # Get available relationship types from schema to avoid warnings
                available_relationships = self.schema.get('relationship_types', [])
                logger.info(f"Available relationships in database: {available_relationships}")
                
                # Try alternative relationships that actually exist
                alternatives = ['PLACED_BY', 'EXECUTED_BY', 'OWNS', 'HAS', 'BELONGS_TO']
                for alt_rel in alternatives:
                    if alt_rel in available_relationships and alt_rel != detection_config['entity_connection']['relationship']:
                        logger.info(f"Trying alternative relationship: {alt_rel}")
                        alt_config = detection_config.copy()
                        alt_config['entity_connection']['relationship'] = alt_rel
                        alt_query = self._build_layering_query(alt_config, lookback_hours)
                        if alt_query:
                            logger.info(f"Trying alternative layering query with {alt_rel}:\n{alt_query}")
                            alt_results = self.db.execute_query(alt_query, {"lookback_hours": lookback_hours})
                            logger.info(f"{alt_rel} query returned {len(alt_results)} results: {alt_results}")
                            if alt_results:
                                results = alt_results
                                detection_config = alt_config
                                break  # Found working relationship, stop trying others
                
                # If still no results, try system-wide layering detection - look for security-based patterns
                if not results:
                    logger.info("No results with entity grouping, trying system-wide layering detection...")
                    id_prop = self._find_id_property(detection_config['primary_node_properties']) or 'transaction_id'
                    
                    # Look for security/instrument property
                    security_prop = None
                    for prop_name, prop_info in detection_config.get('primary_node_properties', {}).items():
                        if any(keyword in prop_name.lower() for keyword in ['security', 'instrument', 'symbol']):
                            security_prop = prop_name
                            break
                    
                    if security_prop:
                        # Group by security for proper layering detection
                        simple_query = f"""
                        MATCH (n:{detection_config['primary_node']})
                        WHERE n.{detection_config['time_property']} >= datetime() - duration({{hours: $lookback_hours}})
                        WITH n.{security_prop} as instrument, collect(n) as items
                        WHERE size(items) >= 3
                        RETURN 'system_wide' as entity_id, instrument, 
                               size(items) as total_items,
                               [node IN items | node.{id_prop}][0..10] as related_items
                        ORDER BY size(items) DESC
                        LIMIT 1
                        """
                        logger.info(f"Trying security-based layering query:\n{simple_query}")
                    else:
                        # Fallback: look for first few transactions if no security property
                        simple_query = f"""
                        MATCH (n:{detection_config['primary_node']})
                        WHERE n.{detection_config['time_property']} >= datetime() - duration({{hours: $lookback_hours}})
                        WITH n ORDER BY n.{detection_config['time_property']} ASC
                        WITH collect(n)[0..3] as first_transactions
                        WHERE size(first_transactions) >= 3
                        RETURN 'system_wide' as entity_id, 'unknown' as instrument, 
                               size(first_transactions) as total_items,
                               [node IN first_transactions | node.{id_prop}] as related_items
                        """
                        logger.info(f"Trying sequential transaction fallback query:\n{simple_query}")
                    
                    simple_results = self.db.execute_query(simple_query, {"lookback_hours": lookback_hours})
                    logger.info(f"System-wide layering query returned {len(simple_results)} results: {simple_results}")
                    if simple_results:
                        results = simple_results
            
            for result in results:
                confidence_score = self._calculate_confidence_score(result, 'layering')
                
                if confidence_score >= 0.4:  # Lowered from 0.6 for smaller datasets
                    # Extract and ensure related_items is a proper list
                    related_items = result.get('related_items', [])
                    if related_items is None:
                        related_items = []
                    elif not isinstance(related_items, list):
                        if isinstance(related_items, str):
                            related_items = [related_items]
                        else:
                            related_items = list(related_items) if related_items else []
                    
                    # Flatten any nested lists
                    flattened_items = []
                    for item in related_items:
                        if isinstance(item, list):
                            flattened_items.extend(item)
                        else:
                            flattened_items.append(item)
                    
                    trader_id = result.get('entity_id', 'unknown')
                    instrument = result.get('instrument', 'unknown')
                    activity_id = self._generate_deterministic_id('LAYERING', trader_id, instrument, flattened_items)
                    
                    # Get account information for this pattern
                    account_id = self._get_account_for_pattern(flattened_items)
                    
                    activity = SuspiciousActivity(
                        activity_id=activity_id,
                        pattern_type=SuspiciousPatternType.LAYERING,
                        trader_id=trader_id,
                        account_id=account_id,
                        instrument=instrument,
                        confidence_score=confidence_score,
                        timestamp=datetime.now(),
                        description=self._generate_layering_description(result),
                        related_trades=flattened_items,
                        related_orders=[],
                        severity=self._determine_severity(confidence_score)
                    )
                    activities.append(activity)
                    logger.info(f"🚨 LAYERING PATTERN DETECTED: "
                              f"Entity={activity.trader_id}, "
                              f"Confidence={confidence_score:.2f}, "
                              f"Severity={activity.severity}, "
                              f"Description={activity.description}, "
                              f"Related_Transactions={activity.related_trades}")
                    
        except Exception as e:
            logger.error(f"Error detecting layering patterns: {e}")
            
        logger.info(f"Layering detection completed: Found {len(activities)} layering patterns")
        return activities
    
    def detect_unusual_patterns(self, lookback_hours: int = 24) -> List[SuspiciousActivity]:
        """Detect unusual activity patterns based on statistical analysis"""
        activities = []
        
        try:
            # Find nodes with high activity volumes
            volume_anomalies = self._detect_volume_anomalies(lookback_hours)
            activities.extend(volume_anomalies)
            
            # Find unusual time patterns
            time_anomalies = self._detect_time_anomalies(lookback_hours)
            activities.extend(time_anomalies)
            
        except Exception as e:
            logger.error(f"Error detecting unusual patterns: {e}")
            
        return activities
    
    def _identify_layering_elements(self) -> Optional[Dict[str, Any]]:
        """Identify database elements suitable for layering detection using specific schema relationships"""
        config = {}
        
        # Use the specific Transaction node for layering detection
        # Based on provided schema: Transaction nodes have PLACED_BY relationship to Trader
        transaction_props = self.schema['node_properties'].get('Transaction', {})
        
        if not transaction_props:
            logger.warning("No Transaction node found in schema")
            return None
        
        config['primary_node'] = 'Transaction'
        config['primary_node_properties'] = transaction_props
        
        # Find temporal property
        config['time_property'] = self._find_temporal_property(transaction_props)
        
        # Find status property (optional for layering)
        config['status_property'] = self._find_status_property(transaction_props)
        
        # Use the specific PLACED_BY relationship to connect to Trader
        config['entity_connection'] = {
            'relationship': 'PLACED_BY',
            'target_label': 'Trader',
            'direction': 'outgoing'
        }
        
        # Add support for CONNECTED_TO relationship for layering detection
        config['connected_to_relationship'] = 'CONNECTED_TO'
        
        logger.info(f"Layering detection config: primary_node={config['primary_node']}, "
                   f"time_property={config.get('time_property')}, "
                   f"status_property={config.get('status_property')}, "
                   f"entity_connection={config.get('entity_connection')}, "
                   f"connected_to_relationship={config.get('connected_to_relationship')}")
        
        return config if config.get('time_property') else None
    
    def _identify_spoofing_elements(self) -> Optional[Dict[str, Any]]:
        """Identify database elements suitable for spoofing detection using specific schema relationships"""
        config = {}
        
        # Use the specific Transaction node for spoofing detection
        # Based on provided schema: Transaction nodes have PLACED_BY relationship to Trader
        transaction_props = self.schema['node_properties'].get('Transaction', {})
        
        if not transaction_props:
            logger.warning("No Transaction node found in schema")
            return None
        
        config['primary_node'] = 'Transaction'
        config['primary_node_properties'] = transaction_props
        
        # Find temporal property
        config['time_property'] = self._find_temporal_property(transaction_props)
        
        # Find status property for cancellation detection
        config['status_property'] = self._find_status_property(transaction_props)
        
        # Use the specific PLACED_BY relationship to connect to Trader
        config['entity_connection'] = {
            'relationship': 'PLACED_BY',
            'target_label': 'Trader',
            'direction': 'outgoing'
        }
        
        logger.info(f"Spoofing detection config: primary_node={config['primary_node']}, "
                   f"time_property={config.get('time_property')}, "
                   f"status_property={config.get('status_property')}, "
                   f"entity_connection={config.get('entity_connection')}")
        
        return config if config.get('time_property') else None
    
    def _find_temporal_property(self, properties: Dict[str, Any]) -> Optional[str]:
        """Find the best temporal property in a node"""
        time_keywords = ['timestamp', 'time', 'date', 'created', 'updated', 'when']
        
        for prop_name in properties.keys():
            prop_lower = prop_name.lower()
            for keyword in time_keywords:
                if keyword in prop_lower:
                    return prop_name
        return None
    
    def _find_status_property(self, properties: Dict[str, Any]) -> Optional[str]:
        """Find the best status property in a node"""
        status_keywords = ['status', 'state', 'condition']
        
        for prop_name in properties.keys():
            prop_lower = prop_name.lower()
            for keyword in status_keywords:
                if keyword in prop_lower:
                    return prop_name
        return None
    
    def _find_entity_connection(self, node_label: str) -> Optional[Dict[str, Any]]:
        """Find how to connect to trader/user entities"""
        # Look for relationships that connect to potential trader nodes
        potential_trader_labels = [node['label'] for node in self.trading_elements.get('potential_trader_nodes', [])]
        
        for pattern in self.schema.get('relationship_patterns', []):
            source_labels = pattern['source_labels']
            target_labels = pattern['target_labels'] 
            rel_type = pattern['relationship_type']
            
            # Check if this node connects outgoing to trader nodes
            if node_label in source_labels:
                for target_label in target_labels:
                    if target_label in potential_trader_labels:
                        return {
                            'relationship': rel_type, 
                            'target_label': target_label, 
                            'direction': 'outgoing'
                        }
            
            # Check if this node connects incoming from trader nodes  
            if node_label in target_labels:
                for source_label in source_labels:
                    if source_label in potential_trader_labels:
                        return {
                            'relationship': rel_type,
                            'target_label': source_label, 
                            'direction': 'incoming'
                        }
        
        return None
    
    def _find_id_property(self, node_properties: Dict[str, Any]) -> Optional[str]:
        """Find a suitable ID property for a node type"""
        # Look for common ID property patterns
        id_candidates = []
        
        for prop_name in node_properties.keys():
            prop_lower = prop_name.lower()
            if prop_lower in ['id', 'uuid', 'guid']:
                return prop_name
            elif 'id' in prop_lower or 'key' in prop_lower:
                id_candidates.append(prop_name)
        
        # Return first candidate or None
        return id_candidates[0] if id_candidates else None

    def _build_spoofing_query(self, config: Dict[str, Any], lookback_hours: int) -> Optional[str]:
        """Build a spoofing detection query using specific schema relationships - looks for cancelled + non-cancelled transaction patterns"""
        primary_node = config['primary_node']
        time_prop = config['time_property']
        status_prop = config.get('status_property')
        primary_node_props = config.get('primary_node_properties', {})
        entity_conn = config.get('entity_connection')
        
        if not time_prop:
            logger.warning(f"No time property found for {primary_node}, cannot build spoofing query")
            return None
        
        # Find actual ID properties
        primary_id_prop = self._find_id_property(primary_node_props)
        
        # Build query using specific relationships for spoofing detection
        query_parts = []
        
        # Use the specific PLACED_BY relationship to connect Transaction to Trader
        if entity_conn and entity_conn['relationship'] == 'PLACED_BY':
            # Join with Security to get instrument information
            query_parts.append(f"MATCH (t:{primary_node})-[:PLACED_BY]->(trader:Trader)")
            query_parts.append(f"OPTIONAL MATCH (t)-[:INVOLVES]->(security:Security)")
        else:
            # Fallback to just transactions without trader grouping
            query_parts.append(f"MATCH (t:{primary_node})")
            query_parts.append(f"OPTIONAL MATCH (t)-[:INVOLVES]->(security:Security)")
        
        # Time filter
        query_parts.append(f"WHERE t.{time_prop} >= datetime() - duration({{hours: $lookback_hours}})")
        
        # Group by trader if entity connection available
        if entity_conn and entity_conn['relationship'] == 'PLACED_BY':
            query_parts.append("WITH trader, collect(t) as all_transactions, collect(DISTINCT security) as all_securities")
            query_parts.append("WHERE size(all_transactions) >= 2")
            
            # Get trader ID property
            trader_props = self.schema['node_properties'].get('Trader', {})
            trader_id_prop = self._find_id_property(trader_props) or 'trader_id'
            
            # Get security properties (use only properties that actually exist)
            security_props = self.schema['node_properties'].get('Security', {})
            
            # Filter out null securities and extract primary security using only real properties
            query_parts.append("WITH trader, all_transactions, [sec IN all_securities WHERE sec IS NOT NULL] as securities")
            query_parts.append("WITH trader, all_transactions, securities,")
            query_parts.append(f"  CASE")
            query_parts.append(f"    WHEN size(securities) > 0 AND securities[0].symbol IS NOT NULL THEN securities[0].symbol")
            query_parts.append(f"    WHEN size(securities) > 0 AND securities[0].cusip IS NOT NULL THEN securities[0].cusip")
            query_parts.append(f"    ELSE 'unknown'")
            query_parts.append(f"  END as primary_security")
            
            # Separate cancelled and non-cancelled transactions
            if status_prop:
                query_parts.append(f"WITH trader, all_transactions, primary_security,")
                query_parts.append(f"  [tx IN all_transactions WHERE tx.{status_prop} IS NOT NULL AND tx.{status_prop} =~ '.*(?i)(cancel|abort|reject).*'] as cancelled_transactions,")
                query_parts.append(f"  [tx IN all_transactions WHERE tx.{status_prop} IS NULL OR NOT (tx.{status_prop} =~ '.*(?i)(cancel|abort|reject).*')] as executed_transactions")
                
                # Spoofing pattern: Must have both cancelled and executed transactions
                query_parts.append("WHERE size(cancelled_transactions) > 0 AND size(executed_transactions) > 0")
                
                # Return results with trader identification - include BOTH cancelled and executed transactions
                return_clause = f"RETURN trader.{trader_id_prop} as entity_id, primary_security as instrument, "
                return_clause += "size(all_transactions) as total_items, size(cancelled_transactions) as cancelled_count"
                if primary_id_prop:
                    # Return ALL transactions involved in spoofing (both cancelled and executed)
                    return_clause += f", [tx IN all_transactions | tx.{primary_id_prop}][0..10] as related_items"
                else:
                    return_clause += ", [tx IN all_transactions | toString(id(tx))][0..10] as related_items"
            else:
                # No status property - just look for multiple transaction patterns
                query_parts.append("WHERE size(all_transactions) >= 2")
                return_clause = f"RETURN trader.{trader_id_prop} as entity_id, primary_security as instrument, "
                return_clause += "size(all_transactions) as total_items, 0 as cancelled_count"
                if primary_id_prop:
                    return_clause += f", [tx IN all_transactions | tx.{primary_id_prop}][0..10] as related_items"
                else:
                    return_clause += ", [tx IN all_transactions | toString(id(tx))][0..10] as related_items"
        else:
            # System-wide fallback if no entity connection
            query_parts.append("WITH collect(t) as all_transactions, collect(DISTINCT security) as all_securities")
            query_parts.append("WHERE size(all_transactions) >= 2")
            
            # Get security properties (use only properties that actually exist)
            security_props = self.schema['node_properties'].get('Security', {})
            
            # Filter out null securities and extract primary security using only real properties
            query_parts.append("WITH all_transactions, [sec IN all_securities WHERE sec IS NOT NULL] as securities")
            query_parts.append("WITH all_transactions, securities,")
            query_parts.append(f"  CASE")
            query_parts.append(f"    WHEN size(securities) > 0 AND securities[0].symbol IS NOT NULL THEN securities[0].symbol")
            query_parts.append(f"    WHEN size(securities) > 0 AND securities[0].cusip IS NOT NULL THEN securities[0].cusip")
            query_parts.append(f"    ELSE 'unknown'")
            query_parts.append(f"  END as primary_security")
            
            if status_prop:
                query_parts.append(f"WITH all_transactions, primary_security,")
                query_parts.append(f"  [tx IN all_transactions WHERE tx.{status_prop} IS NOT NULL AND tx.{status_prop} =~ '.*(?i)(cancel|abort|reject).*'] as cancelled_transactions,")
                query_parts.append(f"  [tx IN all_transactions WHERE tx.{status_prop} IS NULL OR NOT (tx.{status_prop} =~ '.*(?i)(cancel|abort|reject).*')] as executed_transactions")
                
                # Spoofing pattern: Must have both cancelled and executed transactions
                query_parts.append("WHERE size(cancelled_transactions) > 0 AND size(executed_transactions) > 0")
                
                return_clause = "RETURN 'system_wide' as entity_id, primary_security as instrument, "
                return_clause += "size(all_transactions) as total_items, size(cancelled_transactions) as cancelled_count"
                if primary_id_prop:
                    return_clause += f", [tx IN all_transactions | tx.{primary_id_prop}][0..10] as related_items"
                else:
                    return_clause += ", [tx IN all_transactions | toString(id(tx))][0..10] as related_items"
            else:
                return_clause = f"RETURN 'system_wide' as entity_id, primary_security as instrument, "
                return_clause += "size(all_transactions) as total_items, 0 as cancelled_count"
                if primary_id_prop:
                    return_clause += f", [tx IN all_transactions | tx.{primary_id_prop}][0..10] as related_items"
                else:
                    return_clause += ", [tx IN all_transactions | toString(id(tx))][0..10] as related_items"
        
        query_parts.append(return_clause)
        
        final_query = "\n".join(query_parts)
        logger.info(f"Generated spoofing query:\n{final_query}")
        
        return final_query
    
    def _build_layering_query(self, config: Dict[str, Any], lookback_hours: int) -> Optional[str]:
        """Build a layering detection query using specific schema relationships and CONNECTED_TO patterns"""
        primary_node = config['primary_node']
        time_prop = config['time_property']
        primary_node_properties = config.get('primary_node_properties', {})
        entity_conn = config.get('entity_connection')
        connected_to_rel = config.get('connected_to_relationship', 'CONNECTED_TO')
        
        if not time_prop:
            logger.warning(f"No time property found for {primary_node}, cannot build layering query")
            return None
        
        # Find actual ID properties
        primary_id_prop = self._find_id_property(primary_node_properties)
        
        # Build query using specific relationships for layering detection
        query_parts = []
        
        # Use the specific PLACED_BY relationship to connect Transaction to Trader
        if entity_conn and entity_conn['relationship'] == 'PLACED_BY':
            # First, let's find traders with multiple transactions (basic layering pattern)
            query_parts.append(f"MATCH (t:{primary_node})-[:PLACED_BY]->(trader:Trader)")
            
            # Time filter
            query_parts.append(f"WHERE t.{time_prop} >= datetime() - duration({{hours: $lookback_hours}})")
            
            # Group by trader and collect transactions
            query_parts.append("WITH trader, collect(t) as transactions")
            query_parts.append("WHERE size(transactions) >= 3")  # Need at least 3 transactions for layering
            
            # Get trader ID property
            trader_props = self.schema['node_properties'].get('Trader', {})
            trader_id_prop = self._find_id_property(trader_props) or 'trader_id'
            
            # Always try to extract security information via INVOLVES relationship
            # Security info is in separate Security nodes, not Transaction properties
            # Enhanced layering detection: Use similar pattern to spoofing detection
            query_parts.append("UNWIND transactions as tx")
            query_parts.append("OPTIONAL MATCH (tx)-[:INVOLVES]->(security:Security)")
            query_parts.append("WITH trader, collect(tx) as all_transactions, collect(DISTINCT security) as all_securities")
            query_parts.append("WHERE size(all_transactions) >= 2")  # At least 2 transactions per trader
            
            # Get security properties (use only properties that actually exist)
            security_props = self.schema['node_properties'].get('Security', {})
            
            # Filter out null securities and extract primary security with only existing properties
            query_parts.append("WITH trader, all_transactions, [sec IN all_securities WHERE sec IS NOT NULL] as securities")
            query_parts.append("WITH trader, all_transactions, securities,")
            query_parts.append(f"  CASE")
            query_parts.append(f"    WHEN size(securities) > 0 AND securities[0].symbol IS NOT NULL THEN securities[0].symbol")
            query_parts.append(f"    WHEN size(securities) > 0 AND securities[0].cusip IS NOT NULL THEN securities[0].cusip")
            query_parts.append(f"    ELSE 'unknown'")
            query_parts.append(f"  END as primary_security")
            
            # Filter transactions to find all transactions in connected chains (layering patterns)
            # For layering, we need to include ALL transactions in the connected sequence
            query_parts.append("WITH trader, all_transactions, primary_security,")
            query_parts.append("  [tx IN all_transactions WHERE EXISTS { (tx)-[:CONNECTED_TO]->(:Transaction) } OR EXISTS { ()-[:CONNECTED_TO]->(tx) }] as connected_chain_txs,")
            query_parts.append("  [tx IN all_transactions WHERE NOT EXISTS { (tx)-[:CONNECTED_TO]->(:Transaction) } AND NOT EXISTS { ()-[:CONNECTED_TO]->(tx) }] as isolated_txs")
            
            # Layering can be detected in connected chains or multiple isolated transactions
            query_parts.append("WHERE size(connected_chain_txs) >= 3 OR size(isolated_txs) >= 3")
            
            # For layering detection, prefer connected chains over isolated transactions
            query_parts.append("WITH trader, primary_security, connected_chain_txs, isolated_txs")
            query_parts.append("WITH trader, primary_security,")
            query_parts.append("  CASE")
            query_parts.append("    WHEN size(connected_chain_txs) >= 3 THEN connected_chain_txs")
            query_parts.append("    ELSE isolated_txs[0..3]")
            query_parts.append("  END as layering_transactions")
            
            # Return results with trader and security identification
            return_clause = f"RETURN trader.{trader_id_prop} as entity_id, primary_security as instrument, "
            return_clause += "size(layering_transactions) as total_items, 0 as cancelled_count"
            if primary_id_prop:
                return_clause += f", [tx IN layering_transactions | tx.{primary_id_prop}][0..10] as related_items"
            else:
                return_clause += ", [tx IN layering_transactions | toString(id(tx))][0..10] as related_items"
            return_clause += " ORDER BY size(layering_transactions) DESC"
        else:
            # System-wide fallback for layering detection
            query_parts.append(f"MATCH (t:{primary_node})")
            query_parts.append(f"WHERE t.{time_prop} >= datetime() - duration({{hours: $lookback_hours}})")
            
            # Look for security-based patterns as system-wide layering
            security_prop = None
            for prop_name in primary_node_properties.keys():
                if any(keyword in prop_name.lower() for keyword in ['security', 'instrument', 'symbol']):
                    security_prop = prop_name
                    break
            
            if security_prop:
                # Group by security for system-wide layering detection using INVOLVES relationship
                query_parts.append("OPTIONAL MATCH (t)-[:INVOLVES]->(s:Security)")
                query_parts.append("WITH collect(t) as all_transactions, collect(DISTINCT s) as all_securities")
                query_parts.append("WHERE size(all_transactions) >= 3")  # Need multiple transactions
                
                # Get security properties (use only properties that actually exist)
                security_props = self.schema['node_properties'].get('Security', {})
                
                # Filter out null securities and extract primary security with only existing properties
                query_parts.append("WITH all_transactions, [sec IN all_securities WHERE sec IS NOT NULL] as securities")
                query_parts.append("WITH all_transactions, securities,")
                query_parts.append(f"  CASE")
                query_parts.append(f"    WHEN size(securities) > 0 AND securities[0].symbol IS NOT NULL THEN securities[0].symbol")
                query_parts.append(f"    WHEN size(securities) > 0 AND securities[0].cusip IS NOT NULL THEN securities[0].cusip")
                query_parts.append(f"    ELSE 'unknown'")
                query_parts.append(f"  END as primary_security")
                
                # Check for CONNECTED_TO patterns within these transactions
                query_parts.append("WITH all_transactions, primary_security,")
                query_parts.append("  [tx IN all_transactions WHERE EXISTS { (tx)-[:CONNECTED_TO]->(:Transaction) }] as connected_txs,")
                query_parts.append("  [tx IN all_transactions WHERE NOT EXISTS { (tx)-[:CONNECTED_TO]->(:Transaction) }] as unconnected_txs")
                
                # Layering detected if there are connected transactions or many unconnected ones
                query_parts.append("WHERE size(connected_txs) > 0 OR size(unconnected_txs) >= 3")
                
                return_clause = "RETURN 'system_wide' as entity_id, primary_security as instrument, "
                return_clause += "size(all_transactions) as total_items, 0 as cancelled_count"
                if primary_id_prop:
                    return_clause += f", [tx IN all_transactions | tx.{primary_id_prop}][0..10] as related_items"
                else:
                    return_clause += ", [tx IN all_transactions | toString(id(tx))][0..10] as related_items"
                return_clause += " ORDER BY size(all_transactions) DESC"
            else:
                # Fallback: look for first few transactions if no security property
                query_parts.append(f"WITH t ORDER BY t.{time_prop} ASC")
                query_parts.append("WITH collect(t)[0..10] as transactions")
                query_parts.append("WHERE size(transactions) >= 3")
                
                return_clause = "RETURN 'system_wide' as entity_id, 'unknown' as instrument, "
                return_clause += "size(transactions) as total_items, 0 as cancelled_count"
                if primary_id_prop:
                    return_clause += f", [tx IN transactions | tx.{primary_id_prop}] as related_items"
                else:
                    return_clause += ", [tx IN transactions | toString(id(tx))] as related_items"
        
        query_parts.append(return_clause)
        
        final_query = "\n".join(query_parts)
        logger.info(f"Generated layering query:\n{final_query}")
        
        return final_query
    
    def _detect_volume_anomalies(self, lookback_hours: int) -> List[SuspiciousActivity]:
        """Detect volume anomalies across the database"""
        activities = []
        
        # Look for nodes with high activity in recent time
        for label in self.schema['node_labels']:
            props = self.schema['node_properties'].get(label, {})
            time_prop = self._find_temporal_property(props)
            
            if not time_prop:
                continue
            
            try:
                # Fixed query syntax - use proper variable names and structure
                query = f"""
                MATCH (n:{label})
                WHERE n.{time_prop} >= datetime() - duration({{hours: $lookback_hours}})
                WITH count(n) as recent_count
                
                MATCH (total_nodes:{label})
                WITH recent_count, count(total_nodes) as total_count
                WHERE recent_count > total_count * 0.3 AND recent_count > 5
                RETURN recent_count, total_count, '{label}' as node_type
                """
                
                results = self.db.execute_query(query, {"lookback_hours": lookback_hours})
                
                for result in results:
                    if result['recent_count'] > 50:  # Increased threshold to avoid duplicating layering detection
                        # Extract transaction IDs if this is transaction volume anomaly
                        related_transactions = []
                        if label == 'Transaction' or 'transaction' in label.lower():
                            try:
                                # Get transaction IDs for volume anomaly - focus on most recent
                                id_prop = self._find_id_property(props) or 'transaction_id'
                                tx_query = f"""
                                MATCH (n:{label})
                                WHERE n.{time_prop} >= datetime() - duration({{hours: $lookback_hours}})
                                RETURN collect(n.{id_prop})[0..5] as transaction_ids
                                """
                                tx_results = self.db.execute_query(tx_query, {"lookback_hours": lookback_hours})
                                if tx_results and tx_results[0].get('transaction_ids'):
                                    related_transactions = tx_results[0]['transaction_ids']
                                    logger.info(f"Volume anomaly found transaction IDs: {related_transactions}")
                            except Exception as e:
                                logger.error(f"Failed to get transaction IDs for volume anomaly: {e}")
                        
                        # Skip if this is a transaction volume anomaly (let layering detection handle it)
                        if label == 'Transaction' or 'transaction' in label.lower():
                            logger.info(f"Skipping transaction volume anomaly - handled by layering detection")
                            continue
                        
                        # Use LAYERING for non-transaction volume-based patterns
                        trader_id = 'system_wide'
                        instrument = result['node_type']
                        activity_id = self._generate_deterministic_id('VOLUME_ANOMALY', trader_id, instrument, related_transactions)
                        
                        # Get account information for this pattern
                        account_id = self._get_account_for_pattern(related_transactions)
                        
                        activity = SuspiciousActivity(
                            activity_id=activity_id,
                            pattern_type=SuspiciousPatternType.LAYERING,  # Volume-based patterns are more like layering
                            trader_id=trader_id,
                            account_id=account_id,
                            instrument=instrument,
                            confidence_score=0.6,
                            timestamp=datetime.now(),
                            description=f"High volume anomaly: {result['recent_count']} {result['node_type']} records in last {lookback_hours} hours",
                            related_trades=related_transactions,
                            related_orders=[],
                            severity="MEDIUM"
                        )
                        activities.append(activity)
                        logger.info(f"🚨 VOLUME ANOMALY DETECTED: "
                                  f"Type={result['node_type']}, "
                                  f"Count={result['recent_count']}, "
                                  f"Transaction_IDs={related_transactions[:3] if related_transactions else 'N/A'}")
                        
            except Exception as e:
                logger.error(f"Error detecting volume anomalies for {label}: {e}")
        
        return activities
    
    def _detect_time_anomalies(self, lookback_hours: int) -> List[SuspiciousActivity]:
        """Detect unusual time-based patterns"""
        # This could detect things like activity outside normal hours, etc.
        return []  # Placeholder for now
    
    def _calculate_confidence_score(self, result: Dict[str, Any], pattern_type: str) -> float:
        """Calculate confidence score based on result metrics and pattern type"""
        
        if pattern_type == 'spoofing':
            return self._calculate_spoofing_confidence(result)
        elif pattern_type == 'layering':
            return self._calculate_layering_confidence(result)
        else:
            # Default calculation for other patterns
            return self._calculate_default_confidence(result)
    
    def _calculate_spoofing_confidence(self, result: Dict[str, Any]) -> float:
        """Calculate confidence score for spoofing patterns"""
        confidence = 0.5  # Base confidence
        
        # Adjust based on cancellation metrics
        if 'cancelled_count' in result and 'total_items' in result:
            cancellation_rate = result['cancelled_count'] / max(result['total_items'], 1)
            confidence += cancellation_rate * 0.4
        
        # Volume bonus
        if 'total_items' in result:
            if result['total_items'] >= 20:
                confidence += 0.2
            elif result['total_items'] >= 10:
                confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _calculate_layering_confidence(self, result: Dict[str, Any]) -> float:
        """Calculate confidence score for layering patterns"""
        confidence = 0.6  # Higher base confidence for layering
        
        # Volume-based confidence (layering requires multiple transactions)
        if 'total_items' in result:
            total_items = result['total_items']
            if total_items >= 10:
                confidence += 0.3  # High volume = higher confidence
            elif total_items >= 5:
                confidence += 0.2  # Medium volume
            elif total_items >= 3:
                confidence += 0.1  # Minimum volume for layering
        
        # Security-specific patterns increase confidence
        if 'instrument' in result and result['instrument'] != 'unknown':
            confidence += 0.1  # Bonus for security-specific patterns
        
        # Entity-specific patterns (not system_wide) increase confidence
        if 'entity_id' in result and result['entity_id'] != 'system_wide':
            confidence += 0.1  # Bonus for trader-specific patterns
        
        # Transaction ID availability increases confidence
        if 'related_items' in result and result['related_items']:
            if len(result['related_items']) >= 5:
                confidence += 0.1  # Many related transactions
            elif len(result['related_items']) >= 3:
                confidence += 0.05  # Some related transactions
        
        return min(confidence, 1.0)
    
    def _calculate_default_confidence(self, result: Dict[str, Any]) -> float:
        """Default confidence calculation for other pattern types"""
        confidence = 0.5  # Base confidence
        
        # Adjust based on available metrics
        if 'cancelled_count' in result and 'total_items' in result:
            cancellation_rate = result['cancelled_count'] / max(result['total_items'], 1)
            confidence += cancellation_rate * 0.4
        
        if 'total_items' in result:
            if result['total_items'] >= 20:
                confidence += 0.2
            elif result['total_items'] >= 10:
                confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _generate_spoofing_description(self, result: Dict[str, Any]) -> str:
        """Generate description for spoofing pattern"""
        desc = "Potential spoofing activity detected"
        
        total_items = result.get('total_items', 0)
        cancelled_count = result.get('cancelled_count', 0)
        executed_count = total_items - cancelled_count
        
        if total_items > 0:
            desc += f": {total_items} transactions analyzed"
            
            if cancelled_count > 0 and executed_count > 0:
                desc += f" ({cancelled_count} cancelled, {executed_count} executed)"
            elif cancelled_count > 0:
                desc += f" ({cancelled_count} cancelled)"
            elif executed_count > 0:
                desc += f" ({executed_count} executed)"
        
        # Include transaction IDs in the description for better visibility
        if 'related_items' in result and result['related_items']:
            transaction_ids = result['related_items'][:5]  # Show first 5 transaction IDs
            ids_str = ", ".join(str(tid) for tid in transaction_ids)
            if len(result['related_items']) > 5:
                ids_str += f" (+{len(result['related_items']) - 5} more)"
            desc += f". Transaction IDs: {ids_str}"
        
        return desc
    
    def _generate_layering_description(self, result: Dict[str, Any]) -> str:
        """Generate description for layering pattern"""
        desc = "Potential layering activity detected"
        
        total_items = result.get('total_items', 0)
        
        if total_items > 0:
            desc += f": {total_items} transactions analyzed"
        
        # Include transaction IDs in the description for better visibility
        if 'related_items' in result and result['related_items']:
            transaction_ids = result['related_items'][:5]  # Show first 5 transaction IDs
            ids_str = ", ".join(str(tid) for tid in transaction_ids)
            if len(result['related_items']) > 5:
                ids_str += f" (+{len(result['related_items']) - 5} more)"
            desc += f". Transaction IDs: {ids_str}"
        
        return desc
    
    def _determine_severity(self, confidence_score: float) -> str:
        """Determine severity based on confidence score"""
        if confidence_score >= 0.9:
            return "CRITICAL"
        elif confidence_score >= 0.8:
            return "HIGH"
        elif confidence_score >= 0.7:
            return "MEDIUM"
        else:
            return "LOW"

# Global adaptive detector instance
adaptive_detector = AdaptivePatternDetector() 