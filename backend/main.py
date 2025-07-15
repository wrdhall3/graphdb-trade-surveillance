from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
import logging
import asyncio
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

# Import our modules - use adaptive components
from config import settings
from database.neo4j_connection import db_connection
from database.schema_discovery import schema_discovery
from models.trading_models import (
    NLPQueryRequest, NLPQueryResponse, SuspiciousActivity, AlertModel, 
    MonitoringConfig, PatternDetectionResult, SchemaInfo, SuspiciousPatternType
)
from pattern_detection.adaptive_detectors import adaptive_detector
from nlp_to_cypher.adaptive_translator import adaptive_nlp_translator
from agents.surveillance_agent import surveillance_agent

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
monitoring_config = MonitoringConfig()
monitoring_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager"""
    # Startup
    logger.info("🚀 Starting Adaptive Trade Surveillance System...")
    startup_start = datetime.now()
    
    # Test database connection
    try:
        # Discover actual schema
        logger.info("📊 Discovering database schema...")
        discovered_schema = schema_discovery.discover_full_schema()
        logger.info(f"✅ Connected to Neo4j. Discovered {len(discovered_schema['node_labels'])} node types, {len(discovered_schema['relationship_types'])} relationship types.")
        
        # Log discovered trading elements
        trading_elements = schema_discovery.find_trading_related_nodes()
        logger.info(f"🔍 Identified {len(trading_elements.get('potential_trader_nodes', []))} potential trader nodes, "
                   f"{len(trading_elements.get('potential_order_nodes', []))} potential order nodes")
        
    except Exception as e:
        logger.error(f"❌ Failed to connect to Neo4j or discover schema: {e}")
        logger.warning("⚠️  Continuing startup with limited functionality")
    
    # Initialize pattern detector
    try:
        logger.info("🔍 Initializing pattern detection system...")
        adaptive_detector._initialize_schema()
        logger.info("✅ Pattern detection system initialized")
    except Exception as e:
        logger.error(f"❌ Pattern detection initialization failed: {e}")
        logger.warning("⚠️  Pattern detection may not work properly")
    
    # Start continuous monitoring if enabled
    try:
        if monitoring_config.enabled and surveillance_agent:
            logger.info("🤖 Starting continuous monitoring...")
            global monitoring_task
            monitoring_task = asyncio.create_task(
                surveillance_agent.continuous_monitoring(monitoring_config)
            )
            logger.info("✅ Continuous monitoring started")
    except Exception as e:
        logger.error(f"❌ Failed to start continuous monitoring: {e}")
        logger.warning("⚠️  Monitoring disabled")
    
    # Calculate startup time
    startup_time = (datetime.now() - startup_start).total_seconds()
    
    # Log that backend is ready
    logger.info(f"🎉 Backend startup completed in {startup_time:.2f} seconds!")
    logger.info(f"📊 API Documentation: http://{settings.api_host}:{settings.api_port}/docs")
    logger.info(f"🏥 Health Check: http://{settings.api_host}:{settings.api_port}/health")
    logger.info(f"🚀 Ready Check: http://{settings.api_host}:{settings.api_port}/ready")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Adaptive Trade Surveillance System...")
    
    # Cancel monitoring task
    if monitoring_task:
        monitoring_task.cancel()
    
    # Close database connection
    db_connection.close()

# Create FastAPI app with lifespan
app = FastAPI(
    title="Adaptive Trade Surveillance System",
    description="AI-powered trade surveillance system that adapts to any Neo4j GraphDB schema",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Adaptive Trade Surveillance System", 
        "status": "running",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "message": "Adaptive Trade Surveillance System is running"
    }

@app.get("/ready")
async def ready_check():
    """Ready check endpoint - indicates backend is fully initialized"""
    return {
        "status": "ready",
        "timestamp": datetime.now().isoformat(),
        "message": "Backend is ready to serve requests"
    }

@app.get("/api/test")
async def test_endpoint():
    """Simple test endpoint to check if the API is responsive"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "message": "API is responsive"
    }

# Schema Discovery endpoints
@app.get("/api/schema/discovered", response_model=Dict[str, Any])
async def get_discovered_schema():
    """Get the discovered database schema"""
    try:
        discovered_schema = schema_discovery.discover_full_schema()
        return discovered_schema
    except Exception as e:
        logger.error(f"Error getting discovered schema: {e}")
        raise HTTPException(status_code=500, detail=f"Error discovering schema: {str(e)}")

