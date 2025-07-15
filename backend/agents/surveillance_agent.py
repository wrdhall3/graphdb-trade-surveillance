from typing import Dict, Any, List, Optional, TypedDict
import asyncio
import logging
from datetime import datetime, timedelta
from langgraph.graph import StateGraph, END
from langchain_community.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
import uuid

from pattern_detection.adaptive_detectors import AdaptivePatternDetector
from models.trading_models import SuspiciousActivity, AlertModel, MonitoringConfig, SuspiciousPatternType
from database.neo4j_connection import db_connection
from config import settings

logger = logging.getLogger(__name__)

class SurveillanceState(TypedDict):
    messages: List[BaseMessage]
    current_activity: Optional[SuspiciousActivity]
    detected_patterns: List[SuspiciousActivity]
    analysis_results: Dict[str, Any]
    alerts_generated: List[AlertModel]
    monitoring_config: MonitoringConfig
    iteration_count: int
    should_escalate: bool

class PatternAnalysisTool(BaseTool):
    name: str = "pattern_analysis"
    description: str = "Analyze detected suspicious patterns and provide detailed reasoning"
    detector: AdaptivePatternDetector
    
    def __init__(self, detector: AdaptivePatternDetector):
        super().__init__(detector=detector)
    
    def _run(self, pattern_type: str, activities: List[Dict[str, Any]]) -> str:
        """Analyze patterns and provide reasoning"""
        if not activities:
            return "No activities to analyze"
        
        analysis = {
            "pattern_type": pattern_type,
            "total_activities": len(activities),
            "high_confidence_count": len([a for a in activities if a.get("confidence_score", 0) > 0.8]),
            "traders_involved": list(set([a.get("trader_id") for a in activities])),
            "instruments_affected": list(set([a.get("instrument") for a in activities])),
            "severity_distribution": {}
        }
        
        # Calculate severity distribution
        for activity in activities:
            severity = activity.get("severity", "MEDIUM")
            analysis["severity_distribution"][severity] = analysis["severity_distribution"].get(severity, 0) + 1
        
        # Generate reasoning
        reasoning = f"""
        Pattern Analysis for {pattern_type}:
        - Total suspicious activities detected: {analysis['total_activities']}
        - High confidence activities (>80%): {analysis['high_confidence_count']}
        - Unique traders involved: {len(analysis['traders_involved'])}
        - Instruments affected: {len(analysis['instruments_affected'])}
        - Severity distribution: {analysis['severity_distribution']}
        
        Recommendation: {'ESCALATE' if analysis['high_confidence_count'] > 0 else 'MONITOR'}
        """
        
        return reasoning
    
    async def _arun(self, pattern_type: str, activities: List[Dict[str, Any]]) -> str:
        return self._run(pattern_type, activities)

class EscalationDecisionTool(BaseTool):
    name: str = "escalation_decision"
    description: str = "Make escalation decisions based on analysis results"
    
    def _run(self, analysis_results: Dict[str, Any], config: Dict[str, Any]) -> str:
        """Make escalation decisions"""
        should_escalate = False
        reasoning = []
        
        # Check confidence thresholds
        confidence_threshold = config.get("confidence_threshold", 0.7)
        high_confidence_activities = [
            a for a in analysis_results.get("detected_patterns", [])
            if a.get("confidence_score", 0) >= confidence_threshold
        ]
        
        if high_confidence_activities:
            should_escalate = True
            reasoning.append(f"Found {len(high_confidence_activities)} high-confidence activities")
        
        # Check severity thresholds
        severity_threshold = config.get("severity_threshold", "MEDIUM")
        critical_activities = [
            a for a in analysis_results.get("detected_patterns", [])
            if a.get("severity") in ["HIGH", "CRITICAL"]
        ]
        
        if critical_activities:
            should_escalate = True
            reasoning.append(f"Found {len(critical_activities)} critical/high severity activities")
        
        # Check for multiple traders
        unique_traders = set([
            a.get("trader_id") for a in analysis_results.get("detected_patterns", [])
        ])
        if len(unique_traders) > 3:
            should_escalate = True
            reasoning.append(f"Multiple traders involved: {len(unique_traders)}")
        
        decision = {
            "should_escalate": should_escalate,
            "reasoning": reasoning,
            "priority": "HIGH" if should_escalate else "MEDIUM"
        }
        
        return str(decision)
    
    async def _arun(self, analysis_results: Dict[str, Any], config: Dict[str, Any]) -> str:
        return self._run(analysis_results, config)

