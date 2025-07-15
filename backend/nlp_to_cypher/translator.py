from typing import Dict, Any, Optional, List
import re
import json
import logging
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from database.neo4j_connection import db_connection
from models.trading_models import NLPQueryRequest, NLPQueryResponse, SchemaInfo
from config import settings

logger = logging.getLogger(__name__)

class NLPToCypherTranslator:
    def __init__(self):
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key is required for NLP to Cypher translation")
        
        self.llm = ChatOpenAI(
            temperature=0.1,
            model_name="gpt-4",
            openai_api_key=settings.openai_api_key
        )
        
        self.db = db_connection
        self.schema_info = self._get_schema_info()
        
    def _get_schema_info(self) -> SchemaInfo:
        """Get the current Neo4j schema information"""
        try:
            schema_data = self.db.get_schema_info()
            return SchemaInfo(**schema_data)
        except Exception as e:
            logger.error(f"Error getting schema info: {e}")
            # Return a default schema if we can't get the actual one
            return SchemaInfo(
                node_labels=["Trader", "Account", "Transaction", "Security"],
                relationship_types=["PLACED_BY", "PLACED", "INVOLVES", "CONNECTED_TO"],
                property_keys=["trader_id", "account_id", "transaction_id", "symbol", "cusip", "instrument_type", "price", "quantity", "timestamp", "side", "status"],
                constraints=[],
                indexes=[]
            )
    
    def translate_to_cypher(self, request: NLPQueryRequest) -> NLPQueryResponse:
        """Translate natural language query to Cypher"""
        
        # Create the prompt template
        prompt_template = self._create_prompt_template()
        
        # Prepare the input for the LLM
        prompt_input = {
            "natural_language_query": request.natural_language_query,
            "schema_info": self._format_schema_info(),
            "context": request.context or "",
            "examples": self._get_example_queries()
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
            
            # Validate the query
            validation_result = self._validate_cypher_query(response.cypher_query)
            if not validation_result["valid"]:
                response.confidence = max(0.0, response.confidence - 0.3)
                response.explanation += f" Warning: Query validation failed: {validation_result['error']}"
            
            return response
            
        except Exception as e:
            logger.error(f"Error translating NLP to Cypher: {e}")
            return NLPQueryResponse(
                cypher_query="// Error: Could not translate query",
                explanation=f"Error occurred during translation: {str(e)}",
                confidence=0.0,
                parameters={}
            )
    
    def _create_prompt_template(self) -> PromptTemplate:
        """Create the prompt template for NLP to Cypher translation"""
        template = """
You are an expert at translating natural language queries into Neo4j Cypher queries for a financial trading surveillance system.

Database Schema:
{schema_info}

Example Queries:
{examples}

Natural Language Query: {natural_language_query}
Context: {context}

Please translate the natural language query into a Cypher query. Consider the following:
1. Use the exact node labels and relationship types from the schema
2. Include appropriate WHERE clauses for filtering
3. Use proper Cypher syntax
4. Consider temporal aspects (timestamps, dates)
5. Include relevant aggregations if needed
6. Make sure the query is optimized for performance

Return your response in the following JSON format:
{{
    "cypher_query": "MATCH (n:Node) RETURN n",
    "explanation": "Explanation of what the query does",
    "confidence": 0.95,
    "parameters": {{"param1": "value1"}}
}}

Response:
"""
        return PromptTemplate(
            template=template,
            input_variables=["natural_language_query", "schema_info", "context", "examples"]
        )
    
    def _format_schema_info(self) -> str:
        """Format schema information for the prompt"""
        schema_str = f"""
Node Labels: {', '.join(self.schema_info.node_labels)}
Relationship Types: {', '.join(self.schema_info.relationship_types)}
Property Keys: {', '.join(self.schema_info.property_keys)}

Common Properties:
- Trader: trader_id, name, firm, risk_score
- Order: order_id, trader_id, instrument, side, quantity, price, timestamp, status
- Trade: trade_id, order_id, trader_id, instrument, side, quantity, price, timestamp
- Security: symbol, cusip, instrument_type

Common Relationships:
- (Trader)-[:PLACED_BY]->(Transaction)
- (Account)-[:PLACED]->(Transaction)
- (Transaction)-[:INVOLVES]->(Security)
- (Transaction)-[:CONNECTED_TO]->(Transaction)
"""
        return schema_str
    
    def _get_example_queries(self) -> str:
        """Get example NLP to Cypher query pairs"""
        examples = """
Example 1:
Natural Language: "Show me all transactions placed by trader TR001 in the last 24 hours"
Cypher: MATCH (tx:Transaction)-[:PLACED_BY]->(t:Trader {trader_id: 'TR001'}) WHERE tx.timestamp >= datetime() - duration({hours: 24}) RETURN tx

Example 2:
Natural Language: "Find all transactions for AAPL stock"
Cypher: MATCH (tx:Transaction)-[:INVOLVES]->(s:Security {symbol: 'AAPL'}) RETURN tx

Example 3:
Natural Language: "Show me traders with more than 100 transactions today"
Cypher: MATCH (tx:Transaction)-[:PLACED_BY]->(t:Trader) WHERE tx.timestamp >= datetime({date: date()}) WITH t, count(tx) as tx_count WHERE tx_count > 100 RETURN t, tx_count

Example 4:
Natural Language: "Find large transactions above $1 million"
Cypher: MATCH (tx:Transaction) WHERE tx.price * tx.quantity > 1000000 RETURN tx

Example 5:
Natural Language: "Show me all buy orders that were quickly cancelled"
Cypher: MATCH (o:Order) WHERE o.side = 'BUY' AND o.status = 'CANCELLED' AND duration.between(o.timestamp, o.cancelled_at).seconds < 60 RETURN o
"""
        return examples
    
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
            
            explanation = f"Generated Cypher query from natural language input"
            
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
    
    def _validate_cypher_query(self, cypher_query: str) -> Dict[str, Any]:
        """Validate the generated Cypher query"""
        try:
            # Try to explain the query to check syntax
            explain_query = f"EXPLAIN {cypher_query}"
            self.db.execute_query(explain_query)
            return {"valid": True, "error": None}
        except Exception as e:
            return {"valid": False, "error": str(e)}
    
    def execute_translated_query(self, cypher_query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute the translated Cypher query"""
        try:
            return self.db.execute_query(cypher_query, parameters)
        except Exception as e:
            logger.error(f"Error executing translated query: {e}")
            raise e

# Global translator instance
nlp_translator = NLPToCypherTranslator() if settings.openai_api_key else None 