@app.get("/api/schema/trading-elements")
async def get_trading_elements():
    """Get identified trading-related elements in the database"""
    try:
        trading_elements = schema_discovery.find_trading_related_nodes()
        return trading_elements
    except Exception as e:
        logger.error(f"Error getting trading elements: {e}")
        raise HTTPException(status_code=500, detail=f"Error identifying trading elements: {str(e)}")

@app.get("/api/schema/sample-queries")
async def get_sample_queries():
    """Get sample queries based on discovered schema"""
    try:
        sample_queries = schema_discovery.generate_sample_queries()
        return {"sample_queries": sample_queries}
    except Exception as e:
        logger.error(f"Error generating sample queries: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating sample queries: {str(e)}")

@app.post("/api/schema/refresh")
async def refresh_schema():
    """Force refresh of schema discovery"""
    try:
        schema = schema_discovery.discover_full_schema(force_refresh=True)
        if adaptive_nlp_translator:
            adaptive_nlp_translator.refresh_schema()
        return {
            "message": "Schema refreshed successfully",
            "node_labels": len(schema['node_labels']),
            "relationship_types": len(schema['relationship_types'])
        }
    except Exception as e:
        logger.error(f"Error refreshing schema: {e}")
        raise HTTPException(status_code=500, detail=f"Error refreshing schema: {str(e)}")

# Add after the schema discovery endpoints, before the legacy schema endpoint

@app.get("/api/schema/analysis")
async def get_schema_analysis():
    """Get detailed analysis of the discovered schema for debugging"""
    try:
        schema = schema_discovery.discover_full_schema()
        trading_elements = schema_discovery.find_trading_related_nodes()
        
        analysis = {
            "summary": {
                "total_node_types": len(schema['node_labels']),
                "total_relationship_types": len(schema['relationship_types']),
                "total_properties": len(schema['property_keys']),
                "total_nodes_in_db": sum(schema.get('node_counts', {}).values())
            },
            "node_details": [],
            "relationship_details": [],
            "trading_analysis": trading_elements,
            "recommendations": []
        }
        
        # Detailed node analysis
        for label in schema['node_labels']:
            node_info = {
                "label": label,
                "count": schema.get('node_counts', {}).get(label, 0),
                "properties": schema.get('node_properties', {}).get(label, {}),
                "sample_query": f"MATCH (n:{label}) RETURN n LIMIT 5"
            }
            analysis["node_details"].append(node_info)
        
        # Relationship pattern analysis
        for pattern in schema.get('relationship_patterns', [])[:10]:
            rel_info = {
                "source_labels": pattern['source_labels'],
                "relationship_type": pattern['relationship_type'],
                "target_labels": pattern['target_labels'],
                "count": pattern['count'],
                "sample_query": f"MATCH (a)-[r:{pattern['relationship_type']}]->(b) RETURN a, r, b LIMIT 3"
            }
            analysis["relationship_details"].append(rel_info)
        
        # Generate recommendations
        recommendations = []
        
        if not trading_elements.get('potential_trader_nodes'):
            recommendations.append("No obvious trader/user nodes found. Pattern detection may be limited.")
        
        if not trading_elements.get('potential_order_nodes'):
            recommendations.append("No obvious order/transaction nodes found. Consider checking if trading data exists.")
        
        if not trading_elements.get('temporal_properties'):
            recommendations.append("No temporal properties found. Time-based pattern detection will not work.")
        
        if len(schema['node_labels']) == 0:
            recommendations.append("No nodes found in database. Please ensure database contains data.")
        
        analysis["recommendations"] = recommendations
        
        return analysis
        
    except Exception as e:
        logger.error(f"Error getting schema analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Error analyzing schema: {str(e)}")

# Legacy schema endpoint for compatibility
@app.get("/api/schema", response_model=SchemaInfo)
async def get_schema():
    """Get database schema information (legacy endpoint)"""
    try:
        if adaptive_nlp_translator:
            return adaptive_nlp_translator.get_discovered_schema_info()
        else:
            discovered_schema = schema_discovery.discover_full_schema()
            return SchemaInfo(
                node_labels=discovered_schema.get('node_labels', []),
                relationship_types=discovered_schema.get('relationship_types', []),
                property_keys=discovered_schema.get('property_keys', []),
                constraints=discovered_schema.get('constraints', []),
                indexes=discovered_schema.get('indexes', [])
            )
    except Exception as e:
        logger.error(f"Error getting schema: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting schema: {str(e)}")

