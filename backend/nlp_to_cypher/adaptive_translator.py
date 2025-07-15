from typing import Dict, Any, Optional, List
import re
import json
import logging
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from database.neo4j_connection import db_connection
from database.schema_discovery import schema_discovery
from models.trading_models import NLPQueryRequest, NLPQueryResponse, SchemaInfo
from config import settings

logger = logging.getLogger(__name__)

class AdaptiveNLPToCypherTranslator:
    def __init__(self):
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key is required for NLP to Cypher translation")
        
        self.llm = ChatOpenAI(
            temperature=0.1,
            model_name="gpt-4",
            openai_api_key=settings.openai_api_key
        )
        
        self.db = db_connection
        self.discovered_schema = None
        self.trading_elements = None
        self._initialize_schema()
        
    def _initialize_schema(self):
        """Initialize with discovered schema from the actual database"""
        try:
            self.discovered_schema = schema_discovery.discover_full_schema()
            self.trading_elements = schema_discovery.find_trading_related_nodes()
            logger.info(f"Initialized translator with {len(self.discovered_schema['node_labels'])} node types")
        except Exception as e:
            logger.error(f"Error initializing schema: {e}")
            self.discovered_schema = {'node_labels': [], 'relationship_types': [], 'node_properties': {}}
            self.trading_elements = {}
    
    def get_discovered_schema_info(self) -> SchemaInfo:
        """Get schema info from the discovered database structure"""
        if not self.discovered_schema:
            return SchemaInfo(
                node_labels=[],
                relationship_types=[],
                property_keys=[],
                constraints=[],
                indexes=[]
            )
        
        return SchemaInfo(
            node_labels=self.discovered_schema.get('node_labels', []),
            relationship_types=self.discovered_schema.get('relationship_types', []),
            property_keys=self.discovered_schema.get('property_keys', []),
            constraints=self.discovered_schema.get('constraints', []),
            indexes=self.discovered_schema.get('indexes', [])
        )
    
    def translate_to_cypher(self, request: NLPQueryRequest) -> NLPQueryResponse:
        """Translate natural language query to Cypher using discovered schema"""
        
        if not self.discovered_schema or not self.discovered_schema['node_labels']:
            return NLPQueryResponse(
                cypher_query="// Error: No database schema discovered",
                explanation="Cannot translate query - no database schema available",
                confidence=0.0,
                parameters={}
            )
        
        # Create the prompt template
        prompt_template = self._create_adaptive_prompt_template()
        
        # Prepare the input for the LLM
        prompt_input = {
            "natural_language_query": request.natural_language_query,
            "discovered_schema": self._format_discovered_schema(),
            "context": request.context or "",
            "sample_queries": self._generate_sample_queries(),
            "relationship_patterns": self._format_relationship_patterns()
        }
        
        try:
            # Generate the Cypher query using modern LangChain API
            chain = prompt_template | self.llm
            result = chain.invoke(prompt_input)
            
            # Extract content from AIMessage if needed
            if hasattr(result, 'content'):
                result = result.content
            
            # Parse the result
            response = self._parse_llm_response(result)
            
            # Validate the query against discovered schema
            validation_result = self._validate_against_discovered_schema(response.cypher_query)
            if not validation_result["valid"]:
                response.confidence = max(0.0, response.confidence - 0.3)
                response.explanation += f" Warning: Query uses elements not found in database: {validation_result['issues']}"
            
            # Test syntax
            syntax_validation = self._validate_cypher_syntax(response.cypher_query)
            if not syntax_validation["valid"]:
                response.confidence = max(0.0, response.confidence - 0.4)
                response.explanation += f" Syntax error: {syntax_validation['error']}"
            
            return response
            
        except Exception as e:
            logger.error(f"Error translating NLP to Cypher: {e}")
            return NLPQueryResponse(
                cypher_query="// Error: Could not translate query",
                explanation=f"Error occurred during translation: {str(e)}",
                confidence=0.0,
                parameters={}
            )
    
    def _create_adaptive_prompt_template(self) -> PromptTemplate:
        """Create prompt template using discovered schema"""
        template = """
You are an expert at translating natural language queries into Neo4j Cypher queries.

IMPORTANT: You must ONLY use the node labels, relationship types, and properties that exist in the actual database schema provided below. Do NOT make up or assume any schema elements.

DISCOVERED DATABASE SCHEMA:
{discovered_schema}

RELATIONSHIP PATTERNS:
{relationship_patterns}

SAMPLE QUERIES FOR THIS DATABASE:
{sample_queries}

Natural Language Query: {natural_language_query}
Context: {context}

Instructions:
1. ONLY use node labels that appear in the discovered schema above
2. ONLY use relationship types that appear in the discovered schema above  
3. ONLY use property names that exist on the relevant nodes
4. If the query asks for something not available in the schema, explain what's missing
5. Prefer simpler queries that are more likely to return results
6. Use appropriate WHERE clauses and LIMIT results to avoid overwhelming output

Return your response in this JSON format:
{{
    "cypher_query": "MATCH (n:ActualNodeLabel) RETURN n LIMIT 10",
    "explanation": "Explanation of what the query does and why",
    "confidence": 0.85,
    "parameters": {{}}
}}

Response:
"""
        return PromptTemplate(
            template=template,
            input_variables=["natural_language_query", "discovered_schema", "context", "sample_queries", "relationship_patterns"]
        )
    
    def _format_discovered_schema(self) -> str:
        """Format the discovered schema for the prompt"""
        if not self.discovered_schema:
            return "No schema discovered"
        
        schema_str = "ACTUAL DATABASE CONTENTS:\n\n"
        
        # Node labels with counts and key properties
        schema_str += "Node Labels:\n"
        for label in self.discovered_schema['node_labels']:
            count = self.discovered_schema.get('node_counts', {}).get(label, 0)
            props = self.discovered_schema.get('node_properties', {}).get(label, {})
            key_props = list(props.keys())[:5]  # Show first 5 properties
            schema_str += f"  - {label} ({count} nodes) - Properties: {', '.join(key_props)}\n"
        
        schema_str += "\nRelationship Types:\n"
        for rel_type in self.discovered_schema['relationship_types']:
            schema_str += f"  - {rel_type}\n"
        
        # Add trading-specific insights if available
        if self.trading_elements:
            schema_str += "\nIdentified Trading-Related Elements:\n"
            
            if self.trading_elements.get('potential_trader_nodes'):
                schema_str += "  Potential Trader/User Nodes:\n"
                for node in self.trading_elements['potential_trader_nodes'][:3]:
                    schema_str += f"    - {node['label']}: {node['reason']}\n"
            
            if self.trading_elements.get('potential_order_nodes'):
                schema_str += "  Potential Order/Transaction Nodes:\n"
                for node in self.trading_elements['potential_order_nodes'][:3]:
                    schema_str += f"    - {node['label']}: {node['reason']}\n"
            
            if self.trading_elements.get('temporal_properties'):
                schema_str += "  Time-related Properties:\n"
                for prop in self.trading_elements['temporal_properties'][:5]:
                    schema_str += f"    - {prop['label']}.{prop['property']}\n"
        
        return schema_str
    
    def _format_relationship_patterns(self) -> str:
        """Format relationship patterns discovered in the database"""
        if not self.discovered_schema.get('relationship_patterns'):
            return "No relationship patterns discovered"
        
        patterns_str = "COMMON RELATIONSHIP PATTERNS:\n"
        for pattern in self.discovered_schema['relationship_patterns'][:10]:  # Top 10 patterns
            source_labels = ', '.join(pattern['source_labels'])
            target_labels = ', '.join(pattern['target_labels'])
            rel_type = pattern['relationship_type']
            count = pattern['count']
            
            patterns_str += f"  ({source_labels})-[:{rel_type}]->({target_labels}) - {count} instances\n"
        
        return patterns_str
    
    def _generate_sample_queries(self) -> str:
        """Generate sample queries based on discovered schema"""
        if not self.discovered_schema:
            return "No sample queries available"
        
        sample_queries = schema_discovery.generate_sample_queries()
        
        queries_str = "EXAMPLE QUERIES FOR THIS DATABASE:\n\n"
        for i, query_info in enumerate(sample_queries[:8], 1):  # Show up to 8 examples
            queries_str += f"Example {i}:\n"
            queries_str += f"Description: {query_info['description']}\n"
            queries_str += f"Cypher: {query_info['cypher']}\n\n"
        
        return queries_str
    
    def _validate_against_discovered_schema(self, cypher_query: str) -> Dict[str, Any]:
        """Validate query against discovered schema"""
        issues = []
        
        if not self.discovered_schema:
            return {"valid": False, "issues": ["No schema available for validation"]}
        
        # Extract node labels from query (simple regex approach)
        
        # Find node labels in MATCH clauses
        node_patterns = re.findall(r':\s*([A-Za-z_][A-Za-z0-9_]*)', cypher_query)
        for label in node_patterns:
            if label not in self.discovered_schema['node_labels']:
                issues.append(f"Node label '{label}' not found in database")
        
        # Find relationship types
        rel_patterns = re.findall(r'\[:\s*([A-Za-z_][A-Za-z0-9_]*)\]', cypher_query)
        for rel_type in rel_patterns:
            if rel_type not in self.discovered_schema['relationship_types']:
                issues.append(f"Relationship type '{rel_type}' not found in database")
        
        return {"valid": len(issues) == 0, "issues": issues}
    
    def _validate_cypher_syntax(self, cypher_query: str) -> Dict[str, Any]:
        """Validate Cypher syntax"""
        try:
            # Try to explain the query to check syntax
            explain_query = f"EXPLAIN {cypher_query}"
            self.db.execute_query(explain_query)
            return {"valid": True, "error": None}
        except Exception as e:
            return {"valid": False, "error": str(e)}
    
    def _parse_llm_response(self, response: str) -> NLPQueryResponse:
        """Parse the LLM response into a structured format"""
        try:
            # Try to parse as JSON first
            if response.strip().startswith('{'):
                parsed = json.loads(response)
                return NLPQueryResponse(
                    cypher_query=parsed.get("cypher_query", ""),
                    explanation=parsed.get("explanation", ""),
                    confidence=parsed.get("confidence", 0.5),
                    parameters=parsed.get("parameters", {})
                )
            
            # If not JSON, try to extract the query from the response
            lines = response.strip().split('\n')
            cypher_query = ""
            explanation = ""
            confidence = 0.5
            
            for line in lines:
                if line.strip().startswith('MATCH') or line.strip().startswith('CREATE') or line.strip().startswith('RETURN'):
                    cypher_query = line.strip()
                    break
            
            if not cypher_query:
                # Look for code blocks
                if '```' in response:
                    parts = response.split('```')
                    for part in parts:
                        if 'MATCH' in part or 'CREATE' in part or 'RETURN' in part:
                            cypher_query = part.strip()
                            break
            
            explanation = f"Generated Cypher query based on discovered database schema"
            
            return NLPQueryResponse(
                cypher_query=cypher_query,
                explanation=explanation,
                confidence=confidence,
                parameters={}
            )
            
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return NLPQueryResponse(
                cypher_query="// Error: Could not parse response",
                explanation=f"Error parsing LLM response: {str(e)}",
                confidence=0.0,
                parameters={}
            )
    
    def execute_translated_query(self, cypher_query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute the translated Cypher query"""
        try:
            return self.db.execute_query(cypher_query, parameters)
        except Exception as e:
            logger.error(f"Error executing translated query: {e}")
            raise e
    
    def refresh_schema(self):
        """Refresh the schema discovery"""
        self._initialize_schema()

# Global adaptive translator instance
adaptive_nlp_translator = AdaptiveNLPToCypherTranslator() if settings.openai_api_key else None 