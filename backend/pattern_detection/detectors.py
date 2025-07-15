from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import uuid
import logging
from database.neo4j_connection import db_connection
from models.trading_models import SuspiciousActivity, SuspiciousPatternType

logger = logging.getLogger(__name__)

class PatternDetector:
    def __init__(self):
        self.db = db_connection
        
    def detect_all_patterns(self, lookback_hours: int = 24) -> List[SuspiciousActivity]:
        """Detect all suspicious patterns in the specified time window"""
        all_activities = []
        
        # Detect spoofing patterns
        spoofing_activities = self.detect_spoofing(lookback_hours)
        all_activities.extend(spoofing_activities)
        
        # Detect layering patterns
        layering_activities = self.detect_layering(lookback_hours)
        all_activities.extend(layering_activities)
        
        return all_activities
    
    def detect_spoofing(self, lookback_hours: int = 24) -> List[SuspiciousActivity]:
        """
        Detect spoofing patterns:
        - Large orders placed and quickly cancelled
        - Orders placed on one side of the book to manipulate price
        - Pattern of placing and cancelling orders without intention to trade
        """
        activities = []
        
        # Query for potential spoofing patterns
        spoofing_query = """
        MATCH (t:Trader)-[:PLACED]->(o:Order)-[:FOR_INSTRUMENT]->(i:Instrument)
        WHERE o.timestamp >= datetime() - duration({hours: $lookback_hours})
        WITH t, i, collect(o) as orders
        WHERE size(orders) >= 5  // Minimum orders to consider spoofing
        
        // Calculate cancellation patterns
        WITH t, i, orders,
             [o IN orders WHERE o.status = 'CANCELLED'] as cancelled_orders,
             [o IN orders WHERE o.status = 'FILLED'] as filled_orders
        
        WHERE size(cancelled_orders) > 0 AND 
              toFloat(size(cancelled_orders)) / size(orders) >= 0.7  // High cancellation rate
        
        // Check for quick cancellations (within 30 seconds)
        WITH t, i, orders, cancelled_orders, filled_orders,
             [o IN cancelled_orders WHERE duration.between(o.timestamp, o.cancelled_at).seconds <= 30] as quick_cancellations
        
        WHERE size(quick_cancellations) >= 3  // Multiple quick cancellations
        
        // Check for large order sizes compared to typical market
        WITH t, i, orders, cancelled_orders, filled_orders, quick_cancellations,
             [o IN cancelled_orders WHERE o.quantity >= 1000] as large_cancelled_orders
        
        WHERE size(large_cancelled_orders) >= 2  // Large orders being cancelled
        
        RETURN t.trader_id as trader_id, 
               i.symbol as instrument,
               collect(o.order_id) as related_orders,
               size(cancelled_orders) as total_cancelled,
               size(quick_cancellations) as quick_cancelled,
               size(large_cancelled_orders) as large_cancelled,
               min(o.timestamp) as earliest_order,
               max(o.timestamp) as latest_order
        """
        
        try:
            results = self.db.execute_query(spoofing_query, {"lookback_hours": lookback_hours})
            
            for result in results:
                # Calculate confidence score based on multiple factors
                confidence_score = self._calculate_spoofing_confidence(result)
                
                if confidence_score >= 0.6:  # Minimum confidence threshold
                    activity = SuspiciousActivity(
                        activity_id=str(uuid.uuid4()),
                        pattern_type=SuspiciousPatternType.SPOOFING,
                        trader_id=result['trader_id'],
                        instrument=result['instrument'],
                        confidence_score=confidence_score,
                        timestamp=datetime.now(),
                        description=f"Potential spoofing detected: {result['total_cancelled']} cancelled orders, "
                                  f"{result['quick_cancelled']} quick cancellations, "
                                  f"{result['large_cancelled']} large cancelled orders",
                        related_trades=[],
                        related_orders=result['related_orders'],
                        severity=self._determine_severity(confidence_score)
                    )
                    activities.append(activity)
                    
        except Exception as e:
            logger.error(f"Error detecting spoofing patterns: {e}")
            
        return activities
    
    def detect_layering(self, lookback_hours: int = 24) -> List[SuspiciousActivity]:
        """
        Detect layering patterns:
        - Multiple orders placed at different price levels
        - Orders placed to create appearance of demand/supply
        - Pattern of placing orders on multiple levels and then trading through them
        """
        activities = []
        
        # Query for potential layering patterns
        layering_query = """
        MATCH (t:Trader)-[:PLACED]->(o:Order)-[:FOR_INSTRUMENT]->(i:Instrument)
        WHERE o.timestamp >= datetime() - duration({hours: $lookback_hours})
        WITH t, i, collect(o) as orders
        WHERE size(orders) >= 10  // Minimum orders to consider layering
        
        // Group orders by side (BUY/SELL)
        WITH t, i, orders,
             [o IN orders WHERE o.side = 'BUY'] as buy_orders,
             [o IN orders WHERE o.side = 'SELL'] as sell_orders
        
        // Check for multiple price levels
        WITH t, i, orders, buy_orders, sell_orders,
             size(apoc.coll.toSet([o IN buy_orders | o.price])) as buy_price_levels,
             size(apoc.coll.toSet([o IN sell_orders | o.price])) as sell_price_levels
        
        WHERE buy_price_levels >= 3 OR sell_price_levels >= 3  // Multiple price levels
        
        // Check for orders placed in quick succession
        WITH t, i, orders, buy_orders, sell_orders, buy_price_levels, sell_price_levels
        ORDER BY head(orders).timestamp
        WITH t, i, orders, buy_orders, sell_orders, buy_price_levels, sell_price_levels,
             [i IN range(0, size(orders)-2) WHERE 
              duration.between(orders[i].timestamp, orders[i+1].timestamp).seconds <= 10] as rapid_orders
        
        WHERE size(rapid_orders) >= 5  // Rapid order placement
        
        // Check for eventual cancellations or small fills
        WITH t, i, orders, buy_orders, sell_orders, buy_price_levels, sell_price_levels,
             [o IN orders WHERE o.status = 'CANCELLED'] as cancelled_orders,
             [o IN orders WHERE o.status = 'FILLED' AND o.filled_quantity < o.quantity * 0.5] as small_fills
        
        WHERE size(cancelled_orders) + size(small_fills) >= size(orders) * 0.6  // Most orders cancelled or small fills
        
        RETURN t.trader_id as trader_id,
               i.symbol as instrument,
               collect(o.order_id) as related_orders,
               size(orders) as total_orders,
               buy_price_levels,
               sell_price_levels,
               size(cancelled_orders) as cancelled_count,
               size(small_fills) as small_fills_count,
               min(o.timestamp) as earliest_order,
               max(o.timestamp) as latest_order
        """
        
        try:
            results = self.db.execute_query(layering_query, {"lookback_hours": lookback_hours})
            
            for result in results:
                # Calculate confidence score based on multiple factors
                confidence_score = self._calculate_layering_confidence(result)
                
                if confidence_score >= 0.6:  # Minimum confidence threshold
                    activity = SuspiciousActivity(
                        activity_id=str(uuid.uuid4()),
                        pattern_type=SuspiciousPatternType.LAYERING,
                        trader_id=result['trader_id'],
                        instrument=result['instrument'],
                        confidence_score=confidence_score,
                        timestamp=datetime.now(),
                        description=f"Potential layering detected: {result['total_orders']} orders across "
                                  f"{result['buy_price_levels']} buy levels and {result['sell_price_levels']} sell levels, "
                                  f"{result['cancelled_count']} cancelled, {result['small_fills_count']} small fills",
                        related_trades=[],
                        related_orders=result['related_orders'],
                        severity=self._determine_severity(confidence_score)
                    )
                    activities.append(activity)
                    
        except Exception as e:
            logger.error(f"Error detecting layering patterns: {e}")
            
        return activities
    
    def _calculate_spoofing_confidence(self, result: Dict[str, Any]) -> float:
        """Calculate confidence score for spoofing detection"""
        confidence = 0.0
        
        # High cancellation rate
        if result['total_cancelled'] > 0:
            confidence += 0.3
            
        # Quick cancellations
        if result['quick_cancelled'] >= 3:
            confidence += 0.4
            
        # Large cancelled orders
        if result['large_cancelled'] >= 2:
            confidence += 0.3
            
        return min(confidence, 1.0)
    
    def _calculate_layering_confidence(self, result: Dict[str, Any]) -> float:
        """Calculate confidence score for layering detection"""
        confidence = 0.0
        
        # Multiple price levels
        total_levels = result['buy_price_levels'] + result['sell_price_levels']
        if total_levels >= 5:
            confidence += 0.3
        elif total_levels >= 3:
            confidence += 0.2
            
        # High order count
        if result['total_orders'] >= 20:
            confidence += 0.3
        elif result['total_orders'] >= 10:
            confidence += 0.2
            
        # High cancellation/small fill rate
        total_cancelled_small = result['cancelled_count'] + result['small_fills_count']
        if total_cancelled_small >= result['total_orders'] * 0.8:
            confidence += 0.4
        elif total_cancelled_small >= result['total_orders'] * 0.6:
            confidence += 0.3
            
        return min(confidence, 1.0)
    
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