@app.get("/api/data/sample/{label}")
async def get_sample_data(label: str, limit: int = Query(5, ge=1, le=50)):
    """Get sample data for a node label"""
    try:
        sample_data = db_connection.get_sample_data(label, limit)
        return {"label": label, "sample_data": sample_data}
    except Exception as e:
        logger.error(f"Error getting sample data: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting sample data: {str(e)}")

# Pattern Detection endpoints - now adaptive
@app.get("/api/patterns/detect", response_model=PatternDetectionResult)
async def detect_patterns(
    lookback_hours: int = Query(168, ge=1, le=168),
    pattern_types: Optional[List[SuspiciousPatternType]] = Query(None)
):
    """Detect suspicious patterns using adaptive algorithms"""
    try:
        logger.info(f"🌐 API: /api/patterns/detect called with lookback_hours={lookback_hours}")
        all_detected = adaptive_detector.detect_all_patterns(lookback_hours)
        logger.info(f"🌐 API: detect_all_patterns returned {len(all_detected)} patterns")
        
        # Filter by pattern types if specified
        if pattern_types:
            filtered_patterns = [p for p in all_detected if p.pattern_type in pattern_types]
            logger.info(f"🌐 API: Filtered to {len(filtered_patterns)} patterns for types {pattern_types}")
        else:
            filtered_patterns = all_detected
            logger.info(f"🌐 API: No filtering applied, returning all {len(filtered_patterns)} patterns")
        
        result = PatternDetectionResult(
            pattern_type=SuspiciousPatternType.SPOOFING,  # Default, will be ignored for multiple types
            detected_activities=filtered_patterns,
            analysis_timestamp=datetime.now(),
            total_patterns_found=len(filtered_patterns)
        )
        
        logger.info(f"🌐 API: Returning result with {len(filtered_patterns)} patterns")
        return result
        
    except Exception as e:
        logger.error(f"Error detecting patterns: {e}")
        raise HTTPException(status_code=500, detail=f"Error detecting patterns: {str(e)}")

@app.get("/api/patterns/spoofing")
async def get_spoofing_patterns(lookback_hours: int = Query(168, ge=1, le=168)):
    """Get spoofing-like patterns using adaptive detection"""
    try:
        patterns = adaptive_detector.detect_spoofing_patterns(lookback_hours)
        return {"pattern_type": "SPOOFING", "patterns": patterns, "count": len(patterns)}
    except Exception as e:
        logger.error(f"Error getting spoofing patterns: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting spoofing patterns: {str(e)}")

@app.get("/api/patterns/layering")
async def get_layering_patterns(lookback_hours: int = Query(168, ge=1, le=168)):
    """Get layering-like patterns using adaptive detection"""
    try:
        patterns = adaptive_detector.detect_layering_patterns(lookback_hours)
        return {"pattern_type": "LAYERING", "patterns": patterns, "count": len(patterns)}
    except Exception as e:
        logger.error(f"Error getting layering patterns: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting layering patterns: {str(e)}")

