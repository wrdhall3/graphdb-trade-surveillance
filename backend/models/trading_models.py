from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum

class TradingAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    PARTIAL = "PARTIAL"

class SuspiciousPatternType(str, Enum):
    SPOOFING = "SPOOFING"
    LAYERING = "LAYERING"
    WASH_TRADING = "WASH_TRADING"
    FRONT_RUNNING = "FRONT_RUNNING"

class TradeModel(BaseModel):
    trade_id: str
    order_id: str
    trader_id: str
    instrument: str
    side: TradingAction
    quantity: float
    price: float
    timestamp: datetime
    status: OrderStatus
    venue: Optional[str] = None
    
class OrderModel(BaseModel):
    order_id: str
    trader_id: str
    instrument: str
    side: TradingAction
    quantity: float
    price: float
    timestamp: datetime
    status: OrderStatus
    filled_quantity: float = 0.0
    venue: Optional[str] = None
    
class TraderModel(BaseModel):
    trader_id: str
    name: Optional[str] = None
    firm: Optional[str] = None
    risk_score: Optional[float] = None
    
class InstrumentModel(BaseModel):
    symbol: str
    name: Optional[str] = None
    asset_class: Optional[str] = None
    
class SuspiciousActivity(BaseModel):
    activity_id: str
    pattern_type: SuspiciousPatternType
    trader_id: str
    account_id: Optional[str] = None
    instrument: str
    confidence_score: float
    timestamp: datetime
    description: str
    related_trades: List[str]
    related_orders: List[str]
    severity: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    
class AlertModel(BaseModel):
    alert_id: str
    suspicious_activity: SuspiciousActivity
    status: str = "OPEN"  # OPEN, INVESTIGATING, RESOLVED, FALSE_POSITIVE
    created_at: datetime
    updated_at: Optional[datetime] = None
    assigned_to: Optional[str] = None
    notes: Optional[str] = None
    
class CypherQuery(BaseModel):
    query: str
    parameters: Optional[Dict[str, Any]] = None
    
class NLPQueryRequest(BaseModel):
    natural_language_query: str
    context: Optional[str] = None
    
class NLPQueryResponse(BaseModel):
    cypher_query: str
    explanation: str
    confidence: float
    parameters: Optional[Dict[str, Any]] = None
    
class SchemaInfo(BaseModel):
    node_labels: List[str]
    relationship_types: List[str]
    property_keys: List[str]
    constraints: List[Dict[str, Any]]
    indexes: List[Dict[str, Any]]
    
class PatternDetectionResult(BaseModel):
    pattern_type: SuspiciousPatternType
    detected_activities: List[SuspiciousActivity]
    analysis_timestamp: datetime
    total_patterns_found: int
    
class MonitoringConfig(BaseModel):
    enabled: bool = True
    check_interval_minutes: int = 5
    patterns_to_monitor: List[SuspiciousPatternType] = [
        SuspiciousPatternType.SPOOFING,
        SuspiciousPatternType.LAYERING
    ]
    confidence_threshold: float = 0.7
    severity_threshold: str = "MEDIUM" 