class SurveillanceAgent:
    def __init__(self):
        self.detector = AdaptivePatternDetector()
        self.db = db_connection
        self.llm = ChatOpenAI(
            temperature=0.1,
            model_name="gpt-4",
            openai_api_key=settings.openai_api_key
        ) if settings.openai_api_key else None
        
        # Initialize tools
        self.pattern_analysis_tool = PatternAnalysisTool(self.detector)
        self.escalation_tool = EscalationDecisionTool()
        
        # Create the agent graph
        self.graph = self._create_agent_graph()
        
    def _create_agent_graph(self) -> StateGraph:
        """Create the LangGraph agent workflow"""
        workflow = StateGraph(SurveillanceState)
        
        # Define nodes
        workflow.add_node("detect_patterns", self.detect_patterns_node)
        workflow.add_node("analyze_patterns", self.analyze_patterns_node)
        workflow.add_node("make_escalation_decision", self.escalation_decision_node)
        workflow.add_node("generate_alerts", self.generate_alerts_node)
        workflow.add_node("update_monitoring", self.update_monitoring_node)
        
        # Define edges
        workflow.set_entry_point("detect_patterns")
        workflow.add_edge("detect_patterns", "analyze_patterns")
        workflow.add_edge("analyze_patterns", "make_escalation_decision")
        workflow.add_edge("make_escalation_decision", "generate_alerts")
        workflow.add_edge("generate_alerts", "update_monitoring")
        workflow.add_edge("update_monitoring", END)
        
        return workflow.compile()
    
    async def detect_patterns_node(self, state: SurveillanceState) -> SurveillanceState:
        """Node to detect suspicious patterns"""
        logger.info("Starting pattern detection...")
        
        try:
            # Detect all patterns - use a reasonable lookback period of 7 days instead of calculating from check interval
            detected_patterns = self.detector.detect_all_patterns(
                lookback_hours=168  # Always look back 7 days for pattern detection
            )
            
            # Add system message
            system_msg = SystemMessage(
                content=f"Detected {len(detected_patterns)} suspicious patterns in the latest scan."
            )
            
            state["messages"].append(system_msg)
            state["detected_patterns"] = detected_patterns
            
        except Exception as e:
            logger.error(f"Error in pattern detection: {e}")
            error_msg = SystemMessage(content=f"Error in pattern detection: {str(e)}")
            state["messages"].append(error_msg)
        
        return state
    
    async def analyze_patterns_node(self, state: SurveillanceState) -> SurveillanceState:
        """Node to analyze detected patterns"""
        logger.info("Analyzing detected patterns...")
        
        if not state["detected_patterns"]:
            state["messages"].append(SystemMessage(content="No patterns detected to analyze"))
            return state
        
        try:
            # Group patterns by type
            pattern_groups = {}
            for pattern in state["detected_patterns"]:
                pattern_type = pattern.pattern_type
                if pattern_type not in pattern_groups:
                    pattern_groups[pattern_type] = []
                pattern_groups[pattern_type].append(pattern.dict())
            
            # Analyze each pattern type
            analysis_results = {}
            for pattern_type, activities in pattern_groups.items():
                analysis = self.pattern_analysis_tool._run(pattern_type, activities)
                analysis_results[pattern_type] = analysis
            
            state["analysis_results"] = analysis_results
            
            # Add analysis message
            analysis_msg = SystemMessage(
                content=f"Pattern analysis completed for {len(pattern_groups)} pattern types"
            )
            state["messages"].append(analysis_msg)
            
        except Exception as e:
            logger.error(f"Error in pattern analysis: {e}")
            error_msg = SystemMessage(content=f"Error in pattern analysis: {str(e)}")
            state["messages"].append(error_msg)
        
        return state
    
    async def escalation_decision_node(self, state: SurveillanceState) -> SurveillanceState:
        """Node to make escalation decisions"""
        logger.info("Making escalation decisions...")
        
        try:
            # Make escalation decision
            decision_result = self.escalation_tool._run(
                {"detected_patterns": [p.dict() for p in state["detected_patterns"]]},
                state["monitoring_config"].dict()
            )
            
            # Parse decision
            decision = eval(decision_result)  # Note: In production, use proper JSON parsing
            state["should_escalate"] = decision["should_escalate"]
            
            # Add decision message
            decision_msg = SystemMessage(
                content=f"Escalation decision: {'ESCALATE' if decision['should_escalate'] else 'MONITOR'}"
            )
            state["messages"].append(decision_msg)
            
        except Exception as e:
            logger.error(f"Error in escalation decision: {e}")
            error_msg = SystemMessage(content=f"Error in escalation decision: {str(e)}")
            state["messages"].append(error_msg)
        
        return state
    
    async def generate_alerts_node(self, state: SurveillanceState) -> SurveillanceState:
        """Node to generate alerts"""
        logger.info("Generating alerts...")
        
        try:
            alerts = []
            
            # Generate alerts for suspicious activities
            for activity in state["detected_patterns"]:
                if activity.confidence_score >= state["monitoring_config"].confidence_threshold:
                    alert = AlertModel(
                        alert_id=str(uuid.uuid4()),
                        suspicious_activity=activity,
                        status="OPEN",
                        created_at=datetime.now()
                    )
                    alerts.append(alert)
            
            state["alerts_generated"] = alerts
            
            # Add alerts message
            alerts_msg = SystemMessage(
                content=f"Generated {len(alerts)} alerts from detected patterns"
            )
            state["messages"].append(alerts_msg)
            
        except Exception as e:
            logger.error(f"Error generating alerts: {e}")
            error_msg = SystemMessage(content=f"Error generating alerts: {str(e)}")
            state["messages"].append(error_msg)
        
        return state
    
    async def update_monitoring_node(self, state: SurveillanceState) -> SurveillanceState:
        """Node to update monitoring state"""
        logger.info("Updating monitoring state...")
        
        try:
            # Update iteration count
            state["iteration_count"] += 1
            
            # Log monitoring results
            monitoring_msg = SystemMessage(
                content=f"Monitoring iteration {state['iteration_count']} completed. "
                       f"Found {len(state['detected_patterns'])} patterns, "
                       f"generated {len(state['alerts_generated'])} alerts."
            )
            state["messages"].append(monitoring_msg)
            
        except Exception as e:
            logger.error(f"Error updating monitoring: {e}")
            error_msg = SystemMessage(content=f"Error updating monitoring: {str(e)}")
            state["messages"].append(error_msg)
        
        return state
    
    async def run_surveillance_cycle(self, config: MonitoringConfig) -> Dict[str, Any]:
        """Run a complete surveillance cycle"""
        logger.info("Starting surveillance cycle...")
        
        # Initialize state
        initial_state = SurveillanceState(
            messages=[SystemMessage(content="Starting surveillance cycle...")],
            current_activity=None,
            detected_patterns=[],
            analysis_results={},
            alerts_generated=[],
            monitoring_config=config,
            iteration_count=0,
            should_escalate=False
        )
        
        # Run the agent graph
        result = await self.graph.ainvoke(initial_state)
        
        return {
            "detected_patterns": result["detected_patterns"],
            "analysis_results": result["analysis_results"],
            "alerts_generated": result["alerts_generated"],
            "should_escalate": result["should_escalate"],
            "iteration_count": result["iteration_count"],
            "messages": [msg.content for msg in result["messages"]]
        }
    
    async def continuous_monitoring(self, config: MonitoringConfig):
        """Run continuous monitoring"""
        logger.info("Starting continuous monitoring...")
        
        while config.enabled:
            try:
                # Run surveillance cycle
                results = await self.run_surveillance_cycle(config)
                
                # Log results
                logger.info(f"Surveillance cycle completed: {len(results['detected_patterns'])} patterns detected")
                
                # Wait for next cycle
                await asyncio.sleep(config.check_interval_minutes * 60)
                
            except Exception as e:
                logger.error(f"Error in continuous monitoring: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retry

# Global agent instance
surveillance_agent = SurveillanceAgent() if settings.openai_api_key else None 