@app.get("/api/patterns/{pattern_id}/details")
async def get_pattern_details(pattern_id: str):
    """Get detailed information about a specific pattern including transactions, trader, and security details"""
    try:
        logger.info(f"🌐 API: /api/patterns/{pattern_id}/details called")
        
        # Add timeout to prevent hanging
        try:
            # First, detect all patterns to find the one with the given ID (with timeout)
            import asyncio
            all_patterns = await asyncio.wait_for(
                asyncio.to_thread(adaptive_detector.detect_all_patterns, 168), 
                timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.error(f"🌐 API: Pattern detection timed out after 30 seconds")
            raise HTTPException(status_code=503, detail="Pattern detection timed out")
        
        # Find the pattern with the given ID
        target_pattern = None
        for pattern in all_patterns:
            if pattern.activity_id == pattern_id:
                target_pattern = pattern
                break
        
        if not target_pattern:
            logger.error(f"🌐 API: Pattern {pattern_id} not found in {len(all_patterns)} detected patterns")
            raise HTTPException(status_code=404, detail=f"Pattern not found. Available patterns: {detected_ids[:5]}")
        
        # Get transaction details (with timeout to prevent hanging)
        transaction_details = []
        all_transaction_ids = target_pattern.related_trades  # Only use related_trades since we don't have orders
        
        # Limit to first 10 transactions to prevent performance issues
        limited_tx_ids = all_transaction_ids[:10]
        
        for tx_id in limited_tx_ids:
            try:
                tx_query = """
                MATCH (t:Transaction {transaction_id: $tx_id})
                RETURN t
                """
                tx_results = await asyncio.wait_for(
                    asyncio.to_thread(db_connection.execute_query, tx_query, {"tx_id": tx_id}),
                    timeout=5.0
                )
                if tx_results:
                    tx_data = dict(tx_results[0]['t'])
                    transaction_details.append({
                        "transaction_id": tx_id,
                        "details": tx_data
                    })
            except asyncio.TimeoutError:
                logger.warning(f"Timeout fetching details for transaction {tx_id}")
                transaction_details.append({
                    "transaction_id": tx_id,
                    "details": {"error": "Query timeout"}
                })
            except Exception as e:
                logger.warning(f"Could not fetch details for transaction {tx_id}: {e}")
                transaction_details.append({
                    "transaction_id": tx_id,
                    "details": {"error": "Could not fetch transaction details"}
                })
        
        # Get trader details (with timeout)
        trader_details = {}
        try:
            trader_query = """
            MATCH (trader:Trader {trader_id: $trader_id})
            RETURN trader
            """
            trader_results = await asyncio.wait_for(
                asyncio.to_thread(db_connection.execute_query, trader_query, {"trader_id": target_pattern.trader_id}),
                timeout=5.0
            )
            if trader_results:
                trader_details = dict(trader_results[0]['trader'])
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching trader details for {target_pattern.trader_id}")
            trader_details = {"error": "Query timeout"}
        except Exception as e:
            logger.warning(f"Could not fetch trader details for {target_pattern.trader_id}: {e}")
            trader_details = {"error": "Could not fetch trader details"}
        
        # Get security details (with timeout)
        security_details = {}
        try:
            # Try to get security details via the instrument identifier
            security_query = """
            MATCH (s:Security)
            WHERE s.symbol = $instrument OR s.cusip = $instrument
            RETURN s
            """
            security_results = await asyncio.wait_for(
                asyncio.to_thread(db_connection.execute_query, security_query, {"instrument": target_pattern.instrument}),
                timeout=5.0
            )
            if security_results:
                security_details = dict(security_results[0]['s'])
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching security details for {target_pattern.instrument}")
            security_details = {"error": "Query timeout"}
        except Exception as e:
            logger.warning(f"Could not fetch security details for {target_pattern.instrument}: {e}")
            security_details = {"error": "Could not fetch security details"}
        
        # Get account details (with timeout)
        account_details = {}
        try:
            if target_pattern.account_id:
                account_query = """
                MATCH (a:Account {account_id: $account_id})
                RETURN a
                """
                account_results = await asyncio.wait_for(
                    asyncio.to_thread(db_connection.execute_query, account_query, {"account_id": target_pattern.account_id}),
                    timeout=5.0
                )
                if account_results:
                    account_details = dict(account_results[0]['a'])
            else:
                account_details = {"message": "No account information available for this pattern"}
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching account details for {target_pattern.account_id}")
            account_details = {"error": "Query timeout"}
        except Exception as e:
            logger.warning(f"Could not fetch account details for {target_pattern.account_id}: {e}")
            account_details = {"error": "Could not fetch account details"}

        # Get related entities (connections) - simplified to avoid performance issues
        related_entities = {}
        try:
            # Simplified related entities query (limit to first 3 transactions)
            for tx_id in limited_tx_ids[:3]:
                related_query = """
                MATCH (t:Transaction {transaction_id: $tx_id})
                OPTIONAL MATCH (t)-[:CONNECTED_TO]->(connected:Transaction)
                OPTIONAL MATCH (t)-[:INVOLVES]->(security:Security)
                RETURN 
                    [c IN collect(DISTINCT connected) WHERE c IS NOT NULL | {id: c.transaction_id, type: 'Transaction'}] as connected_transactions,
                    [s IN collect(DISTINCT security) WHERE s IS NOT NULL | {id: s.symbol, type: 'Security'}] as involved_securities
                """
                related_results = await asyncio.wait_for(
                    asyncio.to_thread(db_connection.execute_query, related_query, {"tx_id": tx_id}),
                    timeout=5.0
                )
                if related_results:
                    related_entities[tx_id] = {
                        "connected_transactions": related_results[0]['connected_transactions'],
                        "involved_securities": related_results[0]['involved_securities']
                    }
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching related entities")
            related_entities = {"error": "Query timeout"}
        except Exception as e:
            logger.warning(f"Could not fetch related entities: {e}")
            related_entities = {"error": "Could not fetch related entities"}
        
        result = {
            "pattern_id": pattern_id,
            "pattern_info": {
                "pattern_type": target_pattern.pattern_type.value if hasattr(target_pattern.pattern_type, 'value') else str(target_pattern.pattern_type),
                "trader_id": target_pattern.trader_id,
                "account_id": target_pattern.account_id,
                "instrument": target_pattern.instrument,
                "confidence_score": target_pattern.confidence_score,
                "severity": target_pattern.severity,
                "timestamp": target_pattern.timestamp.isoformat(),
                "description": target_pattern.description,
                "related_trades": target_pattern.related_trades,
                "related_orders": []  # We only have transactions, not orders
            },
            "transaction_details": transaction_details,
            "trader_details": trader_details,
            "account_details": account_details,
            "security_details": security_details,
            "related_entities": related_entities
        }
        
        logger.info(f"🌐 API: Returning pattern details for {pattern_id}")
        return result
        
    except Exception as e:
        logger.error(f"Error getting pattern details: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting pattern details: {str(e)}")

# NLP to Cypher endpoints - now adaptive
@app.post("/api/nlp/translate", response_model=NLPQueryResponse)
async def translate_nlp_to_cypher(request: NLPQueryRequest):
    """Translate natural language to Cypher using discovered schema"""
    if not adaptive_nlp_translator:
        raise HTTPException(status_code=503, detail="NLP service not available (missing OpenAI API key)")
    
    try:
        response = adaptive_nlp_translator.translate_to_cypher(request)
        return response
    except Exception as e:
        logger.error(f"Error translating NLP to Cypher: {e}")
        raise HTTPException(status_code=500, detail=f"Error translating query: {str(e)}")

@app.post("/api/cypher/execute")
async def execute_cypher_query(
    query: str,
    parameters: Optional[Dict[str, Any]] = None
):
    """Execute a Cypher query"""
    try:
        results = db_connection.execute_query(query, parameters)
        return {
            "query": query,
            "parameters": parameters,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        logger.error(f"Error executing Cypher query: {e}")
        raise HTTPException(status_code=500, detail=f"Error executing query: {str(e)}")

@app.post("/api/nlp/query")
async def nlp_query(request: NLPQueryRequest):
    """Natural language query with translation and execution using discovered schema"""
    if not adaptive_nlp_translator:
        raise HTTPException(status_code=503, detail="NLP service not available (missing OpenAI API key)")
    
    try:
        # Translate to Cypher using discovered schema
        translation = adaptive_nlp_translator.translate_to_cypher(request)
        
        # Execute the query
        results = []
        error = None
        
        try:
            results = adaptive_nlp_translator.execute_translated_query(
                translation.cypher_query,
                translation.parameters
            )
        except Exception as e:
            error = str(e)
            logger.error(f"Error executing translated query: {e}")
        
        return {
            "natural_language_query": request.natural_language_query,
            "translation": translation.dict(),
            "results": results,
            "count": len(results),
            "error": error,
            "schema_used": "discovered"
        }
        
    except Exception as e:
        logger.error(f"Error processing NLP query: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")

# Monitoring and Agent endpoints (unchanged)
@app.get("/api/monitoring/config")
async def get_monitoring_config():
    """Get current monitoring configuration"""
    return monitoring_config.dict()

@app.post("/api/monitoring/config")
async def update_monitoring_config(config: MonitoringConfig):
    """Update monitoring configuration"""
    global monitoring_config, monitoring_task
    
    # Update config
    monitoring_config = config
    
    # Restart monitoring if needed
    if monitoring_task and not monitoring_task.done():
        monitoring_task.cancel()
    
    if config.enabled and surveillance_agent:
        monitoring_task = asyncio.create_task(
            surveillance_agent.continuous_monitoring(config)
        )
        logger.info("Restarted continuous monitoring with new config")
    
    return {"message": "Monitoring configuration updated", "config": config.dict()}

@app.post("/api/monitoring/run")
async def run_surveillance_cycle():
    """Run a single surveillance cycle"""
    if not surveillance_agent:
        raise HTTPException(status_code=503, detail="Surveillance agent not available (missing OpenAI API key)")
    
    try:
        results = await surveillance_agent.run_surveillance_cycle(monitoring_config)
        return results
    except Exception as e:
        logger.error(f"Error running surveillance cycle: {e}")
        raise HTTPException(status_code=500, detail=f"Error running surveillance cycle: {str(e)}")

@app.get("/api/monitoring/status")
async def get_monitoring_status():
    """Get monitoring status"""
    return {
        "enabled": monitoring_config.enabled,
        "running": monitoring_task is not None and not monitoring_task.done(),
        "config": monitoring_config.dict()
    }

# Alert endpoints
@app.get("/api/alerts")
async def get_alerts(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200)
):
    """Get alerts (this would typically come from a database)"""
    # For now, return sample alerts
    # In a real implementation, this would query alerts from the database
    return {
        "alerts": [],
        "total": 0,
        "filters": {
            "status": status,
            "severity": severity,
            "limit": limit
        }
    }

# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Health check endpoint to verify backend is ready"""
    try:
        # Test database connection
        db_status = "healthy"
        try:
            test_query = "RETURN 1 as test"
            db_connection.execute_query(test_query)
        except Exception as e:
            db_status = f"unhealthy: {str(e)}"
        
        # Test schema discovery
        schema_status = "healthy"
        try:
            schema = schema_discovery.discover_full_schema()
            if not schema.get('node_labels'):
                schema_status = "no_data"
        except Exception as e:
            schema_status = f"unhealthy: {str(e)}"
        
        return {
            "status": "healthy" if db_status == "healthy" and schema_status == "healthy" else "degraded",
            "database": db_status,
            "schema": schema_status,
            "adaptive_detector": "healthy" if adaptive_detector else "not_initialized",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# Dashboard endpoints - now adaptive
@app.get("/api/dashboard/summary")
async def get_dashboard_summary():
    """Get dashboard summary statistics using adaptive detection"""
    try:
        # Get recent patterns using adaptive detector with 7-day lookback
        logger.info("🌐 API: /api/dashboard/summary called")
        recent_patterns = adaptive_detector.detect_all_patterns(168)
        logger.info(f"🌐 API: Dashboard detected {len(recent_patterns)} patterns")
        
        # Calculate statistics
        spoofing_count = len([p for p in recent_patterns if p.pattern_type == SuspiciousPatternType.SPOOFING])
        layering_count = len([p for p in recent_patterns if p.pattern_type == SuspiciousPatternType.LAYERING])
        
        logger.info(f"🌐 API: Dashboard counts - Spoofing: {spoofing_count}, Layering: {layering_count}")
        
        high_confidence = len([p for p in recent_patterns if p.confidence_score >= 0.8])
        critical_severity = len([p for p in recent_patterns if p.severity == "CRITICAL"])
        
        unique_traders = len(set([p.trader_id for p in recent_patterns]))
        unique_instruments = len(set([p.instrument for p in recent_patterns]))
        
        # Get schema stats
        schema = schema_discovery.discover_full_schema()
        
        dashboard_data = {
            "total_patterns": len(recent_patterns),
            "spoofing_patterns": spoofing_count,
            "layering_patterns": layering_count,
            "high_confidence_patterns": high_confidence,
            "critical_patterns": critical_severity,
            "unique_traders": unique_traders,
            "unique_instruments": unique_instruments,
            "monitoring_status": monitoring_config.enabled,
            "last_updated": datetime.now().isoformat(),
            "database_stats": {
                "node_types": len(schema['node_labels']),
                "relationship_types": len(schema['relationship_types']),
                "total_nodes": sum(schema.get('node_counts', {}).values())
            }
        }
        
        logger.info(f"🌐 API: Dashboard returning - Total: {dashboard_data['total_patterns']}, Spoofing: {dashboard_data['spoofing_patterns']}, Layering: {dashboard_data['layering_patterns']}")
        return dashboard_data
        
    except Exception as e:
        logger.error(f"Error getting dashboard summary: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting dashboard summary: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    # Log startup information
    logger.info("🚀 Starting Trade Surveillance System...")
    logger.info(f"🔧 Environment: {settings.environment}")
    logger.info(f"🌐 API Host: {settings.api_host}:{settings.api_port}")
    logger.info(f"🗄️  Neo4j URI: {settings.neo4j_uri}")
    logger.info(f"🔍 Adaptive Detector: {'✅ Ready' if adaptive_detector else '❌ Not initialized'}")
    logger.info(f"🧠 NLP Translator: {'✅ Ready' if adaptive_nlp_translator else '❌ Not available'}")
    
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.environment == "development"
    ) 